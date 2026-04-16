# Human-Readable Summary Design

**Date:** 2026-04-15

## Goal

Add a human-readable daily summary to the CTA Trend Proxy that works in two formats:

- terminal-friendly prose for the local workflow
- shareable Markdown for Slack/email notes

The summary must be deterministic by default and may optionally use a Gemini-based LLM only as a presentation layer. The LLM must never be the source of truth for portfolio facts, validation results, or benchmark math.

## Scope

In scope:

- deterministic summary generation from existing portfolio and validation outputs
- terminal summary rendering
- shareable Markdown rendering
- optional Gemini summary rewrite on top of deterministic facts
- CLI flags to select summary mode and output format
- graceful fallback to deterministic output when Gemini is unavailable

Out of scope for v1:

- SG Trend Indicator scraper implementation
- PDF/email sending integrations
- persistent summary history storage
- multi-provider LLM support beyond a narrow Gemini adapter

## Product Direction

The current report is rich but table-heavy. The new summary layer should answer the first-order trading questions quickly:

- what is the dominant CTA positioning regime right now?
- where is crowding concentrated?
- what changed recently?
- what is at risk of flipping next?
- how much confidence should we place in the proxy given the validation snapshot?

The output should be readable in under 20 seconds and portable into a market note without manual rewriting.

## Recommended Approach

Use one deterministic fact engine with multiple renderers.

1. Build a normalized `summary_facts` payload from existing structured outputs.
2. Render that payload into:
   - concise terminal prose
   - compact shareable Markdown
3. Optionally pass the same fact payload to Gemini for a polished rewrite.

This approach is preferred because it:

- keeps business logic auditable and testable
- avoids divergence between terminal and shareable outputs
- prevents LLM hallucinations from changing numeric conclusions
- allows Gemini to be added without redesigning the summary pipeline

## Architecture

### 1. Fact Builder

Create a new module, likely `summary.py`, centered on a function such as:

```python
build_summary_facts(
    portfolio_result,
    universe,
    flips_by_market,
    signal_validation=None,
    position_validation=None,
    return_validation=None,
    etf_returns_df=None,
    as_of=None,
) -> dict
```

This function will compute a normalized fact object and isolate all summary logic from formatting.

Expected fields include:

- report date
- universe scope and selected market count
- long, short, and flat counts
- crowded long and short lists
- strongest conviction list
- recent flip list
- nearest reversal-risk list
- sector exposure snapshot
- crowding classification
- validation snapshot
- benchmark ETF snapshot
- key caveats such as missing SG validation

### 2. Deterministic Renderers

The same fact object should feed two renderers:

- `render_terminal_summary(facts) -> str`
- `render_markdown_summary(facts) -> str`

Terminal output should be short and high signal, likely 3-5 lines.

Markdown output should be suitable for sharing directly into Slack/email:

- one short headline
- 3-6 bullets
- optional validation bullet
- optional ETF bullet

No tables should be used in Markdown summary mode.

### 3. Optional Gemini Rewrite

Add a separate provider boundary, likely `llm.py`, with a minimal interface such as:

```python
generate_gemini_summary(
    facts: dict,
    output_format: str,
    model: str,
    api_key: str,
) -> str
```

This layer:

- receives only the normalized fact payload
- rewrites or polishes summary prose
- does not calculate weights, correlations, or classifications
- can be disabled without affecting the rest of the program

## Gemini Integration

Gemini must be env-configured and optional.

Suggested configuration:

- `GEMINI_API_KEY`
- `GEMINI_MODEL`

Behavior rules:

- do not hardcode API keys in source or config files
- if the key is missing, invalid, or rate-limited, fall back to deterministic summary
- do not fail the whole report because Gemini is unavailable
- optionally print a short note indicating deterministic fallback

Because a live key was shared in chat, it should be treated as exposed and rotated after implementation is in place.

## CLI Design

Keep the current full report as the default behavior.

Add new flags:

- `--summary`
  - print a human-readable summary above the existing report
- `--summary-only`
  - print only the summary and skip the long report sections
- `--summary-format terminal|markdown`
  - choose renderer output format
- `--llm-summary`
  - request Gemini rewrite

Example usage:

```bash
uv run python main.py --summary
uv run python main.py --summary-only --summary-format markdown
uv run python main.py --summary --summary-format markdown --llm-summary
```

## Content Rules

The summary should speak in trading language but stay bounded by computed facts.

Allowed:

- "CTAs are broadly net long across the selected subset."
- "Crowding is high because all tracked markets are at max long."
- "Euro FX is the nearest flip risk."
- "Validation is mixed: commodities align with COT, financials do not."

Not allowed:

- unsupported causal claims
- forecast language not grounded in computed facts
- statements implying actual CTA holdings rather than proxy estimates

## Error Handling

The summary pipeline should degrade gracefully.

Cases:

- missing SG validation
  - include note in facts and render a brief caveat
- missing ETF data
  - omit ETF bullet rather than error
- Gemini failure
  - log/print a short fallback notice and render deterministic summary
- partial market universe
  - summary should reflect selected subset rather than imply full-universe coverage

## Testing Strategy

Add deterministic tests first.

Test areas:

- fact builder classification logic
- terminal renderer output shape
- Markdown renderer output shape
- summary behavior for subset runs such as `--markets ES GC CL 6E`
- Gemini fallback when key is absent or client errors

The Gemini client should be isolated and mocked in tests.

## Expected Outcome

The system should preserve the current analytical depth while adding a fast top-layer interpretation.

Default users get:

- deterministic summary
- consistent wording
- no API dependency

Advanced users get:

- optional Gemini polish
- same facts, better phrasing
- no risk of the model inventing numbers
