# CTA Proxy Flow And Summary Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add estimated CTA proxy flow outputs and improved explanatory summaries with deterministic facts, optional Gemini rewrite, and shareable/JSON surfaces.

**Architecture:** Build a new flow estimation layer on top of the existing historical weight history, then thread the resulting facts into the report, summary, and JSON output. Keep deterministic calculations as the sole source of truth and let Gemini rewrite only a constrained fact payload.

**Tech Stack:** Python, pandas, unittest, argparse, requests

---

### Task 1: Add failing tests for flow estimation

**Files:**
- Create: `tests/test_flow.py`
- Modify: `config.py`
- Modify: `model/portfolio.py`
- Create: `flow_estimator.py`

**Step 1: Write the failing test**

Add tests that define:

- a simple weight history with known 1-day and 5-day changes
- price and multiplier inputs
- expected USD and contract flow outputs when `assumed_cta_aum_usd` is present
- expected `None` dollar/contract fields when AUM is omitted

**Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_flow -v`

Expected: FAIL because `flow_estimator.py` and related exports do not exist yet.

**Step 3: Write minimal implementation**

Create `flow_estimator.py` with a class or helper that computes flow rows from historical weights, prices, and contract specs.

**Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_flow -v`

Expected: PASS

### Task 2: Add failing tests for summary fact upgrades

**Files:**
- Modify: `tests/test_summary.py`
- Modify: `summary.py`
- Modify: `llm.py`

**Step 1: Write the failing test**

Add tests that require:

- `build_summary_facts(...)` to include `data_used`, `calculation_method`, `conclusion`, `suggestions`, and flow facts
- Markdown summary to mention the data source/mode, method, conclusion, and suggestion blocks
- Gemini prompt to mention assumptions and forbid invention

**Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_summary -v`

Expected: FAIL because the new fact keys and render behavior do not exist yet.

**Step 3: Write minimal implementation**

Extend `summary.py` and `llm.py` to build and render the richer fact model.

**Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_summary -v`

Expected: PASS

### Task 3: Add failing tests for CLI/JSON/report integration

**Files:**
- Modify: `tests/test_report.py`
- Modify: `main.py`
- Modify: `report.py`

**Step 1: Write the failing test**

Add tests that require:

- `--assumed-cta-aum` to parse
- JSON output to include flow payload
- report rendering to include an estimated flow section

**Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_report -v`

Expected: FAIL because the CLI/report do not carry flow data yet.

**Step 3: Write minimal implementation**

Thread the flow estimator into `main.py`, `report.py`, and the JSON payload.

**Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_report -v`

Expected: PASS

### Task 4: Refine deterministic and Gemini summary behavior

**Files:**
- Modify: `summary.py`
- Modify: `llm.py`
- Modify: `README.md`

**Step 1: Implement deterministic sections**

Render concise but explicit sections for:

- data used
- method
- conclusion
- suggestions

**Step 2: Tighten LLM prompt and fallback**

Require the Gemini prompt to preserve assumptions, methodology, caveats, and suggestions. Reject malformed or under-specified output and fall back cleanly.

**Step 3: Update usage docs**

Document the new `--assumed-cta-aum` flag and the meaning of estimated proxy flow.

**Step 4: Run focused tests**

Run:

- `uv run python -m unittest tests.test_flow -v`
- `uv run python -m unittest tests.test_summary -v`
- `uv run python -m unittest tests.test_report -v`

Expected: PASS

### Task 5: Full verification

**Files:**
- Modify: `main.py`
- Modify: `report.py`
- Modify: `summary.py`
- Modify: `llm.py`
- Modify: `config.py`
- Modify: `README.md`
- Create: `flow_estimator.py`
- Create/Modify: tests as needed

**Step 1: Run full test suite**

Run: `uv run python -m unittest discover -s tests -v`

Expected: PASS

**Step 2: Run representative CLI checks**

Run:

- `uv run python main.py --summary-only --summary-format markdown --markets ES GC CL 6E`
- `uv run python main.py --summary-only --summary-format markdown --markets ES GC CL 6E --assumed-cta-aum 100000000000`
- `uv run python main.py --profile daily_note --output json --assumed-cta-aum 100000000000`

Expected:

- shareable summary with explicit method/conclusion/suggestions
- flow estimates present when AUM is supplied
- JSON payload includes structured flow output
