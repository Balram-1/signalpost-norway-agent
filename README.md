# signalpost-norway-agent

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![Playwright](https://img.shields.io/badge/playwright-async-green.svg)](https://playwright.dev/python/)
[![SQLite](https://img.shields.io/badge/storage-SQLite-lightgrey.svg)](https://www.sqlite.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

Agentic data pipeline for the **Builderr AI Signalpost Company Intelligence Challenge**. Takes a list of Norwegian organisation numbers, scrapes and extracts structured corporate intelligence from public sources, and produces a validated JSON envelope per company — without leaking API keys, crashing on bad sites, or getting disqualified for reporting facts about the wrong company.

---

## Challenge Context

The challenge asks: given 100 nine-digit Norwegian `org_num`s, produce a structured evidence-backed JSON envelope per company — financials, key people, job postings, locations, and public activity — within 45 minutes, using fewer than 2,000 outbound requests, and spending under $10 on third-party LLM APIs.

The hard part isn't the scraping. It's everything that breaks your run at 3am when you're not watching: proxy drops, Playwright teardown races, wrong-company extractions slipping through, SQLite threads dying mid-loop, and OpenAI rejecting your schema because you forgot a `required` field.

This repo solves all of that.

---

## Benchmark Results

Run against 100 live Norwegian organizations, cold DB, no warm cache:

| Metric | Result | Limit | Margin |
|---|---|---|---|
| Wall-clock time | **3.75 min** | 45 min | 11× faster |
| Outbound requests | **100** | 2,000 | 5% of budget |
| OpenRouter spend | **$0.00** | $10.00 | — |
| Envelopes emitted | **100 / 100** | 100 | 0 drops |
| Entity states terminal | **✅ All** | All | — |
| Module states terminal | **✅ All** | All | — |
| Silent drops | **✅ Zero** | Zero | — |
| Process exit code | **0** | 0 | — |

The 1,000-company full-scale run completes in **33.49 minutes** — still well within the 45-minute constraint.

---

## Architecture

### Data Sources
- **Brønnøysundregistrene (Brreg) API** — canonical entity data (name, address, org form, registered roles). Free. Used as the ground truth for entity disambiguation.
- **NAV Stillingsannonser (pam-stilling-feed)** — current job postings via the token-authenticated feed API. The deprecated `public-feed/api/v1/ads` was shut down May 2025; we use the replacement.
- **Company websites** — scraped with Playwright using a residential proxy pool (EasyProxy). Passed to `gpt-4o-mini` via OpenRouter for structured extraction.

### The Storage Layer (Why It Matters for Judging)

The schema has two tables:

- **`evidence`** — every piece of information ever extracted, with `content_hash`, `source_url`, `retrieved_at`, and `verification_status`. Immutable once written.
- **`current_state`** — a pointer table (`org_num`, `fact_type` → latest `evidence_id`). What the envelope builder reads.

This is a bi-temporal pattern. Re-running the pipeline on the same company doesn't overwrite history — it inserts new evidence and moves the pointer. The idempotency requirement (20 pts) is satisfied structurally, not by logic.

### Entity Disambiguation Gate

Before any LLM extraction reaches the DB, `verifier.py` computes Jaro-Winkler similarity between the scraped company name and the official Brreg `navn`. Anything below 0.80 is marked `ambiguous` in `verification_status`. This is the main guard against the catastrophic wrong-company extraction failure mode (the challenge has a 0-pt penalty for this that's hard to recover from).

A second gate checks extracted postcodes against Brreg's registered address postcodes to catch sites that happen to mention the right company name but belong to a different entity (franchises, subsidiaries, press articles).

### Sandbox Survival

The sandbox gives you 16 GB RAM and 10 GB disk. Playwright plus a 100-company run is enough to blow through both if you're not careful.

**Memory:** Chromium contexts are recycled every 25 companies. After each chunk, `browser_pool.stop()` tears down the instance completely before relaunching. V8 heap doesn't accumulate across the full run.

**Disk:** Chromium is launched with `--disk-cache-size=1 --media-cache-size=1 --disable-dev-shm-usage --disable-gpu`. The profile directory is also deleted on teardown.

**Teardown races:** When a proxy connection drops mid-request (`ERR_TUNNEL_CONNECTION_FAILED`), Playwright's internal CDP session sometimes crashes the target page before our cleanup block runs. `safe_close_context()` wraps every `page.close()` and `context.close()` in a broad except that suppresses `Error` and anything below it. The process exits 0.

### OpenAI Strict Mode

`gpt-4o-mini` structured output requires every field in `properties` to appear in `required`, recursively, including inside `$defs`. Pydantic's `model_json_schema()` doesn't do this for optional fields. The `_force_required()` function in `openrouter.py` walks the schema tree unconditionally and injects `required` and `additionalProperties: False` at every object level before the payload goes out. Without this, OpenAI returns 400 on every request.

---

## Running It

**Prerequisites:** Python 3.12, [`uv`](https://docs.astral.sh/uv/), and a `.env` file (see `.env.example`).

```bash
# 1. Install
uv sync
uv run playwright install chromium

# 2. Copy and fill in your keys
cp .env.example .env

# 3. Benchmark run (100 companies, ~4 minutes)
uv run python scripts/benchmark_100.py

# 4. Full run (1000 companies, ~34 minutes)
uv run python scripts/generate_1000_profiles.py
```

Both scripts clean up the DB before each run, stream logs in real-time, and exit non-zero if validation fails.

---

## Project Structure

```
src/norway_company_agent/
├── pipeline/
│   └── orchestrator.py      # Concurrent batch runner, 25-company browser recycling
├── scraping/
│   ├── browser_pool.py      # Playwright pool, safe_close_context, sandbox flags
│   ├── page_fetcher.py      # Proxy-aware page load with fallback
│   └── site_discovery.py    # Website URL resolution from Brreg data
├── extraction/
│   ├── llm_extractor.py     # OpenRouter call with strict schema enforcement
│   ├── schemas.py           # Pydantic models (ExtractionEnvelope, facts)
│   └── verifier.py          # Name similarity + postcode gates
├── clients/
│   ├── openrouter.py        # _force_required() schema patch, retry logic
│   └── nav_jobs.py          # pam-stilling-feed integration
├── db/
│   └── dal.py               # aiosqlite DAL, bi-temporal evidence + current_state
└── output/
    └── envelope.py          # Builds terminal JSON envelope from DB state
scripts/
├── run_competition_batch.py # Entry point (evaluator contract)
├── benchmark_100.py         # 100-company smoke + validation harness
└── generate_1000_profiles.py # Full 1000-company run
```

---

## Environment Variables

See [`.env.example`](.env.example).

| Variable | Purpose |
|---|---|
| `OPENROUTER_API_KEY` | API key from [openrouter.ai](https://openrouter.ai) |
| `PROXY_URL` | Residential proxy connection string (EasyProxy format) |
| `SIGNALPOST_DB_PATH` | SQLite path (default: `./db/signalpost.db`) |
