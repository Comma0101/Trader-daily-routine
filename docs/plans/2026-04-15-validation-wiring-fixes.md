# Validation Wiring Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the benchmark math and COT metadata bugs, then wire the existing validation components into the daily CLI report.

**Architecture:** Keep the current module split. Add narrow test coverage first, then make the smallest production changes needed in `config.py`, `report.py`, `model/portfolio.py`, and `main.py`. Use a lightweight historical return series from the existing signal and vol engines so return validation can run without adding a separate backtest subsystem.

**Tech Stack:** Python 3.12, stdlib `unittest`, pandas, numpy, yfinance, cot-reports

---

### Task 1: Regression Tests

**Files:**
- Create: `tests/test_config.py`
- Create: `tests/test_portfolio.py`
- Create: `tests/test_report.py`

**Step 1: Write the failing tests**

- Add a config regression test asserting `NQ` and `YM` use the correct CFTC codes.
- Add a report test asserting ETF YTD uses only the current calendar year and compounds returns.
- Add a portfolio/history test asserting historical model returns use lagged weights.
- Add a report-format test asserting validation sections render when results are supplied.

**Step 2: Run test to verify it fails**

Run: `uv run python -m unittest discover -s tests -v`
Expected: failures for missing helper APIs and incorrect config values.

### Task 2: Fix Metadata And ETF Summary Math

**Files:**
- Modify: `config.py`
- Modify: `report.py`

**Step 1: Correct the COT codes**

- Update `FUTURES_UNIVERSE["NQ"]["cot_code"]` to the CME Nasdaq mini contract code.
- Update `FUTURES_UNIVERSE["YM"]["cot_code"]` to the CBOT DJIA mini contract code.

**Step 2: Refactor ETF summary logic**

- Extract ETF summary calculation into a small helper in `report.py`.
- Compute 5D, 20D, and YTD as compounded returns.
- Filter YTD to the report year instead of summing the full fetched history.

**Step 3: Run targeted tests**

Run: `uv run python -m unittest tests.test_config tests.test_report -v`
Expected: green for the metadata and ETF summary regressions.

### Task 3: Historical Model Returns And Validation Output

**Files:**
- Modify: `model/portfolio.py`
- Modify: `main.py`
- Modify: `report.py`

**Step 1: Add historical model return generation**

- Add a method that derives daily signal history and daily vol-scalar history.
- Build per-day weights with the existing sector-budget logic.
- Shift weights by one day before applying returns to avoid lookahead bias.

**Step 2: Wire validation into CLI**

- Call the signal, position, and return validators from `main.py`.
- Pass validation results into the report layer.
- Print a compact validation section, including stub/no-data notes when a source is unavailable.

**Step 3: Run targeted tests**

Run: `uv run python -m unittest tests.test_portfolio tests.test_report -v`
Expected: green for the historical-return and report-rendering behavior.

### Task 4: End-To-End Verification

**Files:**
- Modify: `README.md` only if command output or feature description needs to be corrected.

**Step 1: Run the full test suite**

Run: `uv run python -m unittest discover -s tests -v`
Expected: all tests pass.

**Step 2: Run the CLI**

Run: `uv run python main.py`
Expected: report prints corrected ETF YTD values and a validation summary section.
