# CTA Trend Proxy

Daily CTA (Commodity Trading Advisor) positioning tracker. Estimates where the largest systematic trend-following funds are positioned across 21 futures markets using signal replication.

## Quick Start

```bash
uv run python main.py              # full report, all 21 markets
uv run python main.py --quick      # skip benchmark ETF fetch
uv run python main.py --markets ES GC CL ZN 6E   # specific markets
uv run python main.py --profile daily_note
uv run python main.py --profile daily_note --output json
uv run python main.py --summary-only --summary-format markdown --markets ES GC CL 6E --assumed-cta-aum 100000000000
uv run python main.py --summary    # add human-readable summary above the report
uv run python main.py --summary-only --summary-format markdown --markets ES GC CL 6E
uv run python main.py --live --refresh --summary-only --summary-format markdown --markets ES GC CL 6E
uv run python main.py --summary --llm-summary    # optional Gemini rewrite if GEMINI_API_KEY is set
uv run python main.py -v           # verbose/debug logging
```

## Agent Mode

For agents, start with [agent_instructions.json](/home/comma/Documents/Trader-daily-routine/agent_instructions.json:1). It describes the repo entrypoint, the recommended profile, and the machine-readable JSON command.

```bash
uv run python main.py --profile daily_note
uv run python main.py --profile daily_note --output json
```

- `--profile daily_note` expands to the live, refreshed, summary-only Markdown workflow
- `--output json` emits a machine-readable payload with summary text, summary facts, report context, portfolio, proxy flow, capital state, flips, and validation

## Summary Modes

The report now supports deterministic human-readable summaries in terminal and shareable Markdown formats. Summaries explicitly state the data used, how the tracker calculated the estimate, the main conclusion, and suggested next actions. When `--llm-summary` is enabled, the Markdown path aims for a more polished professional note.

```bash
uv run python main.py --summary
uv run python main.py --summary-only
uv run python main.py --summary-only --summary-format markdown
uv run python main.py --summary --summary-format markdown
```

- `--summary` prints a short summary above the full report
- `--summary-only` prints only the summary text
- `--summary-format markdown` emits a shareable Markdown headline plus bullets for Slack or email
- `--assumed-cta-aum` converts relative proxy flow changes into estimated dollar and contract flow using your chosen aggregate CTA AUM assumption
- deterministic summaries are the default and remain the fallback path even when the LLM option is enabled
- `--live` overlays the most recent intraday price as a nowcast for current signals and watch lists
- `--refresh` bypasses the same-day CSV cache before rebuilding prices

## Proxy Flow Mode

The tracker can now estimate daily and 5-trading-day CTA proxy flow from changes in model target weights.

```bash
uv run python main.py --quick --markets ES GC CL 6E
uv run python main.py --quick --markets ES GC CL 6E --assumed-cta-aum 100000000000
uv run python main.py --profile daily_note --output json --assumed-cta-aum 100000000000
```

- without `--assumed-cta-aum`, the tracker reports relative 1D and 5D flow changes only
- with `--assumed-cta-aum`, it also reports estimated USD notional flow and estimated contract flow
- this is an **estimated CTA proxy flow**, not observed CTA trading
- the dollar estimate is calculated from target weight change multiplied by the supplied CTA AUM assumption
- contract estimates are calculated from estimated USD flow divided by the latest price times the contract multiplier

## Optional Gemini Rewrite

If you want the summary phrased more naturally, you can enable the Gemini rewrite layer. The model only rewrites already-computed facts; it does not calculate signals or validation itself.

```bash
export GEMINI_API_KEY=...
export GEMINI_MODEL=gemini-3-pro-preview   # optional override
export GEMINI_FALLBACK_MODEL=gemini-2.5-flash   # optional override for markdown note fallback
uv run python main.py --summary --llm-summary
uv run python main.py --summary-only --summary-format markdown --llm-summary
```

- if `GEMINI_API_KEY` is missing, invalid, or Gemini errors, the program falls back to deterministic summary output
- the markdown note path first tries the configured Gemini model, then retries with `GEMINI_FALLBACK_MODEL` if the first note is malformed
- the Markdown Gemini path aims for a professional daily CTA note: headline, short narrative paragraphs, then bullets for flows, validation, risks, and actions
- do not hardcode API keys in the repo

## Capital State

The tracker also estimates overall CTA capital state from the current portfolio.

```bash
uv run python main.py --quick --markets ES GC CL 6E
uv run python main.py --quick --markets ES GC CL 6E --assumed-cta-aum 100000000000
uv run python main.py --profile daily_note --output json
```

- the report prints `ESTIMATED CTA CAPITAL STATE`
- this includes estimated gross risk deployed, net risk deployed, and remaining gross headroom
- these figures represent **risk deployed**, not cash spent
- if you do not pass `--assumed-cta-aum`, the capital section uses the SG tracked-fund basket as a clearly labeled reference basis
- if you do pass `--assumed-cta-aum`, that assumption overrides the reference basket for capital and proxy-flow calculations

## Live Nowcast

If you want the report to reflect today’s session instead of the latest completed daily bar, use:

```bash
uv run python main.py --live --refresh
uv run python main.py --live --refresh --summary-only --summary-format markdown --markets ES GC CL 6E
```

- daily history remains the official signal history and still drives return-validation backtests
- `--live` only affects current signal state, flip detection, watch lists, and summary/report timestamping
- the report will show whether it is using a `LIVE nowcast` or `DAILY close`
- yfinance intraday data is still a best-effort source and may lag or miss some contracts

## What It Does

1. **Trend Signal Engine** — Two-speed MA crossover (20d/120d) matching SG Trend Indicator methodology
2. **Vol-Targeted Sizing** — 3-month EWMA volatility, 15% vol target per position
3. **Risk Parity Portfolio** — Equal risk budget across 6 sectors (Equity, Fixed Income, Energy, Metals, Agriculture, FX)
4. **CTA Proxy Flow** — 1D and 5D weight changes, optional dollar/contract estimates from an explicit CTA AUM assumption
5. **Capital State** — Estimated gross risk deployed, net risk deployed, and remaining gross headroom
6. **Daily Report** — Positioning, signal flips, crowding risk, reversal watch list, benchmark ETF comparison

## Markets Tracked (21)

| Sector | Markets |
|--------|---------|
| Equity Index | S&P 500, Nasdaq 100, Dow Jones, Russell 2000 |
| Fixed Income | 30Y T-Bond, 10Y T-Note, 5Y T-Note |
| Energy | Crude Oil WTI, Natural Gas, RBOB Gasoline |
| Metals | Gold, Silver, Copper |
| Agriculture | Corn, Soybeans, Wheat |
| FX | EUR, JPY, GBP, AUD, Dollar Index |

## Validation Layers

| Layer | Source | What It Validates |
|-------|--------|-------------------|
| Signal | SG Trend Indicator | Per-market signal direction (stub — needs scraper or manual data) |
| Position | CFTC COT (TFF + Disagg) | Directional agreement with leveraged/managed money flows |
| Return | DBMF / KMLM / CTA ETFs | Portfolio-level return shape and correlation |

**Important COT mapping**: Financial futures use TFF report (Leveraged Funds), physical commodities use Disaggregated report (Managed Money). These are different CFTC frameworks.

## CTAs Being Replicated (SG Trend Index 2026)

Man AHL, Graham Capital, AQR, Aspect Capital, Winton, Transtrend, Lynx, PIMCO, AlphaSimplex, iSAM — combined ~$100B+ AUM.

## Project Structure

```
config.py              — Futures universe, parameters, CFTC mappings
data/
  futures.py           — Continuous futures data (yfinance, back-adjusted)
  cot.py               — CFTC COT fetcher (TFF + Disaggregated)
  benchmarks.py        — Benchmark ETFs, SG Trend Indicator stub, NilssonHedge
model/
  trend.py             — MA crossover signal generation
  volatility.py        — EWMA vol estimation, vol targeting
  portfolio.py         — Risk parity construction, sector weighting
flow_estimator.py      — Model-implied CTA proxy flow estimation
capital_estimator.py   — Estimated CTA capital-state calculation
validation/
  signal_validation.py — vs SG Trend Indicator
  position_validation.py — vs CFTC COT
  return_validation.py — vs benchmark ETFs
report.py              — Terminal dashboard
main.py                — Entry point
```

## Known Limitations

- **yfinance futures data** has opaque roll handling — fine for prototype, not for trading. Production should use Norgate, CSI, or IB.
- **This is a trend proxy, not a positioning engine.** "Model says long" ≠ "CTAs are long." It estimates the direction trend-followers are likely positioned, not their actual holdings.
- **Proxy flow is assumption-sensitive.** Dollar and contract outputs depend on the CTA AUM assumption you pass via `--assumed-cta-aum`.
- **Capital state is estimated risk deployment.** Gross and net deployed figures are not cash balances, and the default basis is a tracked-fund reference basket rather than the full CTA industry.
- **SG Trend Indicator integration is a stub** — the web tool requires browser automation or institutional API access.
- **COT data is weekly and noisy** — useful for directional validation, not position sizing.
