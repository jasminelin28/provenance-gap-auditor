"""Configuration and credential loading for the provenance gap auditor.

The teaching staff clone every repo into a shared folder whose `.env` sits one
level ABOVE the repo. So we look in the repo folder first, then the parent.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

repo_root = Path(__file__).resolve().parent.parent


def load_environment() -> str:
    """Load .env from the repo folder, then the folder above it.

    Returns a short description of where the key was found, for display in the
    app footer and for troubleshooting a fresh clone.
    """
    candidates = [repo_root / ".env", repo_root.parent / ".env"]
    for candidate in candidates:
        if candidate.is_file():
            load_dotenv(candidate, override=False)
            if os.environ.get("PORTKEY_API_KEY") or os.environ.get("OPENAI_API_KEY"):
                return str(candidate)
    # Fall back to real environment variables (how the hosted deployment works).
    if os.environ.get("PORTKEY_API_KEY") or os.environ.get("OPENAI_API_KEY"):
        return "process environment"
    searched = " and ".join(str(c) for c in candidates)
    raise RuntimeError(
        f"No PORTKEY_API_KEY or OPENAI_API_KEY found. Looked for a .env in {searched}. "
        "Copy .env.example to .env and fill in your key."
    )


# Model. The course key serves this under two aliases; the spec names this one.
model_name = "gpt-6-luna"

# Published per-million-token prices used for the cost estimates shown in the
# app and the report. Update here if the course rate card changes.
price_per_million_input = 0.25
price_per_million_cached_input = 0.025
price_per_million_output = 2.00

# Spend and runaway protection. These are the guardrails described in the
# report's safety section.
max_input_characters = 20000
max_agent_steps = 8
max_cost_per_run_usd = 0.05
max_runs_per_session = 25

# Where the SQLite database of red-flag dealers and cached Lostart records lives.
database_path = repo_root / "data" / "provenance_auditor.sqlite"

# Sent to public SPARQL endpoints; Wikidata requires a descriptive agent.
http_user_agent = "provenance-gap-auditor/0.1 (MGT409 course project)"
http_timeout_seconds = 25
