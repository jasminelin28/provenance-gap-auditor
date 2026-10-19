"""A metered wrapper around the course Portkey/OpenAI endpoint.

Every call is logged with its measured token usage and computed cost. This is
what the report's tokenomics section is built from, and it is also the
enforcement point for the per-run spend cap.
"""

import csv
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from portkey_ai import Portkey

from . import config
from .schema import token_usage

usage_log_path = config.repo_root / "data" / "usage_log.csv"
_log_lock = threading.Lock()
_client: Optional[Portkey] = None


class spend_cap_exceeded(RuntimeError):
    """Raised when a single run would cost more than the configured ceiling."""


class upstream_refused(RuntimeError):
    """Raised when the provider's own content filter rejects the request.

    The course endpoint sits behind Azure OpenAI, which screens prompts before
    they reach the model. A provenance record quoting wartime material, or one
    carrying an injected instruction, can trip that screen. We surface it as a
    clear message rather than a stack trace.
    """


def get_client() -> Portkey:
    global _client
    if _client is None:
        config.load_environment()
        api_key = os.environ.get("PORTKEY_API_KEY")
        if not api_key:
            raise RuntimeError("PORTKEY_API_KEY is not set.")
        _client = Portkey(api_key=api_key, provider="openai")
    return _client


def compute_cost(input_tokens: int, cached_input_tokens: int, output_tokens: int) -> float:
    """Price a call. Cached input bills at the lower cached rate."""
    fresh_input = max(input_tokens - cached_input_tokens, 0)
    cost = (
        fresh_input / 1_000_000 * config.price_per_million_input
        + cached_input_tokens / 1_000_000 * config.price_per_million_cached_input
        + output_tokens / 1_000_000 * config.price_per_million_output
    )
    return round(cost, 8)


def _record_usage(agent_name: str, usage: token_usage, elapsed_seconds: float) -> None:
    """Append one row to the usage log used for the tokenomics measurements."""
    usage_log_path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "agent": agent_name,
        "model": config.model_name,
        "input_tokens": usage.input_tokens,
        "cached_input_tokens": usage.cached_input_tokens,
        "output_tokens": usage.output_tokens,
        "cost_usd": f"{usage.cost_usd:.8f}",
        "elapsed_seconds": f"{elapsed_seconds:.2f}",
    }
    with _log_lock:
        is_new = not usage_log_path.exists()
        with usage_log_path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(row))
            if is_new:
                writer.writeheader()
            writer.writerow(row)


class run_budget:
    """Tracks spend across the several agent calls that make up one audit run."""

    def __init__(self, ceiling_usd: Optional[float] = None) -> None:
        self.ceiling_usd = ceiling_usd or config.max_cost_per_run_usd
        self.total = token_usage()

    def charge(self, usage: token_usage) -> None:
        self.total = self.total.add(usage)
        if self.total.cost_usd > self.ceiling_usd:
            raise spend_cap_exceeded(
                f"This run reached ${self.total.cost_usd:.4f}, above the "
                f"${self.ceiling_usd:.4f} per-run ceiling. Stopping before further spend."
            )


def call_model(
    agent_name: str,
    messages: List[Dict[str, str]],
    budget: Optional[run_budget] = None,
    expect_json: bool = True,
) -> Any:
    """Call the model once, meter it, and return parsed JSON (or raw text).

    `agent_name` is recorded in the usage log so the report can break cost down
    by agent rather than only per run.
    """
    client = get_client()
    started = time.monotonic()
    request: Dict[str, Any] = {"model": config.model_name, "messages": messages}
    if expect_json:
        request["response_format"] = {"type": "json_object"}

    try:
        response = client.chat.completions.create(**request)
    except Exception as error:
        detail = str(error)
        if "content_filter" in detail or "content management policy" in detail:
            raise upstream_refused(
                "The model provider's content filter rejected this text before it "
                "reached the model, so this step could not run. This happens with "
                "some wartime material and with text carrying injected "
                "instructions. Try the record without any non-provenance text."
            ) from error
        raise
    elapsed = time.monotonic() - started

    raw_usage = response.usage
    input_tokens = getattr(raw_usage, "prompt_tokens", 0) or 0
    output_tokens = getattr(raw_usage, "completion_tokens", 0) or 0
    details = getattr(raw_usage, "prompt_tokens_details", None)
    cached = 0
    if details is not None:
        cached = (getattr(details, "cached_tokens", 0) or 0) if not isinstance(details, dict) \
            else (details.get("cached_tokens", 0) or 0)

    usage = token_usage(
        input_tokens=input_tokens,
        cached_input_tokens=cached,
        output_tokens=output_tokens,
        cost_usd=compute_cost(input_tokens, cached, output_tokens),
        call_count=1,
    )
    _record_usage(agent_name, usage, elapsed)
    if budget is not None:
        budget.charge(usage)

    content = response.choices[0].message.content or ""
    if not expect_json:
        return content, usage
    try:
        return json.loads(content), usage
    except json.JSONDecodeError:
        # The model occasionally wraps JSON in prose or a code fence.
        start, end = content.find("{"), content.rfind("}")
        if start != -1 and end > start:
            return json.loads(content[start : end + 1]), usage
        raise
