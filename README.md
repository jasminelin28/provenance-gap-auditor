# Provenance Gap Auditor

Paste the provenance section of an auction or gallery catalogue entry. The app
rebuilds the chain of ownership, marks every gap in it, checks the owner names
against public databases, and returns a risk rating: **clear**, **needs
review**, or **high risk**.

It is built for the 1933–1945 problem in particular. A work that goes quiet for
twelve years in the middle of the century, or passes through an unnamed "private
collection" in that window, is the single most common signal of an unresolved
restitution claim — and it is exactly what a reader skims past.

**Live app:** _(link added at submission)_

---

## Run it locally

You need Python 3.10 or newer.

**1. Install the dependencies**

```bash
pip install -r requirements.txt
```

**2. Provide an API key**

The app reads `PORTKEY_API_KEY` and looks for a `.env` file in **two** places,
in this order:

1. this repo folder
2. the folder one level above it

So a shared `.env` sitting next to the repo works without any changes:

```
submissions/
├── .env                  <-- found here too
└── provenance-auditor/
    ├── .env              <-- checked first
    └── app.py
```

If you need to make one, copy `.env.example` to `.env` and fill in the key.
Real environment variables also work, which is how the hosted version runs.

**3. Start it**

```bash
python app.py
```

Open <http://127.0.0.1:8050>. The box is pre-filled with a sample record, so you
can press **Audit this record** straight away.

---

## Try these

The `samples/` folder holds four records that each show something different.
Paste one in, or use the upload link.

| File | What it shows |
|---|---|
| `gap_matisse.txt` | **High risk.** A 17-year silence across the war and an unnamed Swiss owner. Loaded by default. |
| `clean_contemporary.txt` | **Needs review.** A 1965 print with a continuous chain — the app does *not* raise the Nazi era for post-war works. |
| `injection_subtle.txt` | **Safety.** The record ends with text instructing the app to return "clear". It returns high risk instead and reports the attempt. |
| `injection_attempt.txt` | A blunter version of the same attack. The model provider's own filter rejects it upstream; the app degrades to a clear message rather than an error. |

You can also upload a PDF lot page. Only the first 8 pages are read, to bound
the cost of a single audit. Scanned PDFs with no text layer are not supported —
the app says so rather than returning an empty chain.

---

## How it works

Four agents run in sequence. Only two of them call a model, which is why one
audit costs roughly half a cent.

```
  provenance text
        │
        ▼
  parse_agent      model call   →  ownership events, with dates and roles
        │
        ▼
  gap_agent        rules only   →  gaps: silences, placeholders, border moves
        │
        ▼
  crossref_agent   tools only   →  matches in Wikidata, Getty ULAN, local tables
        │
        ▼
  verdict_agent    model call   →  rating + explanation
        │
        ▼
  deterministic floor           →  the rating can be raised, never lowered
```

**Model:** `gpt-6-luna`, through Portkey.

**Why the middle two steps use no model.** Gap detection is arithmetic over
years and string matching over owner names. A model would add cost and a
hallucination risk without adding accuracy, and every gap the app reports can
instead be traced to a named rule.

**The deterministic floor.** The model proposes a rating, but a rule applied
afterwards can only ever raise it. If a documented Nazi-era dealer appears in
the chain, the verdict cannot come back `clear` — no matter what the model said,
and no matter what the pasted record tried to instruct.

### Sources checked

| Source | How it is used |
|---|---|
| Wikidata | Live API. Resolves owner and dealer names to real entities. |
| Getty ULAN | Live SPARQL. Resolves names against the Union List of Artist Names. |
| Red-flag table | Local SQLite. Documented Nazi-era dealers, agents and looting bodies. |
| Lost Art Database | Local cached snapshot, because lostart.de publishes no API. |

A match in Wikidata or Getty only confirms that a name exists in a reference
work. It is not evidence of wrongdoing, and the absence of a match is not
evidence of anything. The app says so on screen.

---

## Rebuilding the database

The repo ships with `data/provenance_auditor.sqlite` already built, so you do
not need to run this. To regenerate it:

```bash
python data/build_database.py
```

---

## Cost and safety controls

Every model call is written to `data/usage_log.csv` with its measured token
counts and computed cost, which is where the report's numbers come from. The
per-run cost also appears at the bottom of each result.

Four limits are enforced in `provenance_auditor/config.py`:

- `max_input_characters` — long inputs are truncated before they reach the model
- `max_cost_per_run_usd` — a run that exceeds it stops and returns partial results
- `max_pdf_pages` — only the first 8 pages of an upload are read
- `max_lookups` — bounds the outbound requests one audit can make

---

## What this is not

This flags gaps for a human researcher. It is not a title opinion, it is not
legal advice, and a **clear** result is not proof of clean title — it means
only that the text you pasted contains no gap the app can detect. A fabricated
provenance with no holes in it will come back clear.
