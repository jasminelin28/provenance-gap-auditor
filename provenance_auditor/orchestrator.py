"""Runs the four agents in sequence and assembles one audit result.

    raw text
       |
       v
  parse_agent      (model call)  -> ownership events
       |
       v
  gap_agent        (rules only)  -> gaps
       |
       v
  crossref_agent   (tools only)  -> matches in Wikidata, Getty, local tables
       |
       v
  verdict_agent    (model call)  -> rating + explanation, then a rule-based floor

Two of the four steps need no model at all, which is why one run costs about
half of what a fully model-driven pipeline would.
"""

from typing import Optional

from .agents.crossref_agent import cross_reference
from .agents.gap_agent import chain_reaches_nazi_era, detect_gaps
from .agents.parse_agent import parse_provenance
from .agents.verdict_agent import decide_verdict
from .llm_client import run_budget, spend_cap_exceeded, upstream_refused
from .schema import audit_result, risk_verdict, token_usage
from .scoring import compute_score
from .tools.lookup_tools import enrich_artwork


def run_audit(raw_text: str, budget: Optional[run_budget] = None) -> audit_result:
    """Audit one provenance record end to end.

    Never raises for an expected failure. A blown spend cap or a dead source
    returns a partial result with the reason in `warnings`, so the user always
    sees how far the audit got instead of an error page.
    """
    budget = budget or run_budget()
    result = audit_result()

    if not raw_text or not raw_text.strip():
        result.warnings.append("No provenance text was provided.")
        result.reasoning = "Paste a provenance record to audit it."
        return result

    # Step 1: parse.
    try:
        work, events, parse_usage, parse_warnings = parse_provenance(
            raw_text, budget=budget
        )
    except spend_cap_exceeded as error:
        result.warnings.append(str(error))
        result.reasoning = "The audit stopped at the parsing step to protect the budget."
        return result
    except upstream_refused as error:
        result.warnings.append(str(error))
        result.reasoning = (
            "The record could not be parsed because the provider's content filter "
            "rejected it. No verdict was produced."
        )
        return result

    result.work = work
    result.events = events
    result.usage = result.usage.add(parse_usage)
    result.warnings.extend(parse_warnings)

    # Find the work itself, for the picture and the prominence figure. This is
    # presentation and context only; a failure here must not block the audit.
    work, artwork_warnings = enrich_artwork(work)
    result.work = work
    result.warnings.extend(artwork_warnings)

    if not events:
        result.warnings.append(
            "No ownership events could be read from this text. Check that it is a "
            "provenance record rather than a catalogue description."
        )
        result.verdict = risk_verdict.review
        result.reasoning = (
            "The chain could not be assessed because no ownership events were found."
        )
        result.score = compute_score(
            work, [], detect_gaps([]), [], True, risk_verdict.review
        )
        return result

    # Step 2: gaps, from rules. No tokens spent.
    result.gaps = detect_gaps(events)
    era_relevant = chain_reaches_nazi_era(events)

    # Step 3: cross-reference, from tools. No tokens spent.
    hits, crossref_warnings = cross_reference(events)
    result.crossref_hits = hits
    result.warnings.extend(crossref_warnings)

    # Step 4: verdict.
    try:
        verdict, reasoning, verdict_usage, verdict_warnings = decide_verdict(
            events,
            result.gaps,
            hits,
            crossref_warnings,
            era_relevant=era_relevant,
            budget=budget,
        )
    except spend_cap_exceeded as error:
        result.warnings.append(str(error))
        result.verdict = risk_verdict.review
        result.reasoning = (
            "The per-run spend cap was reached before a verdict could be written. "
            "The gaps listed above were still found by the rule checks."
        )
        result.score = compute_score(
            work, events, result.gaps, hits, era_relevant, risk_verdict.review
        )
        return result
    except upstream_refused as error:
        result.warnings.append(str(error))
        result.verdict = risk_verdict.review
        result.reasoning = (
            "The provider's content filter rejected the verdict request, so no "
            "rating was written. The gaps found by the rule checks still stand, "
            "and they are listed above."
        )
        result.score = compute_score(
            work, events, result.gaps, hits, era_relevant, risk_verdict.review
        )
        return result

    result.verdict = verdict
    result.reasoning = reasoning
    result.usage = result.usage.add(verdict_usage)
    result.warnings.extend(verdict_warnings)

    # Scored last, so the number can be held consistent with the verdict.
    result.score = compute_score(
        work, events, result.gaps, hits, era_relevant, verdict
    )
    return result


def summarise_usage(usage: token_usage) -> str:
    """One line for the app footer, so cost is visible on every run."""
    return (
        f"{usage.call_count} model calls | "
        f"{usage.input_tokens:,} input tokens "
        f"({usage.cached_input_tokens:,} cached) | "
        f"{usage.output_tokens:,} output tokens | "
        f"${usage.cost_usd:.5f} this run"
    )
