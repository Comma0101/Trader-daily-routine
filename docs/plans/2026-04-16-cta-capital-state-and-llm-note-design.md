# CTA Capital State And LLM Note Design

**Goal:** Extend the CTA tracker so it can estimate overall CTA capital state in a defensible way and generate a more polished professional LLM note that explains what the data means and why it matters.

## Capital State Decision

We will not claim to know actual CTA cash balances or exact industry deployment from public data.

Instead, the tracker will estimate:

- `reference_tracked_aum_usd`
- `estimated_gross_risk_deployed_usd`
- `estimated_net_risk_deployed_usd`
- `estimated_remaining_gross_headroom_usd`

These figures represent **risk deployed** and **remaining risk headroom**, not cash spent or idle cash.

## AUM Basis

The capital estimate will support two bases:

1. `user_assumption`
   - when `--assumed-cta-aum` is provided
2. `sg_tracked_reference_basket`
   - when no explicit AUM is supplied
   - based on the existing `SG_TREND_INDEX_FUNDS` list in `config.py`
   - clearly labeled as an approximate tracked-fund basket, not the full CTA industry

This gives the user a default reference without pretending it is exact industry truth.

## Capital State Calculation

Inputs:

- `portfolio_result["gross_leverage"]`
- `portfolio_result["net_exposure"]`
- `PORTFOLIO_PARAMS["max_leverage"]`
- optional `assumed_cta_aum_usd`
- tracked-fund reference AUM from `SG_TREND_INDEX_FUNDS`

Outputs:

- `aum_basis.source`
- `aum_basis.label`
- `aum_basis.aum_usd`
- `gross_risk_deployed_pct_of_aum`
- `net_risk_deployed_pct_of_aum`
- `remaining_gross_headroom_pct_of_aum`
- `estimated_gross_risk_deployed_usd`
- `estimated_net_risk_deployed_usd`
- `estimated_remaining_gross_headroom_usd`
- `note`

Core formulas:

- `gross_risk_deployed_pct_of_aum = gross_leverage`
- `net_risk_deployed_pct_of_aum = net_exposure`
- `remaining_gross_headroom_pct_of_aum = max(0, max_leverage - gross_leverage)`
- `estimated_gross_risk_deployed_usd = gross_risk_deployed_pct_of_aum * aum_basis.aum_usd`
- `estimated_net_risk_deployed_usd = net_risk_deployed_pct_of_aum * aum_basis.aum_usd`
- `estimated_remaining_gross_headroom_usd = remaining_gross_headroom_pct_of_aum * aum_basis.aum_usd`

## LLM Note Design

The Markdown LLM summary will become a professional daily note rather than a labeled rewrite of deterministic bullets.

Target structure:

- headline
- short paragraph: current CTA regime
- short paragraph: what data drove the read and what it means
- flat bullets:
  - `Key Flows:`
  - `Validation:`
  - `Risks:`
  - `Actions:`

The note must explain:

- what data was used
- what the data implies
- why it matters now
- what to watch next

The note must not:

- invent numbers
- invent validation confidence
- treat risk deployed as cash spent
- overstate reference AUM as full industry AUM

## Fact Model Upgrade

Add deterministic fact groups:

- `capital`
- `thesis`
- `drivers`
- `interpretation`
- `why_now`
- `confidence`
- `actions`

The LLM prompt should draw from these explicit groups rather than inferring everything from low-level fields.

## Validation And Fallback

Markdown LLM output should be accepted only if it has:

- one headline
- at least two non-bullet paragraphs
- bullets for flows, validation, risks, and actions

If Gemini returns malformed structure or omits meaning/why-now context, the CLI should fall back to deterministic output.
