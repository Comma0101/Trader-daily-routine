# Human-Readable Summary Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add deterministic terminal and Markdown summaries to the CTA Trend Proxy, with optional Gemini-powered prose rewrite and safe fallback to deterministic output.

**Architecture:** Introduce a new summary fact-builder module that computes normalized summary facts from existing portfolio and validation results. Keep rendering separate from fact computation, then add a narrow Gemini adapter that rewrites already-computed facts without owning any business logic.

**Tech Stack:** Python 3.12, stdlib `unittest`, pandas, existing project modules, Google Gemini REST API via `requests`

---

### Task 1: Add Summary Regression Tests

**Files:**
- Create: `tests/test_summary.py`
- Modify: `tests/test_report.py`

**Step 1: Write the failing test**

Add tests for:

- fact builder counts long, short, and flat markets correctly
- fact builder identifies strongest convictions and nearest flip risks
- terminal renderer returns short prose
- Markdown renderer returns shareable bullet output
- Gemini fallback returns deterministic output when config is missing

Example skeleton:

```python
def test_build_summary_facts_counts_position_buckets():
    facts = build_summary_facts(...)
    assert facts["position_counts"] == {"long": 2, "short": 1, "flat": 1}
```

**Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_summary -v`
Expected: FAIL because `summary.py` does not exist yet.

**Step 3: Write minimal implementation**

Create only enough summary scaffolding to satisfy imports and fail on assertions instead of import errors.

**Step 4: Run test to verify it passes or fails for the right reason**

Run: `uv run python -m unittest tests.test_summary -v`
Expected: assertion failures tied to missing behavior, not missing modules.

**Step 5: Commit**

```bash
git add tests/test_summary.py tests/test_report.py
git commit -m "test: add summary feature regressions"
```

### Task 2: Implement Deterministic Summary Fact Builder

**Files:**
- Create: `summary.py`
- Modify: `report.py`

**Step 1: Write the failing test**

Add focused tests asserting:

- `build_summary_facts()` includes report date, selected universe size, crowding classification, and validation caveats
- ETF snapshot is omitted cleanly when benchmark data is unavailable

**Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_summary -v`
Expected: FAIL on missing fact fields.

**Step 3: Write minimal implementation**

Implement:

- `build_summary_facts(...)`
- helper functions for:
  - position counts
  - strongest convictions
  - recent flips
  - nearest reversal risks
  - validation snapshot extraction
  - ETF snapshot extraction

Keep the output dict normalized and renderer-agnostic.

**Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_summary -v`
Expected: PASS for fact-builder tests.

**Step 5: Commit**

```bash
git add summary.py tests/test_summary.py report.py
git commit -m "feat: add deterministic summary fact builder"
```

### Task 3: Implement Terminal And Markdown Renderers

**Files:**
- Modify: `summary.py`
- Modify: `report.py`
- Modify: `main.py`

**Step 1: Write the failing test**

Add tests asserting:

- terminal renderer returns concise multi-line prose
- Markdown renderer returns headline plus bullets
- `--summary-only --summary-format markdown` prints only shareable summary content

Example skeleton:

```python
def test_render_markdown_summary_returns_headline_and_bullets():
    output = render_markdown_summary(facts)
    assert output.startswith("## ")
    assert "- " in output
```

**Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_summary tests.test_report -v`
Expected: FAIL because renderer functions and CLI wiring are incomplete.

**Step 3: Write minimal implementation**

Implement:

- `render_terminal_summary(facts)`
- `render_markdown_summary(facts)`
- CLI flags:
  - `--summary`
  - `--summary-only`
  - `--summary-format`
- report integration:
  - summary above full report when `--summary`
  - summary-only output path when requested

**Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_summary tests.test_report -v`
Expected: PASS for renderer and CLI summary tests.

**Step 5: Commit**

```bash
git add summary.py report.py main.py tests/test_summary.py tests/test_report.py
git commit -m "feat: add deterministic terminal and markdown summaries"
```

### Task 4: Add Gemini Adapter With Deterministic Fallback

**Files:**
- Create: `llm.py`
- Modify: `summary.py`
- Modify: `main.py`
- Test: `tests/test_summary.py`

**Step 1: Write the failing test**

Add tests for:

- missing `GEMINI_API_KEY` falls back to deterministic output
- provider exception falls back to deterministic output
- Gemini request builder uses env-configured model

Example skeleton:

```python
def test_gemini_summary_falls_back_when_key_missing():
    text = maybe_generate_llm_summary(facts, use_llm=True, ...)
    assert "CTAs are" in text
```

**Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_summary -v`
Expected: FAIL on missing Gemini adapter behavior.

**Step 3: Write minimal implementation**

Implement:

- `llm.py` with a small Gemini REST client using `requests`
- env lookups for:
  - `GEMINI_API_KEY`
  - `GEMINI_MODEL`
- optional CLI flag:
  - `--llm-summary`
- safe fallback:
  - if config missing or request fails, use deterministic renderer

Do not store credentials on disk.

**Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_summary -v`
Expected: PASS for fallback and config tests.

**Step 5: Commit**

```bash
git add llm.py summary.py main.py tests/test_summary.py
git commit -m "feat: add optional gemini summary rewrite"
```

### Task 5: Verify End-To-End Summary Modes

**Files:**
- Modify: `README.md`

**Step 1: Write the failing test**

Add or extend tests to assert CLI output shape for:

- `--summary`
- `--summary-only`
- `--summary-only --summary-format markdown`

**Step 2: Run test to verify it fails**

Run: `uv run python -m unittest discover -s tests -v`
Expected: FAIL if README examples or CLI behavior are out of sync.

**Step 3: Write minimal implementation**

Update README with:

- summary commands
- deterministic vs Gemini behavior
- env var setup instructions
- note that Gemini is optional and summary falls back safely

**Step 4: Run test to verify it passes**

Run: `uv run python -m unittest discover -s tests -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add README.md main.py tests/test_summary.py tests/test_report.py summary.py llm.py
git commit -m "docs: document summary and gemini usage"
```

### Task 6: Manual Verification

**Files:**
- None required unless verification reveals an issue.

**Step 1: Run terminal summary mode**

Run: `uv run python main.py --summary --quick`
Expected: concise prose summary above the existing full report.

**Step 2: Run Markdown summary-only mode**

Run: `uv run python main.py --summary-only --summary-format markdown --markets ES GC CL 6E`
Expected: shareable Markdown with headline and bullets, no long tables.

**Step 3: Run Gemini fallback mode without env**

Run: `uv run python main.py --summary-only --summary-format markdown --llm-summary --quick`
Expected: deterministic summary plus a short fallback note, no crash.

**Step 4: Run Gemini mode with env configured**

Run:

```bash
export GEMINI_API_KEY='...'
export GEMINI_MODEL='gemini-3-pro-preview'
uv run python main.py --summary-only --summary-format markdown --llm-summary --quick
```

Expected: polished Markdown prose generated from deterministic facts.

**Step 5: Commit**

```bash
git add README.md main.py report.py summary.py llm.py tests/test_summary.py tests/test_report.py
git commit -m "feat: add human-readable daily summaries"
```
