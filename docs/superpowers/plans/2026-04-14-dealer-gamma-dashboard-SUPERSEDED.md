# Dealer Gamma / Options Positioning Intelligence Dashboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an internal tool that estimates dealer gamma positioning, key options levels, and regime context for SPX/SPY/ES/QQQ — producing a daily premarket summary and interactive research dashboard for discretionary index trading.

**Architecture:** Python (FastAPI) backend with BSM-based analytics engine, DuckDB + Parquet storage for analytical queries over daily chain snapshots, Next.js + ECharts frontend for dense interactive visualizations. Data ingestion via Tradier (free sandbox) + OCC (free OI) + FRED (VIX). All modeled outputs labeled as estimates with explicit assumptions and confidence ratings.

**Tech Stack:** Python 3.12 / FastAPI / DuckDB / Parquet / APScheduler / Next.js / TypeScript / ECharts / Docker Compose

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Scope Definition](#2-scope-definition)
3. [Data Source Evaluation](#3-data-source-evaluation)
4. [Metric Definitions](#4-metric-definitions)
5. [System Architecture](#5-system-architecture)
6. [Data Model](#6-data-model)
7. [Job Design](#7-job-design)
8. [API Design](#8-api-design)
9. [Frontend Plan](#9-frontend-plan)
10. [Validation Plan](#10-validation-plan)
11. [Risks / Limitations](#11-risks--limitations)
12. [Implementation Roadmap](#12-implementation-roadmap)
13. [Developer Task Breakdown](#13-developer-task-breakdown)
14. [Open Questions](#14-open-questions)

---

## 1. Executive Summary

This system estimates dealer gamma exposure, key options positioning levels, and volatility regime context for major US index products (SPX, SPY, ES, QQQ). It produces:

- A **premarket summary** answering: Are we in positive or negative gamma? Where are walls, pins, and flip levels? What regime behavior should we expect?
- A **research dashboard** with strike heatmaps, expiry analysis, historical comparison, and raw assumption debugging.
- A **historical archive** enabling event studies on whether estimated levels held, broke, or predicted regime behavior.

### Reality constraints the system is designed around

1. **Dealer positioning is unknowable from public data.** Every "dealer gamma" number is a model estimate based on the assumption that open interest is predominantly customer-long / dealer-short. This assumption is wrong 15-30% of the time (covered calls, collar funds, interdealer, 0DTE mixed flow). The system labels all outputs accordingly.

2. **Open interest is T+1.** OCC reports OI as of prior close. Intraday, true OI can differ 10-30% on active strikes. The system tracks data freshness and degrades confidence ratings when inputs are stale.

3. **Free data is delayed.** The best free source (Tradier sandbox) provides 15-minute delayed chains with greeks. This is adequate for premarket/EOD analysis but insufficient for real-time intraday gamma tracking.

4. **0DTE distorts everything.** 0DTE SPX options represent ~50%+ of daily volume but their OI is ephemeral. The system separates 0DTE analysis from the structural multi-day gamma map.

5. **No metric in this system is tradeable truth.** Every output is a probabilistic estimate. The system exists to inform discretionary judgment, not to generate signals.

---

## 2. Scope Definition

### v1.0 — Core Engine + Premarket Summary (target: 6-8 weeks)

**In scope:**
- Ingestion from Tradier sandbox (chains + greeks + IV) and OCC (daily OI)
- BSM gamma/vanna/charm computation engine
- Per-strike GEX, net GEX, GEX profile curve
- Call wall, put wall, key gamma strike identification
- Gamma flip / zero gamma estimation
- Regime classification (positive / negative / neutral)
- VIX context from FRED
- Premarket summary generation (structured JSON + plain-text interpretation)
- Daily EOD snapshot archival to Parquet
- FastAPI serving summary + strike-level data
- Minimal CLI or terminal-based premarket report
- Unit tests for all BSM formulas, GEX computation, regime classification
- Data quality checks and anomaly detection

**Out of scope for v1:**
- Frontend dashboard (CLI/terminal only)
- Intraday polling
- Vanna/charm flow estimates (computed but not surfaced in summary)
- ES futures options (SPX/SPY/QQQ only)
- Historical comparison views
- Alerting

### v1.5 — Dashboard + Historical (target: +4 weeks after v1)

**Adds:**
- Next.js frontend with premarket overview, strike heatmap, expiry view
- Historical comparison (today vs yesterday, wall movement tracking)
- Vanna context surfaced in summary
- Expiration roll-off modeling ("what does the map look like tomorrow?")
- ES futures options via CME settlement data
- Intraday polling (every 15 min during market hours via Tradier)
- Research/debug view showing raw assumptions and confidence scores

### v2.0 — Validation + Paid Data Upgrade Path (target: +6 weeks after v1.5)

**Adds:**
- Event study framework (level touch/reject/break analysis)
- Pinning behavior analysis
- Regime vs realized vol validation
- Confidence scoring based on data freshness and coverage
- Optional IBKR integration for real-time data ($10/mo)
- Optional ThetaData integration for historical backtesting
- Alerting (premarket email/Slack, intraday level breach)
- Multi-ticker expansion framework

---

## 3. Data Source Evaluation

### Primary Sources (v1)

| Source | Data | Cost | Latency | SPX | Greeks | Stability | Use |
|--------|------|------|---------|-----|--------|-----------|-----|
| **Tradier Sandbox** | Full chains: bid/ask, volume, OI, IV, delta/gamma/theta/vega (ORATS-powered) | Free, no account needed | 15-min delayed | Yes (SPXW) | Yes | Good — documented REST, 60 req/min | **Primary chain source** |
| **OCC Series Search** | Per-strike, per-expiry OI for any symbol | Free, no auth | EOD (T+1) | Yes | No | Simple HTTP, no documented limits | **OI ground truth / cross-validation** |
| **FRED API** | VIX daily close (VIXCLS), VIX 3-month, volatility indices | Free with API key | EOD | N/A | N/A | Excellent — government-backed | **VIX/vol context** |
| **CBOE VIX CSV** | VIX historical OHLC | Free download | EOD | N/A | N/A | Stable file | **VIX history backfill** |

### Secondary Sources (v1.5+)

| Source | Data | Cost | Latency | Use |
|--------|------|------|---------|-----|
| **yfinance** | Chains with OI, volume, IV (no greeks) | Free | 15-min delayed | Backup/validation; fragile |
| **CME Settlement** | ES futures options: settlement prices, IVs, OI | Free | EOD (midnight CT) | ES options positioning |

### Upgrade Path (v2)

| Source | Data | Cost | Latency | Use |
|--------|------|------|---------|-----|
| **IBKR** | Real-time chains, greeks, streaming | $10/mo (US Securities bundle) | Real-time | Production intraday |
| **Tradier funded** | Real-time equity options (SPX still 15m delayed) | $0 account + $10/mo data | Mixed | Better SPY/QQQ data |
| **ThetaData** | Historical tick-level options data | ~$80/mo | Historical | Backtesting / validation |
| **Databento** | Full OPRA tick data | $125 free credits, then usage-based | Historical/RT | Research sprints |

### Source-Specific Technical Notes

**Tradier Sandbox:**
- Endpoint: `GET /v1/markets/options/chains?symbol=SPX&expiration=YYYY-MM-DD&greeks=true`
- Rate limit: 60 req/min. With ~50 expiries per symbol and 4 symbols, a full chain pull takes ~4 requests (paginated) x 50 expiries = ~200 requests = ~3.5 minutes per symbol. Acceptable for premarket; tight for intraday.
- Greeks are ORATS-powered, generally high quality.
- Sandbox may use simulated delayed data rather than real delayed market data — must verify empirically in Phase 0.
- Expirations endpoint: `GET /v1/markets/options/expirations?symbol=SPX` to discover available expiries.

**OCC Series Search:**
- URL: `https://marketdata.theocc.com/series-search?symbolType=U&symbol=SPX`
- Returns tab-separated text: ProductSymbol, Year, Month, Day, Strike (integer + decimal), Call/Put flag, Call OI, Put OI, Position Limit
- Updated daily, typically available by 7:00 AM ET
- No authentication, no API key
- Parsing required (not clean CSV — tab-delimited with header rows)
- Legal status: public data from the clearinghouse; batch processing guide published by OCC suggests automated access is tolerated

**FRED API:**
- `GET https://api.stlouisfed.org/fred/series/observations?series_id=VIXCLS&api_key=KEY&file_type=json`
- 120 req/min, free API key
- VIX closes available next business day

### What Is NOT Available for Free

| Data | Why it matters | Cheapest path |
|------|---------------|---------------|
| Real-time SPX chains | Intraday gamma tracking | IBKR ($10/mo) |
| Trade-side information (customer buy vs sell) | Dealer sign assumption validation | Not available at any price from public feeds |
| Intraday OI updates | Detecting positioning shifts same-day | Not available; must use volume as proxy |
| Historical tick-level options data | Backtesting GEX signals | ThetaData ($80/mo) or Databento credits |
| OPRA raw feed | Complete real-time options data | $1,500/mo redistribution fee |

---

## 4. Metric Definitions

### 4.1 Per-Strike Gamma Exposure (GEX)

**Definition:** The dollar amount of delta hedging that occurs per 1% move in the underlying, attributed to dealer positions at a given strike, aggregated across all expiries.

**Formula:**
```
GEX(K) = Σ_T [ Gamma(S, K, T, σ) × OI(K, T, type) × multiplier × S² × 0.01 × sign(type) ]

where:
  sign(call) = +1  (dealer short call → stabilizing hedge flow)
  sign(put)  = -1  (dealer short put → subtract from net)
  Gamma = φ(d₁) × e^(-qT) / (S × σ × √T)     [BSM]
  d₁ = [ln(S/K) + (r - q + σ²/2)T] / (σ√T)
```

**Classification:** MODELED. Depends on BSM greeks + customer-long assumption.
**Inputs:** OI, IV (or greeks directly), spot, risk-free rate, dividend yield, multiplier.
**Assumptions:** All OI is customer-long / dealer-short. BSM greeks accurate. IV from data source is correct.
**Known failure modes:** Covered call ETFs overstate call GEX by 15-25%. 0DTE OI is stale. Interdealer OI (~10-15%) should be excluded but can't be.
**Confidence:** MEDIUM. Directionally correct for structural positioning; magnitude uncertain by 20-40%.
**Update cadence:** EOD (v1), every 15 min (v1.5+).

### 4.2 Net Gamma Exposure (Portfolio GEX)

**Definition:** Sum of per-strike GEX across all strikes. A single number representing the estimated total dealer gamma position.

**Formula:**
```
Net_GEX = Σ_K [ GEX(K) ]
        = Σ_K,T [ Gamma_call(K,T) × OI_call(K,T) - Gamma_put(K,T) × OI_put(K,T) ] × mult × S² × 0.01
```

**Classification:** MODELED.
**Confidence:** MEDIUM. Scale is approximate; sign is more reliable than magnitude.
**Update cadence:** Same as per-strike GEX.

### 4.3 GEX Profile Curve

**Definition:** Net dealer gamma evaluated at a grid of hypothetical spot prices, showing how the gamma regime would change as price moves.

**Formula:**
```
GEX_profile(S_h) = Σ_K,T [ Gamma(S_h, K, T, σ) × OI × mult × S_h² × 0.01 × sign(type) ]

for S_h in [S × 0.90, S × 0.91, ..., S × 1.10]   (200 steps)
```

**IV assumption:** Sticky strike (each option keeps its observed IV regardless of hypothetical spot). This is a simplification — in reality, IV would change with spot via the skew surface.

**Classification:** MODELED. Double approximation (dealer assumption + sticky strike).
**Confidence:** LOW-MEDIUM. Shape is informative; exact values are rough.
**Update cadence:** EOD (v1), every 15 min (v1.5+). Same as per-strike GEX.

### 4.4 Gamma Flip / Zero Gamma Estimate

**Definition:** The spot price where the GEX profile crosses zero — below this level, estimated dealer gamma is negative (destabilizing); above, positive (stabilizing).

**Method:** Linear interpolation on GEX profile zero-crossings. Take the crossing closest to and below current spot as the "primary flip."

**Classification:** MODELED ESTIMATE. Highly sensitive to assumptions.
**Typical range:** 1-5% below ATM in normal markets. Near or above ATM in bear/high-vol markets.
**Sensitivity:** ±0.5-2% shift from reasonable alternative assumptions (excluding 0DTE, adjusting covered call fraction, different DTE cutoffs).
**Confidence:** LOW. Useful as a zone (±10-20 SPX points), not a precise level. The system reports it as a range, not a line.
**Update cadence:** EOD (v1), every 15 min (v1.5+). Derived from GEX profile.
**Sensitivity band computation:** Run the flip finder under 3 scenarios: (a) baseline, (b) with 20% covered-call OI reduction on calls, (c) excluding 0DTE. The range [min_flip, max_flip] across scenarios forms the uncertainty band.

### 4.5 Call Wall

**Definition:** The strike with the highest gamma-weighted call exposure within ±10% of spot, considering only expiries < 45 DTE.

**Formula:**
```
Call_Wall = argmax_K { Σ_{T<45DTE} [ Gamma_call(K,T) × OI_call(K,T) × mult × S² × 0.01 ] }
```

**Also reported:** OI-based call wall (highest raw call OI strike) as a supplementary reference.

**Behavioral interpretation:** Acts as resistance / magnet. Dealer hedging of short calls creates selling pressure as price approaches from below (stabilizing). Pinning effect strengthens near expiration.

**Classification:** DERIVED from modeled GEX. More stable than flip estimate.
**Confidence:** MEDIUM-HIGH for identification of the correct zone (±1-2 strikes). Behavioral interpretation confidence: MEDIUM.
**Known failure modes:** Wall identification is unstable when multiple strikes have similar GEX (e.g., during broad OI dispersion). Round-number strikes (xx00, xx50) attract disproportionate OI and may dominate even when neighboring strikes have similar gamma exposure. Covered-call ETF rolls can temporarily inflate call OI at specific strikes.
**Update cadence:** EOD (v1), every 15 min (v1.5+).

### 4.6 Put Wall

**Definition:** The strike with the highest gamma-weighted put exposure within ±10% of spot, considering only expiries < 45 DTE.

**Formula:** Symmetric to call wall, using put OI/gamma.

**Behavioral interpretation:** Acts as support. If broken (spot falls through), the positive dealer gamma from puts inverts and accelerates the selloff — put wall breaks are typically more violent than call wall breaks.

**Classification:** DERIVED. Same confidence as call wall.
**Known failure modes:** Same as call wall. Additionally, put wall breaks are harder to identify in advance because panic-driven put buying can shift the wall intraday (not visible in T+1 OI).
**Update cadence:** EOD (v1), every 15 min (v1.5+).

### 4.7 Key Gamma Strike

**Definition:** The strike with the highest absolute net GEX (|call_gex - put_gex|) near spot. This is where the largest hedging flow concentration exists, regardless of direction.

**Classification:** DERIVED.
**Confidence:** MEDIUM-HIGH for zone identification.
**Update cadence:** EOD (v1), every 15 min (v1.5+).

### 4.8 Dealer Gamma Regime

**Definition:** Classification of the current estimated dealer positioning environment.

**Rules:**
```
POSITIVE / STRONG:    Net GEX > +$10B AND spot above flip     → Strong stabilizing
POSITIVE / MODERATE:  Net GEX > +$5B AND spot above flip      → Moderate stabilizing
NEGATIVE / STRONG:    Net GEX < -$5B OR spot well below flip   → Strong destabilizing
NEGATIVE / MODERATE:  Net GEX < -$2B AND spot below flip       → Moderate destabilizing
NEUTRAL:              Between thresholds or conflicting signals → Mixed/transitional
```

**Thresholds are for SPX.** Must be re-calibrated quarterly by examining the GEX distribution. For SPY, divide by ~10. For QQQ, separate calibration needed.

**Expected behavioral signatures:**
- Positive gamma → realized vol < implied, range-bound tape, gaps get faded
- Negative gamma → realized vol > implied, trending tape, gaps get extended

**Classification:** MODEL-BASED REGIME ESTIMATE.
**Historical reliability:** ~65-70% hit rate for vol compression in positive gamma; ~55-65% for vol expansion in negative gamma; unreliable for direction; fails during tail events (Volmageddon, margin cascades, central bank interventions).
**Confidence:** MEDIUM for the regime label. LOW for using it as a standalone trading signal.
**Update cadence:** EOD (v1), every 15 min (v1.5+). Regime can shift intraday if 0DTE gamma changes.

### 4.9 Vanna Context

**Definition:** Estimated net dealer vanna exposure — how much delta hedging shifts when IV changes.

**Formula:**
```
Vanna(K, T) = -φ(d₁) × e^(-qT) × d₂ / σ

Dealer_Vanna = -Σ_{K,T} [ Vanna(K,T) × OI(K,T) × mult × S × 0.01 ]
```

**Key insight:** Due to skew (more OTM put OI with higher vanna), put vanna typically dominates:
- IV drop → net buying pressure from dealer vanna re-hedging (tailwind in rallies)
- IV rise → net selling pressure (headwind in selloffs)

This creates the "vanna tailwind" feedback loop in low-vol environments.

**Classification:** MODELED. Same assumptions as GEX + requires accurate IV surface.
**Confidence:** LOW-MEDIUM. Directional signal is more reliable than magnitude.
**Update cadence:** EOD (v1), on VIX change triggers (v2).

### 4.10 Expiration Impact

**Definition:** How the gamma map changes when near-term options expire.

**Method:**
```
GEX_post_expiry(K) = GEX_current(K) - GEX_from_expiring_contracts(K)
```

Compute for: today's 0DTE, this week's Friday, this month's OPEX.

**Key question answered:** "If today's expiring options were removed, would the regime flip?"

**Classification:** DERIVED from modeled GEX. Mechanically computed.
**Confidence:** MEDIUM. The subtraction is exact given the GEX model; the uncertainty is in the GEX model itself.
**Known failure modes:** Assumes no new OI opens to replace expiring positions. In practice, roll activity can partially offset expiry removal. Most accurate for monthly OPEX (large predictable expiry) and least accurate for daily 0DTE (continuous replacement).
**Update cadence:** EOD (v1), premarket + intraday (v1.5+).

### 4.11 Pinning Probability Zones

**Definition:** Strike ranges where the combination of high gamma concentration and near expiry creates strong mean-reversion forces that tend to keep price near specific strikes.

**Heuristic:**
```
Pin_score(K) = Σ_{T < 2DTE} [ |GEX(K, T)| ] / Σ_K [ |GEX(K, T < 2DTE)| ]

Pinning zone: strikes where Pin_score > 15% of the total near-term gamma
```

**Classification:** HEURISTIC ESTIMATE.
**Historical reliability:** Pinning is most observable on monthly OPEX Fridays with large OI at round strikes. Less reliable on non-OPEX days. 0DTE has reduced pinning reliability since 2022.
**Confidence:** MEDIUM on OPEX; LOW on non-OPEX days.
**Update cadence:** EOD (v1), premarket + intraday (v1.5+).

### 4.12 Volatility Regime Context

**Definition:** Current VIX level, VIX term structure (contango/backwardation), and VIX percentile rank.

**Inputs:** VIX close from FRED, VIX term structure from CBOE (VIX, VIX3M, VIX9D if available).

**Derived signals:**
- VIX < 15: Low vol regime, positive gamma likely dominant
- VIX 15-25: Normal vol, mixed signals
- VIX > 25: Elevated vol, negative gamma more likely
- VIX term structure inverted (VIX > VIX3M): Stress signal, near-term fear
- VIX term structure steep contango: Complacency, vol supply dominant

**Classification:** RAW (VIX level) + HEURISTIC (regime label).
**Confidence:** HIGH for VIX data. MEDIUM for behavioral interpretation.
**Update cadence:** EOD from FRED (v1). Intraday VIX polling from quote source (v1.5+).

### 4.13 Modeling Tiers

The architecture is designed so Tier 1 launches fast, while Tier 2 and Tier 3 evolve cleanly without rewriting the core.

**Tier 1 — Free Heuristic Model (v1)**
- Data: Tradier sandbox (15m delayed, free) + OCC (EOD OI, free) + FRED (VIX, free)
- Greeks: BSM with provider IV. Use Tradier-supplied greeks when available; compute from IV via BSM otherwise.
- Dealer assumption: 100% customer-long. No covered-call adjustment. No volume-based direction estimation.
- IV surface: Flat per-option (each option's own IV). Sticky-strike for profile sweeps.
- Exercise: BSM for all (ignore American-exercise premium for SPY/QQQ; error < 1% for GEX).
- OI: EOD only. No intraday correction.
- 0DTE: Included in aggregates using stale T+1 OI. Flagged in confidence.
- Cost: $0/month.

**Tier 2 — Improved Model (v1.5-v2)**
- Data: IBKR ($10/mo) for real-time chains + greeks. OCC for OI ground truth.
- Greeks: Provider-computed greeks (IBKR uses proprietary model). Fallback to Bjerksund-Stensland (2002) for American-exercise greeks on SPY/QQQ.
- Dealer assumption: Configurable covered-call adjustment factor (default 15% for SPY calls, 20% for QQQ calls, 0% for SPX). Calibrated from ETF prospectus data (QYLD, XYLD, JEPQ notional).
- IV surface: Per-option IV. Optional sticky-moneyness interpolation for profile sweeps.
- OI: EOD base + intraday volume-based correction heuristic: `estimated_OI(K) = OI_eod(K) + alpha * max(0, volume_today(K) - avg_volume_20d(K))`.
- 0DTE: Separate analysis. Volume-weighted 0DTE gamma computed as a parallel metric. Headline GEX reported both with and without 0DTE.
- Cost: ~$10-15/month.

**Tier 3 — Institutional-Grade Model (future)**
- Data: ThetaData ($80/mo) or Databento for historical tick-level data. IBKR or Tradier production for real-time. CFTC Commitments of Traders for ES futures option positioning.
- Greeks: Local volatility or SABR model for consistent vol surface. Profile sweeps use fitted surface instead of sticky-strike.
- Dealer assumption: Volume-at-bid/ask classification for customer direction estimation (requires tick-level trade data). Trades at ask → customer buy. Trades at bid → customer sell. Accuracy ~60-70%.
- IV surface: Fitted parametric surface (SVI or SABR). Profile sweeps interpolate IV at each hypothetical spot.
- OI: EOD base + tick-level volume-with-direction intraday correction.
- 0DTE: Full intraday 0DTE gamma tracking with volume-direction classification. Separate 0DTE regime indicator.
- Additional: CFTC COT integration for ES futures options (weekly data, identifies commercial vs non-commercial positioning). 13F quarterly data for known institutional positions.
- Cost: ~$100-200/month.

**Tier progression architecture:** All tiers share the same analytics engine interfaces (`compute_strike_gex`, `classify_regime`, etc.). Tier differences are isolated to: (a) data ingestion adapters, (b) greek computation strategy (BSM vs Bjerksund-Stensland vs local vol), (c) OI adjustment layer, (d) confidence scoring weights. The `config.py` module stores tier-specific parameters. Switching tiers is a configuration change, not a rewrite.

---

## 5. System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          SCHEDULER (APScheduler)                     │
│  Premarket (6:00-9:30 ET) │ Intraday (9:30-16:00) │ EOD (16:05)   │
└──────────┬──────────────────────────┬────────────────────┬──────────┘
           │                          │                    │
           ▼                          ▼                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      INGESTION LAYER                                 │
│                                                                      │
│  ┌──────────────┐  ┌─────────────┐  ┌──────────┐  ┌─────────────┐  │
│  │ Tradier       │  │ OCC         │  │ FRED     │  │ yfinance    │  │
│  │ Chain Fetcher │  │ OI Fetcher  │  │ VIX      │  │ (backup)    │  │
│  └──────┬───────┘  └──────┬──────┘  └────┬─────┘  └──────┬──────┘  │
│         │                 │              │               │           │
│         ▼                 ▼              ▼               ▼           │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │              NORMALIZATION LAYER                              │   │
│  │  - Unified OptionContract schema                             │   │
│  │  - Strike/expiry standardization                             │   │
│  │  - Source tagging + freshness timestamp                      │   │
│  │  - Data quality flags (missing IV, zero OI, stale quotes)    │   │
│  └──────────────────────────┬───────────────────────────────────┘   │
└─────────────────────────────┼───────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      STORAGE LAYER                                   │
│                                                                      │
│  ┌─────────────────────────────┐  ┌──────────────────────────────┐  │
│  │ Parquet Files (DuckDB reads)│  │ SQLite (metadata)            │  │
│  │                             │  │                              │  │
│  │ data/snapshots/             │  │  - job_runs                  │  │
│  │   {YYYY}/{MM}/{DD}/        │  │  - data_quality_log          │  │
│  │     {SYM}_{DATE}_{TIME}    │  │  - config                    │  │
│  │       .parquet             │  │  - alert_thresholds          │  │
│  │                             │  │                              │  │
│  │ data/derived/              │  │                              │  │
│  │   daily_summaries/         │  │                              │  │
│  │   gex_profiles/            │  │                              │  │
│  │   level_history/           │  │                              │  │
│  └─────────────────────────────┘  └──────────────────────────────┘  │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      ANALYTICS ENGINE                                │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │ BSM Greeks    │  │ GEX Engine   │  │ Regime Classifier        │  │
│  │ Calculator    │  │              │  │                          │  │
│  │ - gamma       │  │ - per-strike │  │ - net GEX thresholds    │  │
│  │ - vanna       │  │ - profile    │  │ - flip-based override    │  │
│  │ - charm       │  │ - flip finder│  │ - vol context fusion     │  │
│  │ - delta       │  │ - wall finder│  │ - confidence scoring     │  │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘  │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │ Vanna/Charm  │  │ Expiry       │  │ Interpretation Engine    │  │
│  │ Analyzer     │  │ Roll-off     │  │                          │  │
│  │              │  │ Modeler      │  │ - regime → trader text   │  │
│  │              │  │              │  │ - level descriptions     │  │
│  │              │  │              │  │ - risk notes             │  │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘  │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      API LAYER (FastAPI)                              │
│                                                                      │
│  GET /api/summary/{symbol}         → premarket summary JSON          │
│  GET /api/strikes/{symbol}         → per-strike GEX/OI/vanna         │
│  GET /api/profile/{symbol}         → GEX profile curve data          │
│  GET /api/expiry/{symbol}          → expiry-bucketed analysis        │
│  GET /api/history/{symbol}         → historical daily summaries      │
│  GET /api/compare/{symbol}         → today vs yesterday diff         │
│  GET /api/health                   → system health + data freshness  │
│  GET /api/debug/{symbol}           → raw assumptions + confidence    │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      FRONTEND (Next.js + ECharts)                    │
│                                                                      │
│  /overview      → Premarket summary for all symbols                  │
│  /spx/gamma     → Strike heatmap + GEX profile + regime badge        │
│  /spx/expiry    → Expiry analysis + roll-off impact                  │
│  /spx/history   → Historical comparison + wall drift                 │
│  /spx/debug     → Raw data + assumptions + confidence                │
└─────────────────────────────────────────────────────────────────────┘
```

### Module Boundaries

```
trader-daily-routine/
├── backend/
│   ├── src/
│   │   ├── ingestion/           # Data fetching + normalization
│   │   │   ├── tradier.py       # Tradier API client
│   │   │   ├── occ.py           # OCC OI parser
│   │   │   ├── fred.py          # FRED VIX client
│   │   │   ├── yfinance_backup.py
│   │   │   ├── normalizer.py    # Unified schema conversion
│   │   │   └── quality.py       # Data quality checks
│   │   ├── models/              # Domain types
│   │   │   ├── options.py       # OptionContract, UnderlyingInfo, etc.
│   │   │   └── analytics.py     # StrikeGEX, GammaRegime, Summary, etc.
│   │   ├── analytics/           # Computation engine
│   │   │   ├── bsm.py           # Black-Scholes greeks
│   │   │   ├── gex.py           # GEX computation + profile + flip
│   │   │   ├── walls.py         # Call/put wall + key strike finder
│   │   │   ├── regime.py        # Regime classifier
│   │   │   ├── vanna.py         # Vanna exposure analysis
│   │   │   ├── expiry.py        # Expiry roll-off modeling
│   │   │   └── interpreter.py   # Analytics → trader text
│   │   ├── storage/             # Persistence
│   │   │   ├── parquet.py       # Snapshot read/write
│   │   │   ├── duckdb_queries.py # Analytical queries
│   │   │   └── metadata.py      # SQLite metadata ops
│   │   ├── api/                 # FastAPI routes
│   │   │   ├── main.py          # App setup + middleware
│   │   │   ├── routes_summary.py
│   │   │   ├── routes_strikes.py
│   │   │   ├── routes_history.py
│   │   │   └── routes_debug.py
│   │   ├── jobs/                # Scheduled tasks
│   │   │   ├── scheduler.py     # APScheduler setup
│   │   │   ├── premarket.py     # Premarket chain fetch + analysis
│   │   │   ├── intraday.py      # Intraday polling
│   │   │   └── eod.py           # EOD snapshot + derived metrics
│   │   └── config.py            # Settings, constants, thresholds
│   ├── tests/
│   │   ├── test_bsm.py
│   │   ├── test_gex.py
│   │   ├── test_walls.py
│   │   ├── test_regime.py
│   │   ├── test_interpreter.py
│   │   ├── test_ingestion.py
│   │   ├── test_quality.py
│   │   └── fixtures/            # Sample chain data for tests
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── app/                 # Next.js app router
│   │   │   ├── page.tsx         # Overview dashboard
│   │   │   └── [symbol]/
│   │   │       ├── gamma/page.tsx
│   │   │       ├── expiry/page.tsx
│   │   │       ├── history/page.tsx
│   │   │       └── debug/page.tsx
│   │   ├── components/
│   │   │   ├── PremarketCard.tsx
│   │   │   ├── StrikeHeatmap.tsx
│   │   │   ├── GexProfileChart.tsx
│   │   │   ├── RegimeBadge.tsx
│   │   │   ├── ExpiryTimeline.tsx
│   │   │   ├── HistoryDiff.tsx
│   │   │   └── ConfidenceMeter.tsx
│   │   ├── hooks/
│   │   │   └── useApi.ts        # SWR/React Query wrapper
│   │   └── lib/
│   │       └── api.ts           # API client
│   ├── Dockerfile
│   └── package.json
├── data/                        # Gitignored, runtime data
│   ├── snapshots/
│   └── derived/
├── docker-compose.yml
└── docs/
    └── dealer-gamma-exposure-technical-report.md
```

### Technology Choices

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Backend | **Python 3.12 + FastAPI** | Quant ecosystem (numpy/scipy for BSM), async for concurrent fetches, auto-generated OpenAPI docs |
| Analytics DB | **DuckDB + Parquet** | Columnar analytics on wide option chains (200 strikes × 50 expiries), zero-ops embedded DB, native Parquet reads. At ~40K rows/snapshot, 3x/day, DuckDB handles years of data trivially. |
| Metadata DB | **SQLite** | Job history, config, alert thresholds. No server process. |
| Scheduling | **APScheduler** | In-process, timezone-aware, no broker dependency. Single machine. |
| Caching | **cachetools TTLCache** | In-memory, 5-min TTL. Computed metrics are static between data refreshes. Zero infrastructure. |
| Frontend | **Next.js (React)** | Dense layout control for trader dashboards. File-based routing. SSR for fast initial load. |
| Charts | **ECharts (echarts-for-react)** | First-class heatmaps, markLine/markArea for level annotations, excellent performance with 40K-point datasets, financial-grade density. |
| Deployment | **Docker Compose** | Two containers (api + dashboard), reproducible, one-command startup, cloud-portable. |

---

## 6. Data Model

### 6.1 Raw Chain Snapshot (Parquet)

One file per symbol per snapshot: `data/snapshots/2026/04/14/SPX_20260414_0630.parquet`

| Column | Type | Description |
|--------|------|-------------|
| symbol | string | Underlying symbol |
| strike | float64 | Strike price |
| expiry | date | Expiration date |
| option_type | string | "call" or "put" |
| open_interest | int32 | OI (contracts) |
| volume | int32 | Today's volume |
| bid | float64 | Bid price |
| ask | float64 | Ask price |
| last | float64 | Last trade price |
| implied_vol | float64 | Annualized IV |
| delta | float64 | Delta (from source or computed) |
| gamma | float64 | Gamma (from source or computed) |
| vega | float64 | Vega |
| theta | float64 | Theta |
| spot | float64 | Underlying spot at snapshot time |
| snapshot_ts | timestamp | When this snapshot was taken |
| source | string | "tradier" / "occ" / "yfinance" |
| data_delay_min | int32 | Estimated delay in minutes |
| greeks_source | string | "provider" / "computed_bsm" |

**Estimated size:** ~40K rows × ~20 columns × ~8 bytes avg = ~6.4 MB per snapshot (uncompressed). Parquet compression → ~1-2 MB. ~3 snapshots/day × 4 symbols × 252 trading days = ~3K files/year, ~3-6 GB/year. Trivial.

### 6.2 OCC OI Snapshot (Parquet)

Separate from Tradier chains because OCC OI is the ground truth. `data/snapshots_occ/2026/04/14/SPX_OI_20260414.parquet`

| Column | Type | Description |
|--------|------|-------------|
| symbol | string | Product symbol |
| expiry | date | Expiration date |
| strike | float64 | Strike price |
| call_oi | int32 | Call open interest |
| put_oi | int32 | Put open interest |
| snapshot_date | date | Date of OI report |

### 6.3 Derived: Daily GEX Summary (Parquet)

`data/derived/daily_summaries/SPX_20260414.parquet`

| Column | Type | Description |
|--------|------|-------------|
| symbol | string | |
| date | date | Trading date |
| spot | float64 | Spot at computation time |
| net_gex | float64 | Total net dealer GEX ($) |
| regime | string | POSITIVE / NEGATIVE / NEUTRAL |
| regime_strength | string | STRONG / MODERATE / WEAK |
| gamma_flip_low | float64 | Flip range lower bound |
| gamma_flip_mid | float64 | Flip estimate midpoint |
| gamma_flip_high | float64 | Flip range upper bound |
| call_wall_gamma | float64 | Call wall (gamma-weighted) |
| call_wall_oi | float64 | Call wall (OI-based) |
| put_wall_gamma | float64 | Put wall (gamma-weighted) |
| put_wall_oi | float64 | Put wall (OI-based) |
| key_gamma_strike | float64 | Highest absolute net GEX strike |
| total_dealer_vanna | float64 | Net dealer vanna exposure |
| vix_close | float64 | VIX close |
| gex_0dte | float64 | GEX from 0DTE only |
| gex_weekly | float64 | GEX from 1-7 DTE |
| gex_monthly | float64 | GEX from 7-45 DTE |
| gex_far | float64 | GEX from >45 DTE |
| data_freshness_min | int32 | Age of underlying chain data |
| confidence | string | HIGH / MEDIUM / LOW |
| snapshot_ts | timestamp | When computed |

### 6.4 Derived: Level History (Parquet)

`data/derived/level_history/SPX_levels.parquet`

For tracking how walls and levels move over time.

| Column | Type | Description |
|--------|------|-------------|
| symbol | string | |
| date | date | |
| call_wall | float64 | Call wall strike |
| put_wall | float64 | Put wall strike |
| gamma_flip | float64 | Gamma flip estimate |
| key_gamma_strike | float64 | |
| spot_open | float64 | |
| spot_close | float64 | |
| spot_high | float64 | |
| spot_low | float64 | |
| did_touch_call_wall | bool | Price reached within 0.2% of call wall |
| did_touch_put_wall | bool | |
| did_breach_call_wall | bool | Price exceeded call wall |
| did_breach_put_wall | bool | |
| realized_range_pct | float64 | (high - low) / open |
| regime | string | |
| vix | float64 | |
| is_opex | bool | Monthly/quarterly OPEX day |
| is_weekly_expiry | bool | Weekly expiry day |
| highest_oi_strike | float64 | Strike with largest total OI (calls + puts) |
| close_to_highest_oi_dist | float64 | |spot_close - highest_oi_strike| in points |
| did_pin | bool | Close within ±0.1% of highest_oi_strike |
| pin_score | float64 | Pinning heuristic score (0-1) |
| contracts_expired | int32 | Total contracts that expired this day |
| gex_removed_by_expiry | float64 | GEX $ that was removed by expiring contracts |
| regime_post_expiry | string | Regime after removing expired contracts |

### 6.5 Derived: GEX Profile Archive (Parquet)

`data/derived/gex_profiles/SPX_20260414.parquet`

| Column | Type | Description |
|--------|------|-------------|
| symbol | string | |
| date | date | |
| spot_hypothetical | float64 | Hypothetical spot price |
| net_gex | float64 | Net GEX at that spot |
| call_gex | float64 | Call GEX component |
| put_gex | float64 | Put GEX component |

### 6.6 SQLite Metadata Schema

```sql
CREATE TABLE job_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_name TEXT NOT NULL,          -- 'premarket_fetch', 'eod_snapshot', etc.
    symbol TEXT,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    status TEXT NOT NULL,            -- 'running', 'success', 'failed'
    records_fetched INTEGER,
    error_message TEXT,
    duration_seconds REAL
);

CREATE TABLE data_quality_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP NOT NULL,
    symbol TEXT NOT NULL,
    check_name TEXT NOT NULL,        -- 'missing_iv', 'zero_oi_chain', 'stale_quote', etc.
    severity TEXT NOT NULL,          -- 'warning', 'error', 'info'
    message TEXT,
    affected_records INTEGER
);

CREATE TABLE config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP
);
```

---

## 7. Job Design

All times in US/Eastern.

### Premarket Jobs (6:00 - 9:30 ET)

| Job | Schedule | Action | Duration |
|-----|----------|--------|----------|
| `occ_oi_fetch` | 6:00 | Fetch OCC daily OI for SPX, SPY, QQQ. Parse tab-delimited response. Store as Parquet. | ~30s |
| `fred_vix_fetch` | 6:05 | Fetch latest VIX close from FRED. | ~5s |
| `tradier_chain_fetch` | 6:15 | Fetch full chains for SPX, SPY, QQQ from Tradier (with greeks). Store as Parquet snapshot. | ~15 min (rate limited) |
| `premarket_analysis` | 6:35 (after chain fetch) | Run full GEX pipeline → generate daily summary + premarket report. Store derived Parquet + print to CLI. | ~30s |
| `premarket_refresh` | 8:00, 9:00 | Re-fetch Tradier chains + re-run analysis with fresher quotes. | ~16 min each |

### Intraday Jobs (9:30 - 16:00 ET) — v1.5

| Job | Schedule | Action |
|-----|----------|--------|
| `intraday_poll` | Every 15 min | Fetch Tradier chains, recompute GEX, update cached summary |
| `vix_intraday_check` | Every 30 min | Check if VIX has moved >5% from open, update vol context |

### End-of-Day Jobs (16:00+)

| Job | Schedule | Action |
|-----|----------|--------|
| `eod_snapshot` | 16:05 | Final chain snapshot with closing prices. Primary daily archival snapshot. |
| `eod_analysis` | 16:10 | Run full analysis on EOD snapshot. Compute level history entries (did walls hold? did price pin?). Store daily summary. |
| `eod_validation` | 16:15 | Compare premarket predictions vs actual: regime vs realized vol, wall touch/breach, pinning. Log to level_history. |
| `expiry_rolloff` | 16:20 | If options expired today, compute "tomorrow's map" without expired OI. |

### Weekend Jobs

| Job | Schedule | Action |
|-----|----------|--------|
| `weekly_calibration` | Saturday 10:00 | Re-examine GEX distribution percentiles. Update regime thresholds if distribution has shifted. |
| `data_cleanup` | Sunday 10:00 | Compact old snapshots (keep only EOD after 30 days). Validate Parquet file integrity. |

---

## 8. API Design

### Summary Endpoint

`GET /api/summary/{symbol}`

Response:
```json
{
  "symbol": "SPX",
  "spot": 5234.50,
  "snapshot_ts": "2026-04-14T06:35:00-04:00",
  "data_freshness_minutes": 20,

  "net_gex": 7.2e9,
  "net_gex_formatted": "+$7.2B",
  "regime": "POSITIVE",
  "regime_strength": "MODERATE",
  "expected_vol_bias": "LOW",

  "gamma_flip": {
    "estimate": 5185.0,
    "range_low": 5170.0,
    "range_high": 5200.0,
    "distance_from_spot_pct": -0.95,
    "confidence": "LOW"
  },

  "call_wall": {
    "gamma_weighted": 5300.0,
    "oi_based": 5300.0,
    "distance_from_spot_pct": 1.25
  },
  "put_wall": {
    "gamma_weighted": 5150.0,
    "oi_based": 5100.0,
    "distance_from_spot_pct": -1.61
  },
  "key_gamma_strike": 5250.0,

  "vanna_context": {
    "net_dealer_vanna": -2.1e8,
    "interpretation": "Moderate put vanna dominance. IV drop would create buying pressure."
  },

  "expiry_impact": {
    "next_expiry": "2026-04-14",
    "contracts_expiring": 145000,
    "gex_removed_by_expiry": 1.2e9,
    "regime_after_expiry": "POSITIVE",
    "regime_change": false
  },

  "vol_context": {
    "vix_close": 16.5,
    "vix_percentile_1y": 35,
    "vix_term_structure": "CONTANGO",
    "interpretation": "Below-average vol. Term structure normal. Supports positive gamma thesis."
  },

  "gex_by_dte_bucket": {
    "0dte": 1.1e9,
    "weekly": 2.3e9,
    "monthly": 3.1e9,
    "far": 0.7e9
  },

  "trader_read": {
    "headline": "Moderate positive gamma. Stabilizing regime expected.",
    "key_levels": "Support at put wall 5150. Resistance at call wall 5300. Likely pin zone 5200-5250.",
    "risk_notes": "Watch for expansion if price breaks below 5170 (flip zone) with rising VIX. 0DTE gamma ($1.1B) could shift intraday map.",
    "action_bias": "Favor mean reversion within 5150-5300 range. Fade gaps toward the center."
  },

  "confidence": {
    "overall": "MEDIUM",
    "details": {
      "data_quality": "GOOD",
      "model_assumptions": "STANDARD",
      "known_distortions": ["0DTE OI is stale", "Covered call OI not adjusted"]
    }
  },

  "metadata": {
    "model_version": "1.0.0",
    "data_sources": ["tradier_sandbox", "occ", "fred"],
    "assumptions": [
      "All OI assumed customer-long / dealer-short",
      "BSM greeks with sticky-strike IV",
      "No covered-call adjustment",
      "0DTE included in aggregates"
    ],
    "disclaimer": "All values are estimates based on modeled assumptions. Dealer positioning cannot be directly observed from public data."
  }
}
```

### Strikes Endpoint

`GET /api/strikes/{symbol}?min_strike=5000&max_strike=5500&max_dte=45`

Returns per-strike GEX, OI, vanna data for the heatmap view. Array of StrikeGEX objects.

### Expiry Endpoint

`GET /api/expiry/{symbol}`

Response:
```json
{
  "symbol": "SPX",
  "spot": 5234.50,
  "upcoming_expiries": [
    {
      "date": "2026-04-14",
      "label": "0DTE",
      "contracts_expiring": 145000,
      "call_oi_expiring": 82000,
      "put_oi_expiring": 63000,
      "gex_contribution": 1.2e9,
      "gex_pct_of_total": 16.7,
      "post_expiry_net_gex": 6.0e9,
      "post_expiry_regime": "POSITIVE",
      "regime_change": false,
      "post_expiry_call_wall": 5300.0,
      "post_expiry_put_wall": 5150.0,
      "post_expiry_flip": 5180.0,
      "wall_shift": {"call_wall_delta": 0, "put_wall_delta": 0}
    },
    {
      "date": "2026-04-18",
      "label": "Weekly",
      "contracts_expiring": 310000,
      "gex_contribution": 2.3e9,
      "gex_pct_of_total": 31.9,
      "post_expiry_net_gex": 4.9e9,
      "post_expiry_regime": "NEUTRAL",
      "regime_change": true
    }
  ],
  "gex_by_dte_bucket": {
    "0dte": 1.1e9,
    "weekly": 2.3e9,
    "monthly": 3.1e9,
    "far": 0.7e9
  },
  "total_gex": 7.2e9,
  "dominant_expiry": "2026-04-18",
  "dominant_expiry_pct": 31.9
}
```

### Profile Endpoint

`GET /api/profile/{symbol}`

Returns the GEX profile curve: array of `[spot_hypothetical, net_gex]` pairs.

### History Endpoint

`GET /api/history/{symbol}?start=2026-04-01&end=2026-04-14`

Returns daily summaries for the date range. Used for historical comparison and trend analysis.

### Compare Endpoint

`GET /api/compare/{symbol}?date1=2026-04-13&date2=2026-04-14`

Returns diff of two daily summaries: wall movements, GEX changes, regime transitions.

### Debug Endpoint

`GET /api/debug/{symbol}`

Returns raw computation inputs: chain data freshness per expiry, number of options with missing IV, BSM parameters used, threshold values, confidence breakdown.

### Health Endpoint

`GET /api/health`

Returns: data source status, last successful fetch time per source, scheduler status, DuckDB file sizes, error counts.

---

## 9. Frontend Plan

### View 1: Premarket Overview (`/overview`)

Dense, compact view designed for 6:30 AM scan.

**Layout:**
```
┌──────────────────────────────────────────────────────────────┐
│  [SPX] [SPY] [QQQ]  ← instrument tabs                       │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  SPX 5234.50         POSITIVE GAMMA (MODERATE)    VIX 16.5  │
│  ══════════════════════════════════════════════════════════  │
│                                                              │
│  Net GEX: +$7.2B     Flip: ~5185 (LOW conf)                │
│  Call Wall: 5300      Put Wall: 5150                         │
│  Key Strike: 5250     Pin Zone: 5200-5250                    │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ TRADER READ                                            │  │
│  │ Moderate positive gamma. Stabilizing regime expected.  │  │
│  │ Support at 5150, resistance at 5300.                   │  │
│  │ Favor mean reversion within range. Fade gaps.          │  │
│  │                                                        │  │
│  │ ⚠ Watch 5170 (flip zone) + rising VIX for regime      │  │
│  │   change. 0DTE gamma ($1.1B) can shift map intraday.  │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  Data: Tradier 15m delayed │ OI: EOD 04/13 │ Conf: MEDIUM  │
└──────────────────────────────────────────────────────────────┘
```

**Components:**
- `RegimeBadge` — color-coded (green = positive, red = negative, yellow = neutral) with strength label
- `PremarketCard` — structured summary with all key levels
- `ConfidenceMeter` — visual indicator of data quality/model confidence
- `TraderReadBlock` — plain-English interpretation with risk notes

### View 2: Strike Heatmap (`/{symbol}/gamma`)

**Left panel: GEX by strike (bar chart)**
- Horizontal bars per strike
- Green bars: positive net GEX (stabilizing)
- Red bars: negative net GEX (destabilizing)
- Vertical line at current spot
- markLine annotations for call wall, put wall, flip level

**Right panel: Strike × Expiry heatmap**
- X-axis: strikes (centered on spot, ±10%)
- Y-axis: expiry dates (nearest at top)
- Color: net GEX intensity (red-yellow-green diverging colormap)
- Spot price vertical marker
- Dense positioning clusters visually obvious as hot spots

**Bottom strip: GEX profile curve**
- X-axis: hypothetical spot prices
- Y-axis: net GEX
- Zero line emphasized
- Shaded regions for positive/negative gamma
- Current spot marker + flip point marker

### View 3: Expiration View (`/{symbol}/expiry`)

**Timeline of upcoming expirations:**
- Today / Tomorrow / This Friday / Next Friday / Monthly OPEX / Quarterly
- For each: contracts expiring, GEX contribution, % of total GEX

**"What if expired?" simulator:**
- Toggle to remove specific expiry's contracts
- See how regime changes
- See how walls shift
- Useful for OPEX day planning

**GEX by DTE bucket stacked bar:**
- 0DTE | Weekly | Monthly | Far
- Shows where gamma is concentrated temporally

### View 4: Historical Comparison (`/{symbol}/history`)

**Side-by-side: Today vs Yesterday**
- Walls: did they move? Which direction?
- Net GEX: increase or decrease?
- Regime: same or changed?
- Flip: shifted up or down?

**Level history chart (time series):**
- X-axis: dates (last 30 days)
- Lines: call wall, put wall, gamma flip, spot close
- Overlay: regime color bands (green/red background)
- This is the "did the levels predict anything?" chart

**Wall hold rate table:**
- Last 20 sessions: for each day, did price touch/breach call wall? Put wall?
- Running statistics: call wall hold rate, put wall hold rate

### View 5: Research / Debug (`/{symbol}/debug`)

**Raw assumptions table:**
- Risk-free rate used, dividend yield, BSM model version
- Number of options in chain, expiries included, strike range
- OI source and timestamp, chain source and timestamp
- Options with missing IV (count + %), options excluded and why

**Confidence breakdown:**
- Data quality score (0-100)
- Model assumption score (0-100)
- Known distortions list
- Freshness score (minutes since last data)

**Chain coverage heat check:**
- Heatmap of data quality by strike × expiry
- Green = good (IV present, OI matches OCC, reasonable spread)
- Yellow = warning (estimated IV, wide spread, low OI)
- Red = missing or unreliable

**Formula details:**
- For selected strike: show gamma, OI, GEX computation step by step
- For flip estimate: show the profile curve with calculation trace

### Visual Encodings

| Data | Encoding | Library Feature |
|------|----------|-----------------|
| Net GEX by strike | Horizontal bar chart, green/red | ECharts bar series with `itemStyle` |
| GEX profile curve | Area chart, green above zero / red below | ECharts line series with `areaStyle` |
| Strike × Expiry positioning | Heatmap, diverging colormap | ECharts heatmap series + `visualMap` |
| Regime badge | Colored badge with text | Custom React component |
| Key levels on charts | Vertical dashed lines with labels | ECharts `markLine` |
| Pin zones | Shaded rectangles | ECharts `markArea` |
| Confidence | Color-graded meter | Custom component, 3-tier |
| Historical walls | Multi-line time series | ECharts line series |
| Regime history | Background color bands | ECharts `markArea` on time axis |

---

## 10. Validation Plan

### 10.1 Unit Tests

| Test Suite | What It Validates | Method |
|------------|-------------------|--------|
| `test_bsm.py` | BSM gamma/vanna/charm formulas | Compare against known analytical values. Test gamma symmetry (call gamma = put gamma). Test put-call parity on delta. Test edge cases (T→0, deep ITM/OTM). |
| `test_gex.py` | Per-strike GEX computation, profile generation, flip finder | Synthetic chain with known positioning → verify GEX values. Test that a chain with only calls has positive net GEX. Test that flip is found correctly in a simple 2-strike example. |
| `test_walls.py` | Wall identification | Synthetic chain → verify correct strike identified. Test edge cases: ties, no data in range, all strikes equidistant. |
| `test_regime.py` | Regime classification | Test threshold boundaries. Test flip-based override logic. Test with known GEX/flip combinations. |
| `test_interpreter.py` | Trader text generation | Snapshot tests: given a known GammaRegime, verify the output text matches expected templates. |
| `test_quality.py` | Data quality checks | Feed intentionally bad data (missing IV, zero OI, negative values) → verify checks catch them. |

### 10.2 Snapshot Tests

After each daily run, the system stores the complete summary JSON. Snapshot tests verify:
- Schema hasn't changed unexpectedly
- All required fields are present and non-null
- Values are within plausible ranges (e.g., SPX GEX between -$20B and +$20B, flip within ±15% of spot)
- No NaN/Inf in any numeric field

### 10.3 Data Quality Checks (Automated, Every Run)

| Check | Condition | Severity |
|-------|-----------|----------|
| Missing IV | >5% of near-ATM options have IV = 0 or null | ERROR |
| Stale quotes | Bid/ask unchanged from prior snapshot for >50% of options | WARNING |
| OI mismatch | Tradier OI vs OCC OI differ by >20% for top 10 strikes | WARNING |
| Empty chain | <100 valid options returned | ERROR |
| Expiry gaps | Expected expiry dates missing from chain | WARNING |
| Gamma scale check | Total GEX outside [-$25B, +$25B] for SPX | WARNING |
| Flip location check | Flip estimate outside ±15% of spot | WARNING |

### 10.4 Validation Studies (v2)

These are research analyses run periodically to assess whether the system's outputs have predictive value.

**Study 1: Regime vs Realized Volatility**
- For each trading day, record: regime label (morning), realized intraday range (close)
- Test: Do POSITIVE gamma days have lower realized ranges than NEGATIVE gamma days?
- Expected: ~65-70% hit rate for vol compression in positive gamma
- Method: Two-sample t-test on realized range by regime, rolling 60-day windows

**Study 2: Call Wall / Put Wall Hold Rate**
- For each day: did intraday high reach within 0.3% of call wall? Did low reach within 0.3% of put wall?
- If touched, did price reverse (hold) or break through?
- Track hold rate over rolling 30-day windows
- Baseline: ~50% (random). Useful if significantly above.

**Study 3: Pinning Into OPEX**
- On OPEX Fridays (monthly): did SPX close within ±5 points of the highest-OI strike?
- Compare pre-2022 (before 0DTE) vs post-2022
- Expected: Pinning less reliable post-0DTE

**Study 4: Gamma Flip Break → Move Extension**
- When spot breaks below the gamma flip estimate, does the subsequent move extend further than average?
- Compare: distance traveled after flip break vs distance traveled in positive gamma
- Method: Conditional mean analysis

**Study 5: Confidence Scoring Validation**
- When the system rates confidence LOW vs HIGH, is the regime classification more accurate on HIGH-confidence days?
- If not, the confidence scoring needs recalibration

### 10.5 Anomaly Detection

Automated alerts when:
- GEX changes by >50% day-over-day (either large OI shift or data problem)
- Call wall or put wall moves by >3% of spot (level reset vs data error)
- Regime flips twice in 24 hours (real instability or noisy data)
- OCC OI and Tradier OI diverge by >30% on a major strike

---

## 11. Risks / Limitations

### Fundamental Modeling Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| **Dealer positioning is unknowable** | HIGH | Label everything as estimate. Never claim certainty. Show assumptions prominently. |
| **Customer-long assumption is wrong 15-30% of the time** | HIGH | Track known exceptions (covered call ETFs, collar funds). Future: heuristic adjustment factors. |
| **0DTE makes EOD OI stale for gamma estimation** | HIGH | Separate 0DTE analysis. Use volume as intraday proxy. Flag when 0DTE > 40% of total GEX. |
| **GEX doesn't predict direction** | MEDIUM | Never output directional signals. Only vol/regime/level context. |
| **Tail events overwhelm gamma hedging** | MEDIUM | Include VIX-based override. If VIX > 30, downgrade all confidence ratings. |
| **BSM greeks are approximations** | LOW | Adequate for gamma/vanna. Error is small vs OI uncertainty. |
| **Sticky-strike IV assumption in profile sweep** | LOW | Acceptable for ±5% spot range. Worse for larger ranges. Note in docs. |

### Data Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| **Tradier sandbox data quality unknown** | HIGH | Phase 0 validates sandbox data against OCC and manual CBOE checks. |
| **Tradier rate limits constrain fetch speed** | MEDIUM | 60 req/min → ~15 min per full chain pull. Acceptable for premarket; tight for intraday. Batch expiry requests. |
| **OCC changes URL format** | LOW | Simple HTTP GET; monitor for 404s; fallback to cached OI. |
| **yfinance breaks (frequent historical precedent)** | MEDIUM | Use only as backup; never as primary. Graceful degradation. |
| **FRED data delayed** | LOW | VIX is context, not critical input. Stale by 1 day is acceptable. |

### Operational Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| **Single developer bus factor** | MEDIUM | Document everything. Docker Compose for reproducible deploys. Clean code boundaries. |
| **Disk fills with Parquet files** | LOW | Auto-cleanup job. ~6 GB/year. Alert at 80% disk. |
| **Scheduler misses premarket window** | MEDIUM | Health check endpoint. Docker restart policy. Cron backup for critical jobs. |

### Intellectual Honesty Requirements

The system MUST:
1. Never display a modeled value without labeling it as an estimate
2. Always show data freshness (minutes since last update)
3. Always show the assumptions list on every view
4. Degrade confidence ratings when inputs are stale or incomplete
5. Include a persistent footer: "Estimates based on modeled assumptions. Dealer positioning cannot be directly observed."
6. Never claim "the market will" — only "the model suggests" or "positioning implies"

---

## 12. Implementation Roadmap

### Phase 0: Research Spike (1 week)

**Goal:** Validate that the free data stack actually works for this use case.

- [ ] Register for Tradier sandbox API key
- [ ] Fetch SPX option chain from Tradier sandbox, inspect data quality
- [ ] Verify: does Tradier sandbox return greeks for SPX? Are they plausible?
- [ ] Fetch OCC OI data for SPX, verify parsing
- [ ] Cross-validate: compare Tradier OI vs OCC OI for the same date/strikes
- [ ] Manual check: compare computed GEX for 5 strikes against hand calculation
- [ ] Document findings and any data source adjustments needed

**Exit criteria:** Confidence that Tradier sandbox provides usable chain data with greeks, and OCC OI is parseable and consistent.

### Phase 1: Ingestion + Raw Chain Explorer (2 weeks)

**Goal:** Reliable data pipeline that fetches, normalizes, and stores option chains.

- [ ] Set up project structure (pyproject.toml, Docker, tests)
- [ ] Implement Tradier client (chain fetch, expiry discovery)
- [ ] Implement OCC parser
- [ ] Implement FRED VIX client
- [ ] Implement normalizer (unified OptionContract schema)
- [ ] Implement data quality checks
- [ ] Implement Parquet snapshot writer
- [ ] Implement DuckDB query layer for reading snapshots
- [ ] APScheduler: premarket fetch job
- [ ] CLI command to inspect raw chain data
- [ ] Unit tests for all ingestion modules

### Phase 2: Analytics Engine (2 weeks)

**Goal:** Compute all GEX/gamma metrics from stored chain data.

- [ ] BSM greeks module (gamma, vanna, charm, delta) with full test suite
- [ ] Per-strike GEX computation
- [ ] GEX profile curve generation
- [ ] Gamma flip finder
- [ ] Call wall / put wall / key gamma strike identification
- [ ] Regime classifier
- [ ] Vanna exposure analysis
- [ ] Expiry roll-off modeler
- [ ] Daily summary generator
- [ ] Interpretation engine (analytics → trader text)
- [ ] Confidence scoring
- [ ] CLI premarket report output
- [ ] Full test suite for analytics

### Phase 3: API + CLI Polish (1 week)

**Goal:** Serve computed analytics via REST API. Usable premarket workflow.

- [ ] FastAPI app with all endpoints
- [ ] Caching layer (TTLCache)
- [ ] Health / debug endpoints
- [ ] API response validation (Pydantic models)
- [ ] CLI polished premarket report (formatted terminal output)
- [ ] Docker Compose for backend
- [ ] Integration tests (fetch → compute → serve)

### Phase 4: Dashboard (3-4 weeks)

**Goal:** Interactive frontend for all 5 views.

- [ ] Next.js project setup + API client
- [ ] Premarket overview page
- [ ] Strike heatmap / GEX bar chart view
- [ ] GEX profile chart
- [ ] Expiry analysis view
- [ ] Historical comparison view
- [ ] Debug / research view
- [ ] Regime badge + confidence meter components
- [ ] Docker Compose updated for frontend
- [ ] End-to-end test (backend + frontend)

### Phase 5: Validation + Tuning (2-3 weeks)

**Goal:** Assess whether the system produces useful outputs.

- [ ] Historical data backfill (fetch and store chains for 30+ trading days)
- [ ] Implement event study framework
- [ ] Run regime vs realized vol study
- [ ] Run wall hold rate study
- [ ] Run pinning analysis
- [ ] Calibrate regime thresholds based on empirical GEX distribution
- [ ] Adjust confidence scoring based on validation results
- [ ] Document findings

### Phase 6: Alerting + Automation (1-2 weeks) — v2

- [ ] Email/Slack premarket summary delivery
- [ ] Intraday level breach alerts
- [ ] Weekend calibration automation
- [ ] IBKR integration for real-time data (optional)

---

## 13. Developer Task Breakdown

### Task 1: Project Scaffolding

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/src/__init__.py`
- Create: `backend/src/config.py`
- Create: `backend/tests/__init__.py`
- Create: `docker-compose.yml`
- Create: `backend/Dockerfile`
- Create: `.gitignore`

- [ ] **Step 1:** Initialize Python project with pyproject.toml

```toml
[project]
name = "dealer-gamma-dashboard"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "httpx>=0.27",
    "duckdb>=1.1",
    "pyarrow>=17",
    "pandas>=2.2",
    "numpy>=2.0",
    "scipy>=1.14",
    "apscheduler>=3.10",
    "cachetools>=5.5",
    "pydantic>=2.9",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "pytest-cov>=5.0",
    "ruff>=0.6",
]
```

- [ ] **Step 2:** Create config.py with constants

```python
from dataclasses import dataclass
from pathlib import Path

DATA_DIR = Path("data")
SNAPSHOTS_DIR = DATA_DIR / "snapshots"
DERIVED_DIR = DATA_DIR / "derived"
DB_PATH = DATA_DIR / "metadata.db"

SYMBOLS = ["SPX", "SPY", "QQQ"]

RISK_FREE_RATE = 0.043  # 4.3% — update quarterly
DIVIDEND_YIELDS = {"SPX": 0.013, "SPY": 0.013, "QQQ": 0.006, "ES": 0.0}
MULTIPLIERS = {"SPX": 100, "SPY": 100, "QQQ": 100, "ES": 50}
EXERCISE_STYLE = {"SPX": "european", "SPY": "american", "QQQ": "american", "ES": "american"}

# GEX regime thresholds (SPX scale — divide by 10 for SPY, separate for QQQ)
GEX_THRESHOLDS = {
    "SPX": {"strong_positive": 10e9, "positive": 5e9, "negative": -2e9, "strong_negative": -5e9},
    "SPY": {"strong_positive": 1e9, "positive": 0.5e9, "negative": -0.2e9, "strong_negative": -0.5e9},
    "QQQ": {"strong_positive": 0.5e9, "positive": 0.25e9, "negative": -0.1e9, "strong_negative": -0.25e9},
}

MAX_DTE_FOR_WALLS = 45
STRIKE_RANGE_PCT = 0.10
GEX_PROFILE_STEPS = 200
```

- [ ] **Step 3:** Create Dockerfile, docker-compose.yml, .gitignore
- [ ] **Step 4:** Verify `pip install -e ".[dev]"` works
- [ ] **Step 5:** Commit

```bash
git add backend/ docker-compose.yml .gitignore
git commit -m "feat: project scaffolding with dependencies and config"
```

---

### Task 2: Domain Models

**Files:**
- Create: `backend/src/models/options.py`
- Create: `backend/src/models/analytics.py`

- [ ] **Step 1:** Write tests for model validation

```python
# backend/tests/test_models.py
from src.models.options import OptionContract, UnderlyingInfo
from datetime import date

def test_option_contract_creation():
    opt = OptionContract(
        strike=5200.0, expiry=date(2026, 4, 18), option_type="call",
        open_interest=15000, implied_vol=0.18, volume=5000,
        bid=25.50, ask=26.00, last=25.75,
    )
    assert opt.strike == 5200.0
    assert opt.option_type == "call"

def test_underlying_info():
    info = UnderlyingInfo(symbol="SPX", spot=5234.50, multiplier=100,
                          style="european", dividend_yield=0.013, risk_free_rate=0.043)
    assert info.multiplier == 100
```

- [ ] **Step 2:** Run tests — verify they fail (models not yet implemented)
- [ ] **Step 3:** Implement OptionContract and UnderlyingInfo dataclasses
- [ ] **Step 4:** Implement StrikeGEX, GammaRegime, DailySummary, TraderRead dataclasses
- [ ] **Step 5:** Run tests — verify they pass
- [ ] **Step 6:** Commit

---

### Task 3: BSM Greeks Module

**Files:**
- Create: `backend/src/analytics/bsm.py`
- Create: `backend/tests/test_bsm.py`

- [ ] **Step 1:** Write comprehensive test suite for BSM greeks

```python
# Key tests:
# 1. Gamma for ATM option = known value (compare against published tables)
# 2. Gamma(call) == Gamma(put) at same strike/expiry/IV
# 3. Delta(call) - Delta(put) == exp(-qT) (put-call parity)
# 4. Gamma > 0 for all valid inputs
# 5. Gamma peaks at ATM and decays with distance from spot
# 6. As T→0, ATM gamma → infinity (test with small T)
# 7. Vanna sign: positive for OTM calls, negative for OTM puts
# 8. Edge cases: T=0, IV=0, deep ITM, deep OTM
```

- [ ] **Step 2:** Run tests — verify they fail
- [ ] **Step 3:** Implement `norm_pdf`, `norm_cdf`, `compute_d1_d2`
- [ ] **Step 4:** Implement `bsm_gamma`, `bsm_delta_call`, `bsm_delta_put`
- [ ] **Step 5:** Implement `bsm_vanna`, `bsm_charm_call`
- [ ] **Step 6:** Run tests — verify all pass
- [ ] **Step 7:** Commit

---

### Task 4: Tradier API Client

**Files:**
- Create: `backend/src/ingestion/tradier.py`
- Create: `backend/tests/test_tradier.py`
- Create: `backend/tests/fixtures/tradier_chain_response.json`

- [ ] **Step 1:** Write tests using fixture data

```python
# Test: parse Tradier chain response → list[OptionContract]
# Test: handle missing greeks gracefully
# Test: handle empty chain response
# Test: rate limit backoff logic
```

- [ ] **Step 2:** Run tests — verify they fail
- [ ] **Step 3:** Implement TradierClient class

```python
class TradierClient:
    BASE_URL = "https://sandbox.tradier.com/v1"

    async def get_expirations(self, symbol: str) -> list[date]: ...
    async def get_chain(self, symbol: str, expiration: date, greeks: bool = True) -> list[OptionContract]: ...
    async def get_full_chain(self, symbol: str, max_dte: int = 60) -> list[OptionContract]: ...
    async def get_quote(self, symbol: str) -> float: ...  # spot price
```

- [ ] **Step 4:** Run tests — verify they pass
- [ ] **Step 5:** Manual integration test: fetch real SPX chain from sandbox
- [ ] **Step 6:** Commit

---

### Task 5: OCC OI Parser

**Files:**
- Create: `backend/src/ingestion/occ.py`
- Create: `backend/tests/test_occ.py`
- Create: `backend/tests/fixtures/occ_series_search_response.txt`

- [ ] **Step 1:** Write tests using fixture data (tab-delimited OCC format)
- [ ] **Step 2:** Run tests — verify they fail
- [ ] **Step 3:** Implement OCC parser
- [ ] **Step 4:** Run tests — verify they pass
- [ ] **Step 5:** Commit

---

### Task 6: FRED VIX Client

**Files:**
- Create: `backend/src/ingestion/fred.py`
- Create: `backend/tests/test_fred.py`

- [ ] **Step 1:** Write tests (VIX fetch, response parsing, error handling)
- [ ] **Step 2:** Run tests — verify they fail
- [ ] **Step 3:** Implement FREDClient
- [ ] **Step 4:** Run tests — verify they pass
- [ ] **Step 5:** Commit

---

### Task 7: Normalizer + Data Quality

**Files:**
- Create: `backend/src/ingestion/normalizer.py`
- Create: `backend/src/ingestion/quality.py`
- Create: `backend/tests/test_normalizer.py`
- Create: `backend/tests/test_quality.py`

- [ ] **Step 1:** Write tests for normalization (Tradier → unified, OCC → unified) and quality checks (missing IV detection, stale quote detection, OI mismatch detection)
- [ ] **Step 2:** Run tests — verify they fail
- [ ] **Step 3:** Implement normalizer and quality checks
- [ ] **Step 4:** Run tests — verify they pass
- [ ] **Step 5:** Commit

---

### Task 8: Parquet Storage + DuckDB Queries

**Files:**
- Create: `backend/src/storage/parquet.py`
- Create: `backend/src/storage/duckdb_queries.py`
- Create: `backend/src/storage/metadata.py`
- Create: `backend/tests/test_storage.py`

- [ ] **Step 1:** Write tests

```python
# Test: write snapshot → read back → data matches
# Test: query by date/symbol/expiry range
# Test: metadata (job_runs, data_quality_log) CRUD
```

- [ ] **Step 2:** Run tests — verify they fail
- [ ] **Step 3:** Implement Parquet read/write (using pyarrow)
- [ ] **Step 4:** Implement DuckDB query helpers
- [ ] **Step 5:** Implement SQLite metadata layer
- [ ] **Step 6:** Run tests — verify they pass
- [ ] **Step 7:** Commit

---

### Task 9: GEX Computation Engine

**Files:**
- Create: `backend/src/analytics/gex.py`
- Create: `backend/tests/test_gex.py`

- [ ] **Step 1:** Write tests

```python
# Test: synthetic chain with 1 call at K=5200, OI=10000 → verify GEX value
# Test: synthetic chain with 1 put at K=5200, OI=10000 → verify negative GEX
# Test: net GEX of balanced call+put chain → verify net is call-put
# Test: GEX profile shape — positive above ATM, negative below for typical chain
# Test: total GEX scale — should be in billions for SPX-like OI
# Test: empty chain → zero GEX, no errors
```

- [ ] **Step 2:** Run tests — verify they fail
- [ ] **Step 3:** Implement `compute_strike_gex` function
- [ ] **Step 4:** Implement `compute_gex_profile` function
- [ ] **Step 5:** Run tests — verify they pass
- [ ] **Step 6:** Commit

---

### Task 10: Flip Finder + Wall Finder

**Files:**
- Create: `backend/src/analytics/walls.py`
- Create: `backend/tests/test_walls.py`

- [ ] **Step 1:** Write tests

```python
# Test: simple profile that crosses zero → find correct flip point
# Test: profile with no zero crossing → return None
# Test: profile with multiple crossings → return all, primary is below spot
# Test: call wall = strike with highest call GEX
# Test: put wall = strike with highest put GEX
# Test: only considers strikes within range_pct of spot
```

- [ ] **Step 2:** Run tests — verify they fail
- [ ] **Step 3:** Implement `find_gamma_flip`, `find_primary_gamma_flip`
- [ ] **Step 4:** Implement `find_walls_and_key_strikes`
- [ ] **Step 5:** Run tests — verify they pass
- [ ] **Step 6:** Commit

---

### Task 11: Regime Classifier

**Files:**
- Create: `backend/src/analytics/regime.py`
- Create: `backend/tests/test_regime.py`

- [ ] **Step 1:** Write tests for all regime states and edge cases
- [ ] **Step 2:** Run tests — verify they fail
- [ ] **Step 3:** Implement `classify_regime`
- [ ] **Step 4:** Run tests — verify they pass
- [ ] **Step 5:** Commit

---

### Task 12: Vanna + Expiry Modules

**Files:**
- Create: `backend/src/analytics/vanna.py`
- Create: `backend/src/analytics/expiry.py`
- Create: `backend/tests/test_vanna.py`
- Create: `backend/tests/test_expiry.py`

- [ ] **Step 1:** Write tests for vanna exposure computation and expiry roll-off
- [ ] **Step 2:** Run tests — verify they fail
- [ ] **Step 3:** Implement vanna exposure analyzer
- [ ] **Step 4:** Implement expiry roll-off modeler
- [ ] **Step 5:** Run tests — verify they pass
- [ ] **Step 6:** Commit

---

### Task 13: Interpretation Engine

**Files:**
- Create: `backend/src/analytics/interpreter.py`
- Create: `backend/tests/test_interpreter.py`

- [ ] **Step 1:** Write snapshot tests for trader-facing text generation

```python
# Test: POSITIVE/STRONG regime → text includes "strong positive gamma" and "stabilizing"
# Test: NEGATIVE/MODERATE regime → text includes "negative gamma" and "destabilizing"
# Test: spot near flip → text includes warning about regime change
# Test: high VIX → text includes vol context
# Test: OPEX day → text includes expiry warning
```

- [ ] **Step 2:** Run tests — verify they fail
- [ ] **Step 3:** Implement interpreter rules engine

```python
class TraderInterpreter:
    def generate_summary(self, regime: GammaRegime, vanna: VannaContext,
                         expiry: ExpiryImpact, vol: VolContext) -> TraderRead:
        # Rule-based text generation
        # Returns: headline, key_levels, risk_notes, action_bias
```

- [ ] **Step 4:** Run tests — verify they pass
- [ ] **Step 5:** Commit

---

### Task 14: Full Pipeline + CLI Report

**Files:**
- Create: `backend/src/analytics/pipeline.py`
- Create: `backend/src/cli.py`
- Create: `backend/tests/test_pipeline.py`

- [ ] **Step 1:** Write integration test: fixture chain → full pipeline → verify summary structure
- [ ] **Step 2:** Run tests — verify they fail
- [ ] **Step 3:** Implement `run_gex_analysis` pipeline function (orchestrates all analytics)
- [ ] **Step 4:** Implement CLI premarket report (formatted terminal output)

```
═══════════════════════════════════════════════════
  SPX PREMARKET GAMMA REPORT — 2026-04-14 06:35 ET
═══════════════════════════════════════════════════
  Spot: 5234.50   │  VIX: 16.5  │  Conf: MEDIUM
  ─────────────────────────────────────────────────
  Net GEX: +$7.2B │  Regime: POSITIVE (MODERATE)
  Flip:  ~5185    │  Distance: -0.95%
  Call Wall: 5300 │  Put Wall: 5150
  Key Strike: 5250│  Pin Zone: 5200-5250
  ─────────────────────────────────────────────────
  TRADER READ:
  Moderate positive gamma. Stabilizing regime.
  Support 5150, resistance 5300.
  Favor mean reversion. Fade gaps toward center.

  ⚠ Watch 5170 (flip zone) + rising VIX.
  ⚠ 0DTE gamma ($1.1B) can shift intraday map.
  ─────────────────────────────────────────────────
  Data: Tradier 15m delayed │ OI: EOD 04/13
  Model: BSM │ Assumption: customer-long
  ⚠ ALL VALUES ARE ESTIMATES
═══════════════════════════════════════════════════
```

- [ ] **Step 5:** Run tests — verify they pass
- [ ] **Step 6:** Commit

---

### Task 15: Scheduler + Premarket Job

**Files:**
- Create: `backend/src/jobs/scheduler.py`
- Create: `backend/src/jobs/premarket.py`
- Create: `backend/src/jobs/eod.py`

- [ ] **Step 1:** Write tests for job orchestration (mock data fetchers)
- [ ] **Step 2:** Run tests — verify they fail
- [ ] **Step 3:** Implement scheduler setup with APScheduler
- [ ] **Step 4:** Implement premarket job (fetch → normalize → store → analyze → report)
- [ ] **Step 5:** Implement EOD job (final snapshot → daily summary → level history)
- [ ] **Step 6:** Run tests — verify they pass
- [ ] **Step 7:** Commit

---

### Task 16: FastAPI Application

**Files:**
- Create: `backend/src/api/main.py`
- Create: `backend/src/api/routes_summary.py`
- Create: `backend/src/api/routes_strikes.py`
- Create: `backend/src/api/routes_history.py`
- Create: `backend/src/api/routes_debug.py`
- Create: `backend/tests/test_api.py`

- [ ] **Step 1:** Write API tests using TestClient
- [ ] **Step 2:** Run tests — verify they fail
- [ ] **Step 3:** Implement FastAPI app with all endpoints
- [ ] **Step 4:** Implement caching layer
- [ ] **Step 5:** Implement health + debug endpoints
- [ ] **Step 6:** Run tests — verify they pass
- [ ] **Step 7:** Verify auto-generated OpenAPI docs at `/docs`
- [ ] **Step 8:** Commit

---

### Task 17: Frontend — Project Setup + API Client

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/src/hooks/useApi.ts`
- Create: `frontend/Dockerfile`

- [ ] **Step 1:** Initialize Next.js project with TypeScript
- [ ] **Step 2:** Install dependencies: echarts, echarts-for-react, swr
- [ ] **Step 3:** Create API client typed to backend response schema
- [ ] **Step 4:** Create SWR hook for data fetching with auto-refresh
- [ ] **Step 5:** Verify dev server starts
- [ ] **Step 6:** Commit

---

### Task 18: Frontend — Premarket Overview Page

**Files:**
- Create: `frontend/src/app/page.tsx`
- Create: `frontend/src/components/PremarketCard.tsx`
- Create: `frontend/src/components/RegimeBadge.tsx`
- Create: `frontend/src/components/ConfidenceMeter.tsx`
- Create: `frontend/src/components/TraderReadBlock.tsx`

- [ ] **Step 1:** Implement RegimeBadge (green/red/yellow with text)
- [ ] **Step 2:** Implement ConfidenceMeter (3-tier visual)
- [ ] **Step 3:** Implement TraderReadBlock (headline + levels + risks)
- [ ] **Step 4:** Implement PremarketCard (assembles all components for one symbol)
- [ ] **Step 5:** Implement overview page (tabs for SPX/SPY/QQQ)
- [ ] **Step 6:** Verify renders with mock data
- [ ] **Step 7:** Connect to live API
- [ ] **Step 8:** Commit

---

### Task 19: Frontend — Strike Heatmap + GEX Profile

**Files:**
- Create: `frontend/src/app/[symbol]/gamma/page.tsx`
- Create: `frontend/src/components/StrikeHeatmap.tsx`
- Create: `frontend/src/components/GexBarChart.tsx`
- Create: `frontend/src/components/GexProfileChart.tsx`

- [ ] **Step 1:** Implement GexBarChart (horizontal bars, green/red, level markers)
- [ ] **Step 2:** Implement StrikeHeatmap (strike × expiry, diverging colormap)
- [ ] **Step 3:** Implement GexProfileChart (area chart, zero line, flip/wall markers)
- [ ] **Step 4:** Assemble gamma page layout (left: bars, right: heatmap, bottom: profile)
- [ ] **Step 5:** Connect to API
- [ ] **Step 6:** Commit

---

### Task 20: Frontend — Expiry + History + Debug Views

**Files:**
- Create: `frontend/src/app/[symbol]/expiry/page.tsx`
- Create: `frontend/src/app/[symbol]/history/page.tsx`
- Create: `frontend/src/app/[symbol]/debug/page.tsx`
- Create: `frontend/src/components/ExpiryTimeline.tsx`
- Create: `frontend/src/components/HistoryDiff.tsx`

- [ ] **Step 1:** Implement expiry view (DTE bucket chart, roll-off simulator)
- [ ] **Step 2:** Implement history view (today vs yesterday, wall drift time series)
- [ ] **Step 3:** Implement debug view (raw assumptions, confidence breakdown, formula trace)
- [ ] **Step 4:** Connect all views to API
- [ ] **Step 5:** Final polish: responsive layout, loading states, error handling
- [ ] **Step 6:** Commit

---

### Task 21: Integration Testing + Docker Compose

**Files:**
- Modify: `docker-compose.yml`
- Create: `backend/tests/test_integration.py`

- [ ] **Step 1:** Write end-to-end integration test: scheduler triggers → data fetched → analytics computed → API serves → response validates
- [ ] **Step 2:** Update Docker Compose with both services
- [ ] **Step 3:** Verify `docker compose up` brings up working system
- [ ] **Step 4:** Verify frontend can reach backend API
- [ ] **Step 5:** Commit

---

## 14. Open Questions

### Data Questions (Resolve in Phase 0)

1. **Does Tradier sandbox return real delayed data or simulated data for SPX?** Must verify empirically. If simulated, the entire v1 data stack changes.

2. **How complete are Tradier sandbox greeks?** Do all strikes have gamma/delta, or only liquid ones? What happens for deep OTM options?

3. **OCC OI timing:** Exactly when does OCC update? Is it available by 6:00 AM ET? If not, premarket analysis uses stale T-2 OI on some mornings.

4. **Tradier SPX vs SPXW:** Does Tradier use "SPX" or "SPXW" as the root symbol for weekly/0DTE options? Need to test endpoint behavior.

5. **Rate limit reality:** Can we sustain 200+ requests in 15 minutes from Tradier sandbox daily without getting throttled?

### Modeling Questions (Resolve in Phase 2)

6. **Covered call adjustment factor:** Should we apply a heuristic discount to call OI (e.g., 15-20% for SPY/QQQ)? If so, how to calibrate? Tentative answer: implement as a configurable parameter, default to 0 (no adjustment) in v1, tune in v2 based on validation.

7. **0DTE treatment:** Should 0DTE be included in the headline GEX number or reported separately? Tentative answer: include in headline but also show 0DTE bucket separately. Add a "excluding 0DTE" variant.

8. **Regime threshold calibration:** The initial thresholds ($5B/$10B for SPX) are based on community estimates. Need empirical calibration once we have 30+ days of data.

9. **Gamma flip sensitivity band:** How wide should the uncertainty band be? ±10 SPX points? ±0.5%? Need empirical analysis.

10. **Cross-instrument aggregation:** Should we sum SPX + SPY + QQQ GEX into a single "S&P ecosystem" gamma number? Tentative answer: display separately and optionally aggregated.

### Product Questions (Resolve before Phase 4)

11. **Auto-refresh cadence for dashboard:** How often should the frontend poll? Every 60 seconds during market hours? Only on manual refresh premarket?

12. **Mobile / tablet support:** Is this desktop-only? Affects layout decisions significantly.

13. **Multi-user or single-user?** Affects caching strategy and OPRA licensing.

14. **Alert delivery method:** Email, Slack, SMS, push notification? Depends on infrastructure.

---

## Recommended v1 Build Strategy

**Start with Phase 0.** The entire system hinges on whether Tradier sandbox provides usable SPX chain data with greeks. Spend 2-3 days validating this before writing any production code.

**If Tradier sandbox works:** Follow the roadmap as written. The free data stack (Tradier + OCC + FRED) is sufficient for a genuinely useful premarket tool.

**If Tradier sandbox data is inadequate:** Fallback options in priority order:
1. Open a Schwab account ($0 minimum) and use Schwab API — better data quality, but 7-day re-auth pain
2. Use yfinance as primary with OCC for OI ground truth — fragile but free
3. Go straight to IBKR ($10/mo) — best data quality, moderate operational complexity

**Minimum viable data stack:** Tradier sandbox (chains + greeks) + OCC (OI validation) + FRED (VIX). Total cost: $0.

**Biggest modeling risks:**
1. Customer-long assumption being wrong enough to invert the regime call
2. 0DTE making the entire EOD-based gamma map irrelevant by 10 AM
3. GEX thresholds being miscalibrated, producing noisy regime classifications

**Fastest path to a useful internal tool:** Phase 0 (1 week) → Phase 1 (2 weeks) → Phase 2 (2 weeks) → Phase 3 (1 week) = **6 weeks to a CLI-based premarket report that runs every morning.** This is the useful core. The dashboard (Phase 4) is polish on top of a system that already answers the key questions.
