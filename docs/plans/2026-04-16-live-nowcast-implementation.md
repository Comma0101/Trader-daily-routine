# Live Nowcast Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `--live` and `--refresh` modes so the CTA report can use an intraday "today" price nowcast while preserving daily-history backtests and deterministic fallback behavior.

**Architecture:** Keep daily bars as the official history and append a synthetic live point only for current signal computation. Add a cache bypass flag for same-day stale CSVs, then thread live metadata through `main.py`, summaries, and the report so the output makes clear when today's nowcast is being used.

**Tech Stack:** Python 3.12, `unittest`, `pandas`, `yfinance`, existing CLI/report modules

---

### Task 1: Add Red Tests For Live Overlay And Cache Refresh

**Files:**
- Create: `tests/test_futures.py`
- Modify: `tests/test_report.py`

**Step 1: Write the failing test**

Add tests for:
- live overlay appends a new adjusted point using the intraday return vs prior raw close
- `refresh=True` bypasses same-day CSV cache
- `main.py --summary-only --summary-format markdown --live --quick ...` passes a live timestamp into summary facts or report context

**Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_futures tests.test_report -v`
Expected: FAIL on missing live helpers / CLI flags.

**Step 3: Write minimal implementation**

Implement only enough scaffolding in `data/futures.py` and `main.py` for the tests to fail on behavior instead of missing symbols.

**Step 4: Run test to verify red is correct**

Run: `uv run python -m unittest tests.test_futures tests.test_report -v`
Expected: still FAIL, but now for the intended behavior.

### Task 2: Implement FuturesData Live Overlay And Refresh

**Files:**
- Modify: `data/futures.py`
- Modify: `config.py`

**Step 1: Write the failing test**

Add focused tests for:
- `_fetch_one(..., refresh=True)` ignores same-day cache
- live price fetch returns the most recent intraday close and timestamp
- adjusted series appends a synthetic live point computed from adjusted_yesterday * (live_raw / prior_raw_close)

**Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_futures -v`
Expected: FAIL on missing live nowcast behavior.

**Step 3: Write minimal implementation**

Implement:
- new config knobs in `DATA_PARAMS`
- optional `refresh` and `live` fetch behavior
- intraday fetch helper in `FuturesData`
- price-series overlay logic that preserves historical daily bars

**Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_futures -v`
Expected: PASS.

### Task 3: Wire Live Mode Through CLI, Summary, And Report

**Files:**
- Modify: `main.py`
- Modify: `summary.py`
- Modify: `report.py`
- Modify: `tests/test_report.py`

**Step 1: Write the failing test**

Add tests asserting:
- `--live` and `--refresh` are accepted by the CLI
- summary/report use today’s live timestamp when available
- output includes a clear live-nowcast context line

**Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_report -v`
Expected: FAIL on missing CLI/report wiring.

**Step 3: Write minimal implementation**

Implement:
- CLI flags `--live` and `--refresh`
- live metadata threading from `FuturesData` to `main.py`
- summary/report context line such as official close date + live as-of timestamp

**Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_report -v`
Expected: PASS.

### Task 4: Update Documentation And Verify End To End

**Files:**
- Modify: `README.md`

**Step 1: Update docs**

Document:
- `--refresh`
- `--live`
- difference between official close and live nowcast
- current limitations of yfinance intraday data

**Step 2: Run full verification**

Run:
- `uv run python -m unittest discover -s tests -v`
- `uv run python main.py --summary-only --summary-format markdown --live --quick --markets ES GC CL 6E`

Expected:
- test suite passes
- live command runs successfully and surfaces live context when available
