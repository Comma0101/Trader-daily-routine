# CTA Capital State And LLM Note Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add estimated CTA capital-state outputs and upgrade the Gemini Markdown summary into a polished professional note grounded in deterministic facts.

**Architecture:** Add a small capital estimator that converts current portfolio exposure into deployed-risk and headroom estimates using either a user AUM assumption or the SG tracked-fund reference basket. Extend the summary fact model with higher-level interpretation fields, then update the Gemini prompt and format validation so the model writes a professional note instead of a rigid four-label rewrite.

**Tech Stack:** Python, pandas, unittest, argparse, requests

---

### Task 1: Add failing tests for capital-state estimation

**Files:**
- Create: `tests/test_capital.py`
- Create: `capital_estimator.py`
- Modify: `config.py`

**Step 1: Write the failing test**

Add tests that require:

- reference basket AUM to be derived from `SG_TREND_INDEX_FUNDS`
- deployed gross/net risk and remaining gross headroom to be computed from gross leverage, net exposure, and max leverage
- explicit `--assumed-cta-aum` inputs to override the reference basket

**Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_capital -v`

Expected: FAIL because `capital_estimator.py` does not exist yet.

**Step 3: Write minimal implementation**

Create `capital_estimator.py` and expose a capital estimate helper.

**Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_capital -v`

Expected: PASS

### Task 2: Add failing tests for summary fact and LLM note upgrades

**Files:**
- Modify: `tests/test_summary.py`
- Modify: `summary.py`
- Modify: `llm.py`

**Step 1: Write the failing test**

Add tests that require:

- `build_summary_facts(...)` to include `capital`, `thesis`, `drivers`, `interpretation`, `why_now`, `confidence`, and `actions`
- Gemini prompt text to require explanation of what the data means and why it matters
- Markdown LLM output validation to require headline, paragraphs, and labeled bullets

**Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_summary -v`

Expected: FAIL because the richer facts and note-format validation do not exist yet.

**Step 3: Write minimal implementation**

Extend `summary.py` and `llm.py` to support the richer fact model and note prompt.

**Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_summary -v`

Expected: PASS

### Task 3: Add failing tests for CLI, JSON, and report integration

**Files:**
- Modify: `tests/test_report.py`
- Modify: `main.py`
- Modify: `report.py`

**Step 1: Write the failing test**

Add tests that require:

- JSON output to include `capital_estimate`
- the full report to print an estimated capital-state section
- the summary fact builder to receive `capital_estimate`

**Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_report -v`

Expected: FAIL because the CLI and report do not thread capital-state data yet.

**Step 3: Write minimal implementation**

Wire capital estimates through `main.py`, `report.py`, and `summary.py`.

**Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_report -v`

Expected: PASS

### Task 4: Update docs and final verification

**Files:**
- Modify: `README.md`
- Modify: `agent_instructions.json`
- Modify: `summary.py`
- Modify: `llm.py`
- Create: `capital_estimator.py`
- Modify/Create: tests as needed

**Step 1: Update docs**

Document:

- capital-state terminology
- the difference between risk deployed and cash spent
- the improved professional LLM note format

**Step 2: Run full tests**

Run: `uv run python -m unittest discover -s tests -v`

Expected: PASS

**Step 3: Run representative commands**

Run:

- `uv run python main.py --summary-only --summary-format markdown --quick --markets ES GC CL 6E --llm-summary`
- `uv run python main.py --quick --markets ES GC CL 6E`
- `uv run python main.py --profile daily_note --output json`

Expected:

- polished deterministic or LLM note in the new structure
- capital-state section in the full report
- `capital_estimate` present in JSON output
