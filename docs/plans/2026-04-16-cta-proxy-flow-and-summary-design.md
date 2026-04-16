# CTA Proxy Flow And Summary Design

**Goal:** Extend the CTA tracker so it can estimate model-implied daily and 5-day CTA proxy flows, and produce stronger human-readable summaries that explain the data used, how the estimate was computed, the conclusion, and suggested actions.

## Context

The current tracker already computes:

- per-market trend signals
- per-market volatility scalars
- normalized portfolio weights
- historical daily model weights
- report/summary output for current positioning and validation

The current tracker does **not** compute:

- contract multipliers or contract notionals
- model-implied dollar flow
- model-implied contract flow
- explanatory summaries that clearly separate data, method, conclusion, and suggestions

## Product Decision

The new flow output will be an **estimated CTA proxy flow**, not observed CTA trading.

That estimate will be produced in two layers:

1. Always available:
   - relative flow based on daily and 5-trading-day changes in target weights
2. Optional:
   - dollar and contract estimates when the user provides an explicit aggregate CTA AUM assumption

This avoids silently hard-coding an industry-wide AUM number while still enabling crowd-level estimates when the user wants them.

## Flow Estimation Design

### Inputs

- historical weight series from `PortfolioConstructor.historical_weights(...)`
- current market prices
- contract metadata per symbol
- optional `assumed_cta_aum_usd`

### New Contract Metadata

Each market in `FUTURES_UNIVERSE` will gain the minimum fields needed for an estimate:

- `contract_multiplier`
- `contract_unit`
- `quote_currency`

The first version assumes all tracked contracts are USD-quoted or use USD-compatible continuous tickers already represented in the tracker. If a non-USD contract requires explicit FX conversion, the flow layer will support a quote-to-USD conversion hook and default to `1.0` where appropriate.

### Calculation

For each market:

- `weight_1d_change = weight_t - weight_t-1`
- `weight_5d_change = weight_t - weight_t-5`
- `estimated_notional_flow_usd = weight_change * assumed_cta_aum_usd`
- `estimated_contract_flow = estimated_notional_flow_usd / (price * contract_multiplier * fx_rate_to_usd)`

Where no AUM assumption is provided:

- keep `weight_1d_change` and `weight_5d_change`
- omit dollar and contract estimates

### Output Shape

Per market:

- `delta_weight_1d`
- `delta_weight_5d`
- `estimated_flow_usd_1d`
- `estimated_flow_usd_5d`
- `estimated_contracts_1d`
- `estimated_contracts_5d`
- `price_used`
- `assumed_cta_aum_usd`
- `estimation_label`

Aggregate:

- top estimated 1-day buyers
- top estimated 1-day sellers
- top estimated 5-day buyers
- top estimated 5-day sellers
- sector flow totals

## Summary Design

### Deterministic Summary

The fact builder will be extended to include a dedicated summary structure with four sections:

- `data_used`
- `calculation_method`
- `conclusion`
- `suggestions`

The deterministic Markdown renderer will become shareable by default and explicitly describe:

- what market set and timestamps were used
- whether prices are official daily close or live nowcast
- whether flow is weight-only or AUM-based dollar estimate
- key positioning conclusions
- validation caveats
- actionable suggestions

### LLM Summary

The LLM remains optional and presentation-only.

The LLM will receive a constrained fact payload that already contains:

- data used
- method text
- conclusions
- suggestions

The prompt will explicitly require:

- one headline
- bullets grouped logically
- no invented numbers
- explicit mention of assumptions and caveats
- suggestions grounded in the deterministic facts

If Gemini output is malformed, incomplete, or fails basic structure checks, the tracker will fall back to the deterministic summary.

## CLI And Report Design

New CLI flag:

- `--assumed-cta-aum` as a float in USD

The existing summary/report output will gain a new flow section:

- terminal report: compact flow table
- Markdown summary: short flow bullets
- JSON output: full structured flow payload

## Testing Strategy

Add tests first for:

- flow math with and without AUM
- contract conversion math
- summary fact payload sections
- deterministic Markdown/terminal rendering with method + suggestions
- LLM prompt construction and fallback
- JSON output carrying the new flow fields

## Non-Goals

- claiming true observed CTA industry trading
- inferring daily CTA trades from COT
- adding new external paid data sources
- building a full execution or order-book simulator
