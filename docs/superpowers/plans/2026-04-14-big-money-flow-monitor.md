# Big Money Flow Monitor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A small daily premarket script that estimates whether systematic big-money flows (CTAs, vol-control funds, dealer hedging) are likely a tailwind or headwind for SPX today.

**Architecture:** Single Python script. No framework, no database, no frontend. Reads free daily data, applies deterministic rules, prints a structured text report. Entire system fits in ~5 files.

**Tech Stack:** Python 3.12 / httpx / numpy / scipy (BSM only)

---

## 1. Goal

Each trading morning, answer four questions:

1. **CTA / trend-following:** Are systematic trend-followers likely adding or reducing equity exposure?
2. **Vol-control / risk-parity:** Are volatility-targeting allocators likely supportive or pulling back?
3. **Dealer gamma (SPX only):** Is estimated dealer positioning stabilizing or destabilizing?
4. **Combined read:** Tailwind, headwind, or mixed?

Output is a plain-text premarket report. No dashboard. No API. No frontend.

---

## 2. Why the Previous Plan Was Too Broad

The original plan designed a full-stack analytics platform: FastAPI, DuckDB, Parquet, Next.js, ECharts, APScheduler, Docker Compose, 21 developer tasks, 5 dashboard views, event-study framework, multi-symbol support, intraday polling, vanna/charm modeling, rich interpretation engine.

Problems:

- **Options positioning was the entire system.** Dealer gamma is inherently a low-confidence estimate built on unknowable assumptions (who is long, who is short). Making it the sole foundation of a daily workflow is fragile. It should be one input among several.
- **Scope was 3-4 months of build for one developer.** The useful core — "what regime are we in?" — can be answered in a weekend with a script.
- **Most of the infrastructure wasn't load-bearing.** DuckDB, Parquet, APScheduler, Docker — all necessary for a platform, none necessary for a daily report.
- **CTA and vol-control flows were not addressed at all.** These are arguably more mechanically predictable than dealer gamma (they follow deterministic rules around price and vol) and were completely absent from the original plan.
- **The dashboard was premature.** Building UI before validating whether the signals are useful inverts the right order.

The technical research on BSM formulas, GEX computation, and data sources remains valid and is preserved in `docs/dealer-gamma-exposure-technical-report.md`. This plan reuses that research as a component, not as the product.

---

## 3. Lean v1 Scope

### In scope

- SPX-focused daily premarket report
- Three signal components: CTA proxy, vol-control proxy, SPX gamma overlay
- Daily data only (EOD prices, EOD option chains, EOD VIX)
- Deterministic rules with explicit thresholds
- CLI plain-text output (and optionally JSON)
- All options outputs labeled as estimates with stated assumptions
- 0DTE excluded from headline gamma numbers

### Explicitly not being built

- Frontend / dashboard / UI of any kind
- API server or web framework
- Database (DuckDB, PostgreSQL, SQLite)
- Intraday data or polling
- Multi-symbol support (SPY, QQQ, ES deferred)
- Vanna or charm as headline features
- Complex natural-language interpretation engine
- Rich storage architecture (Parquet, snapshot archival)
- Event-study or backtesting platform
- Alerting, email, Slack integration
- Docker, containers, deployment infrastructure
- Anything requiring paid data

---

## 4. Core Signals

### Signal 1: CTA / Trend-Following Proxy

**What it estimates:** Whether systematic trend-following strategies (CTAs, managed futures) are likely net long, net short, or actively changing their equity exposure.

**Why it matters:** CTAs collectively manage ~$350B+ and follow mechanical price-trend rules. When they are adding longs, they provide a persistent bid. When they are cutting, they provide persistent selling. Their flows are large enough to move markets for days. Unlike discretionary flows, CTA behavior is approximately predictable because their rules are known.

**Model:**

CTAs typically use moving-average crossover rules on multiple timeframes. The exact parameters vary by fund, but the industry clusters around well-known lookback windows.

```
Inputs:
  SPX daily close prices (at least 200 trading days of history)

Rules:
  short_ma  = SMA(close, 10)     # ~2 week trend
  medium_ma = SMA(close, 50)     # ~2.5 month trend
  long_ma   = SMA(close, 200)    # ~10 month trend

  # Trend score per timeframe: +1 if price above MA, -1 if below
  trend_short  = +1 if close > short_ma  else -1
  trend_medium = +1 if close > medium_ma else -1
  trend_long   = +1 if close > long_ma   else -1

  # Composite trend score: [-3, +3]
  trend_score = trend_short + trend_medium + trend_long

  # Momentum of the trend (are CTAs likely changing exposure?)
  # Compare current score to score from 5 days ago
  trend_score_5d_ago = trend_short_5d + trend_medium_5d + trend_long_5d
  trend_delta = trend_score - trend_score_5d_ago

Signal output:
  trend_score:  -3 to +3 (current positioning estimate)
  trend_delta:  -6 to +6 (recent change — are they adding or cutting?)
  cta_regime:
    +3:           "FULL LONG — all timeframes aligned bullish"
    +1 to +2:    "MOSTLY LONG — short-term or medium-term wobble"
    0:            "MIXED — no clear trend signal"
    -1 to -2:    "MOSTLY SHORT — likely reducing exposure"
    -3:           "FULL SHORT — all timeframes aligned bearish"
  flow_direction:
    trend_delta > 0:  "ADDING" (buying pressure)
    trend_delta == 0: "HOLDING"
    trend_delta < 0:  "CUTTING" (selling pressure)
```

**Classification:** PROXY / HEURISTIC. Real CTAs use proprietary variations (exponential MAs, breakout rules, vol-adjusted sizing). This captures the central tendency, not any specific fund.

**Known failure modes:**
- Whipsaw regimes: price oscillates around MAs, causing rapid score changes that don't reflect actual fund rebalancing (funds typically have execution lags and smoothing).
- Crowded reversals: when all CTAs hit the same signal simultaneously, the resulting flow can be front-run or overshoot.
- This model cannot distinguish between "CTAs are long and adding" vs "CTAs are long and holding steady." The delta helps but is noisy at daily frequency.

**Confidence:** MEDIUM for the regime label (+3/-3 extremes are reliable). LOW-MEDIUM for the flow direction (delta is noisy).

**Data required:** 200+ daily SPX closes. Free from any source (Yahoo Finance, FRED, etc.).

**Enhancement for later:** Add a vol-adjusted position sizing estimate. CTAs typically scale exposure inversely with realized vol: `position_size ∝ target_vol / realized_vol`. When realized vol rises, they mechanically cut even if the trend signal is still long.

---

### Signal 2: Vol-Control / Risk-Parity Proxy

**What it estimates:** Whether volatility-targeting and risk-parity strategies are likely increasing or decreasing their equity allocation.

**Why it matters:** Vol-targeting strategies (risk-parity funds, vol-control overlays, target-date funds with vol management) collectively manage trillions. Their rule is simple: when realized vol is low, lever up; when realized vol rises, delever. This creates a mechanical feedback loop — selling begets volatility which begets more selling. These flows are slower than CTA flows (rebalancing is typically daily or weekly) but larger in aggregate.

**Model:**

```
Inputs:
  SPX daily close prices (at least 63 trading days)
  VIX daily close

Rules:
  # Realized vol (annualized, using log returns)
  rvol_21d = std(ln(close[t] / close[t-1]) for t in last 21 days) * sqrt(252)
  rvol_63d = std(ln(close[t] / close[t-1]) for t in last 63 days) * sqrt(252)

  # Vol regime classification
  if rvol_21d < 0.10:
      vol_regime = "VERY_LOW"        # <10% annualized — max leverage likely
  elif rvol_21d < 0.15:
      vol_regime = "LOW"             # Supportive — funds levered up
  elif rvol_21d < 0.20:
      vol_regime = "MODERATE"        # Normal — neutral allocation
  elif rvol_21d < 0.30:
      vol_regime = "ELEVATED"        # Deleveraging likely in progress
  else:
      vol_regime = "HIGH"            # Forced selling / max delever

  # Vol trajectory (is vol rising or falling?)
  vol_trajectory = "RISING" if rvol_21d > rvol_63d * 1.10 else
                   "FALLING" if rvol_21d < rvol_63d * 0.90 else
                   "STABLE"

  # VIX vs realized (implied vs realized spread)
  # Large positive spread = market pricing more vol than realized = potential for vol supply
  # Negative spread = realized exceeding implied = stress
  vrp = VIX - rvol_21d * 100  # VIX is in % points, rvol is decimal
  vrp_signal = "POSITIVE" if vrp > 3 else "NEGATIVE" if vrp < -3 else "NEUTRAL"

  # Allocation direction estimate
  if vol_regime in ("VERY_LOW", "LOW") and vol_trajectory != "RISING":
      allocation_direction = "SUPPORTIVE"    # Funds at/near max equity allocation
  elif vol_regime == "MODERATE" and vol_trajectory == "FALLING":
      allocation_direction = "SUPPORTIVE"    # Re-leveraging after a vol spike
  elif vol_regime == "ELEVATED" and vol_trajectory == "RISING":
      allocation_direction = "DELEVERAGING"  # Active selling
  elif vol_regime == "HIGH":
      allocation_direction = "FORCED_SELLING" # Mechanical deleverage at extremes
  else:
      allocation_direction = "NEUTRAL"

Signal output:
  rvol_21d:               realized vol (annualized)
  vol_regime:             VERY_LOW / LOW / MODERATE / ELEVATED / HIGH
  vol_trajectory:         RISING / FALLING / STABLE
  vrp_signal:             POSITIVE / NEGATIVE / NEUTRAL
  allocation_direction:   SUPPORTIVE / NEUTRAL / DELEVERAGING / FORCED_SELLING
```

**Classification:** PROXY / HEURISTIC. Real vol-targeting strategies use proprietary vol estimators (EWMA, GARCH, intraday vol), rebalance at different frequencies, and have varying target-vol levels (6-12% typical). This captures the central tendency.

**Known failure modes:**
- Vol regimes can persist at "ELEVATED" for months (2022). The deleveraging signal stays on even after funds have already finished cutting.
- Vol spike → recovery can be fast. The 21d window lags the actual re-levering by a week or more.
- VIX is not the same as realized vol. The VRP signal is a rough proxy for vol supply/demand.

**Confidence:** HIGH for extreme regimes (VERY_LOW, HIGH). MEDIUM for intermediate. LOW for timing the transition (when exactly funds flip from cutting to adding).

**Data required:** 63+ daily SPX closes + VIX daily close. Both free.

---

### Signal 3: SPX Dealer Gamma Overlay

**What it estimates:** Whether market-maker hedging flows are likely stabilizing (mean-reverting) or destabilizing (trend-amplifying) for SPX.

**Why it's an overlay, not the primary signal:** Dealer gamma estimation requires the assumption that all open interest is customer-long / dealer-short. This assumption is wrong 15-30% of the time. CTA and vol-control signals are based on observable prices and deterministic math. Dealer gamma is based on unobservable positioning and a sign convention. It adds useful context but should never be the lead signal.

**Model:** Uses the GEX computation from `docs/dealer-gamma-exposure-technical-report.md`. Summarized here:

```
Inputs:
  SPX option chain: strike, expiry, OI, IV (for all expiries with DTE 1-45)
  SPX spot price
  Risk-free rate (~4.3%), dividend yield (~1.3%)

  NOTE: 0DTE contracts (DTE = 0) are EXCLUDED from all computations.
  Reason: 0DTE OI is reported T+1 (stale by definition) and the technical
  report explicitly states "you must use real-time volume data, not OI" for
  0DTE (docs/dealer-gamma-exposure-technical-report.md:739). Since we only
  have EOD data, 0DTE gamma is unmeasurable and would distort the output.

Computation:
  For each option (strike K, expiry T, type call/put):
    gamma = BSM_gamma(S, K, T, r, q, IV)
    gex = gamma × OI × 100 × S² × 0.01

  Per-strike net GEX:
    net_gex(K) = Σ_T [ gex_call(K,T) - gex_put(K,T) ]

  Total net GEX:
    total_gex = Σ_K [ net_gex(K) ]

  Gamma flip:
    Sweep hypothetical spot from S×0.92 to S×1.08 (100 steps).
    At each S_h, recompute total net GEX.
    Flip = spot where net GEX crosses zero (linear interpolation).
    Report as a zone (±0.5% of the interpolated value), not a precise level.

  Call wall: strike with highest Σ_T[ gex_call(K,T) ] within ±8% of spot
  Put wall:  strike with highest Σ_T[ gex_put(K,T) ]  within ±8% of spot

  Regime:
    if total_gex > 0 and spot > flip:  "POSITIVE — likely stabilizing"
    if total_gex < 0 or spot < flip:   "NEGATIVE — likely destabilizing"
    else:                               "NEUTRAL — ambiguous"
```

**Important: what "positive" and "negative" gamma mean in this convention.**

The formula `call_gex - put_gex` is a market convention, not a physical description of dealer gamma sign. Here is what it actually represents:

- **The dealer is short gamma on every contract** (under the customer-long assumption). Short gamma is always procyclical — the hedging response amplifies moves. This is true for both short calls and short puts.
- **However, the hedging *direction* differs.** A dealer short a call delta-hedges by buying into rallies and selling into dips (buying the underlying as it rises). A dealer short a put delta-hedges by selling into drops and buying into rallies (selling the underlying as it drops).
- **The convention `call_gex - put_gex` computes the net directional hedging pressure.** When this is positive (call gamma dominates), the dealer's net hedging is buy-on-dip / sell-on-rally — which *looks like* stabilizing flow even though the dealer is short gamma. When it is negative (put gamma dominates), the net hedging is sell-on-dip / buy-on-rally — destabilizing flow.
- **"Positive GEX" does NOT mean the dealer is long gamma.** It means the net hedging flow direction from short-gamma positions happens to be stabilizing at the current spot price. This distinction matters when the customer-long assumption breaks (e.g., covered call ETFs make the dealer long calls, flipping the call-side hedging direction).

This is the single most common source of confusion in GEX analysis. The regime label describes the *expected net hedging flow direction*, not the sign of the dealer's gamma position.

**Classification:** MODELED ESTIMATE. Low-to-medium confidence. All values are approximate.

**Known failure modes (from the technical report):**
- Customer-long assumption wrong 15-30% of the time (covered calls, collar funds, interdealer)
- OI is T+1 stale — positions opened today invisible until tomorrow
- 0DTE excluded entirely (correct for v1, but means intraday gamma shifts are invisible)
- BSM greeks approximate; skew effects ignored in profile sweep (sticky-strike assumption)
- Regime thresholds are uncalibrated until we accumulate data
- Tail events overwhelm gamma flows (Volmageddon, margin cascades, Fed surprises)

**Confidence:** LOW-MEDIUM for regime label. LOW for precise levels (flip, walls). Useful as context, not as a standalone signal.

**Data required:** SPX option chain with OI + IV. Tradier sandbox (free, 15-min delayed, with greeks). OCC daily OI as cross-check (free).

---

### Signal 4: Combined Read

**What it produces:** A single summary assessment of whether systematic flows are a net tailwind, headwind, or mixed.

**Logic:**

```
# Score each component: +1 (tailwind), 0 (neutral), -1 (headwind)

cta_score:
  +1 if trend_score >= 2 and trend_delta >= 0    # strong trend, adding or holding
  -1 if trend_score <= -2 or trend_delta <= -2    # weak trend or actively cutting
   0 otherwise

vol_score:
  +1 if allocation_direction == "SUPPORTIVE"
  -1 if allocation_direction in ("DELEVERAGING", "FORCED_SELLING")
   0 otherwise

gamma_score:
  +1 if regime == "POSITIVE" and confidence >= MEDIUM
  -1 if regime == "NEGATIVE" and confidence >= MEDIUM
   0 otherwise (including when confidence is LOW)

combined = cta_score + vol_score + gamma_score   # range: -3 to +3

combined_read:
  +2 to +3:   "TAILWIND — systematic flows broadly supportive"
  +1:          "LEAN TAILWIND — more supportive than not, but not unanimous"
   0:          "MIXED — no clear systematic bias"
  -1:          "LEAN HEADWIND — more pressure than support"
  -2 to -3:   "HEADWIND — systematic flows broadly negative"
```

**Classification:** COMPOSITE HEURISTIC. Equal-weight combination. No claim of precision — this is a qualitative bias indicator, not a signal to trade mechanically.

---

## 5. Data Sources

| Source | Data | Cost | Latency | Reliability | Use |
|--------|------|------|---------|-------------|-----|
| **yfinance** | SPX daily OHLC (^GSPC), 200+ days history | Free | EOD | Moderate — unofficial, no SLA, occasional outages | CTA proxy, vol-control proxy |
| **FRED API** | VIX daily close (VIXCLS) | Free (API key) | EOD, next business day | Excellent — government-backed | Vol-control proxy |
| **Tradier Sandbox** | SPX option chain: OI, IV, greeks | Free (no account) | 15-min delayed | Good — documented REST API, 60 req/min | Gamma overlay |
| **OCC Series Search** | SPX per-strike OI (ground truth) | Free (no auth) | EOD (T+1) | Moderate — simple HTTP, format could change | OI cross-validation |

**Total cost: $0/month.**

**Fragility assessment:**
- yfinance is the weakest link. It scrapes Yahoo Finance and breaks periodically. Mitigation: cache the last successful fetch; if yfinance fails, report stale data with a warning. Price data is also available from FRED (SP500 series) as a backup, though with 1-day lag.
- Tradier sandbox may return simulated rather than real delayed data. Phase 1 validates this. If sandbox data is bad, fall back to yfinance for OI+IV (no greeks — compute from IV via BSM).
- OCC is a cross-check, not a primary input. If it's unavailable, skip it and note the missing validation.

---

## 6. Daily Report Format

```
══════════════════════════════════════════════════════════════
  BIG MONEY FLOW MONITOR — 2026-04-15 premarket
  SPX 5234.50 (close 04/14)
══════════════════════════════════════════════════════════════

  ▸ CTA / TREND-FOLLOWING
    Trend score:     +3 (FULL LONG)
    Flow direction:  HOLDING (no change in 5 days)
    Context:         Price above 10d, 50d, and 200d MA.
                     All timeframes aligned bullish.

  ▸ VOL-CONTROL / SYSTEMATIC ALLOCATION
    Realized vol:    12.3% (21d annualized)
    Vol regime:      LOW
    Vol trajectory:  STABLE (21d vol ≈ 63d vol)
    VIX:             16.5 | VRP: +4.2 (implied > realized)
    Allocation:      SUPPORTIVE — funds likely near max equity weight

  ▸ SPX DEALER GAMMA (ESTIMATE — see caveats)
    Net GEX:         +$7.2B (call gamma > put gamma)
    Regime:          POSITIVE — net hedging flow is stabilizing
    Flip zone:       ~5170-5200 (1.0-1.2% below spot)
    Call wall:       5300 (gamma-weighted)
    Put wall:        5150 (gamma-weighted)

  ▸ COMBINED READ
    CTA:    +1 (tailwind)
    Vol:    +1 (tailwind)
    Gamma:  +1 (tailwind)
    ───────────────────
    TAILWIND — systematic flows broadly supportive

──────────────────────────────────────────────────────────────
  CAVEATS
  • CTA proxy uses SMA(10/50/200) — real CTAs use proprietary
    variations. Regime (+3/-3) is more reliable than flow delta.
  • Vol-control thresholds are heuristic. Funds rebalance at
    different frequencies and target-vol levels.
  • Gamma estimates assume all OI is customer-long. This is
    wrong 15-30% of the time. 0DTE excluded. OI is T+1 stale.
  • Combined read is equal-weighted. No claim of precision.
  • None of this is a trading signal. It is context for
    discretionary judgment.

  Data: SPX close via yfinance | VIX via FRED | Options via
  Tradier sandbox (15m delayed) | OI check via OCC
══════════════════════════════════════════════════════════════
```

**Also output as JSON** (same data, structured) so it can be piped, logged, or consumed by other tools later.

---

## 7. Minimal Architecture

```
trader-daily-routine/
├── src/
│   ├── main.py              # Entry point: fetch → compute → print
│   ├── data.py              # All data fetching (yfinance, FRED, Tradier, OCC)
│   ├── signals.py           # CTA proxy, vol-control proxy, combined read
│   ├── gamma.py             # BSM greeks + GEX computation + regime
│   └── report.py            # Format plain-text + JSON output
├── tests/
│   ├── test_signals.py      # CTA rules, vol rules, combined logic
│   ├── test_gamma.py        # BSM formulas, GEX computation, regime classification
│   └── fixtures/            # Sample price data, sample option chains
├── output/                  # Daily report files (gitignored)
│   └── 2026-04-15.txt
├── pyproject.toml
└── docs/
    ├── dealer-gamma-exposure-technical-report.md  # (existing research)
    └── superpowers/plans/                         # (this plan)
```

**5 source files. No framework. No database. No containers.**

**Dependencies:**

```toml
[project]
name = "big-money-flow-monitor"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "httpx>=0.27",       # HTTP client for Tradier + FRED + OCC
    "numpy>=2.0",        # Moving averages, std dev
    "scipy>=1.14",       # norm.cdf for BSM
    "yfinance>=0.2",     # SPX price history
]

[project.optional-dependencies]
dev = ["pytest>=8.3", "ruff>=0.6"]
```

**Running it:**

```bash
# One-off manual run (Phase 1)
python src/main.py

# Scheduled daily run (Phase 2)
crontab -e
# 6:30 AM ET on weekdays:
# 30 6 * * 1-5 cd /path/to/project && python src/main.py >> output/$(date +\%Y-\%m-\%d).txt 2>&1
```

No APScheduler. No Docker. Cron is sufficient for a daily script.

**Data flow:**

```
main.py
  │
  ├─ data.fetch_spx_prices()      → pandas Series (200 daily closes)
  ├─ data.fetch_vix()             → float (latest VIX close)
  ├─ data.fetch_spx_chain()       → list[OptionContract] (via Tradier)
  ├─ data.fetch_occ_oi()          → dict[strike → OI] (optional cross-check)
  │
  ├─ signals.cta_proxy(prices)    → CTASignal dataclass
  ├─ signals.vol_proxy(prices, vix) → VolSignal dataclass
  ├─ gamma.spx_gamma_overlay(chain, spot) → GammaSignal dataclass
  ├─ signals.combined_read(cta, vol, gamma) → CombinedSignal dataclass
  │
  └─ report.print_report(cta, vol, gamma, combined)
     report.save_json(cta, vol, gamma, combined)
```

**Storage:** Daily output files in `output/`. Plain text + JSON. That's it. No Parquet, no DuckDB, no archival system. If we later want history, we have the JSON files.

---

## 8. Validation Approach

Validation must be proportional to the system's complexity. This is a small tool with heuristic rules. We don't need an event-study platform.

### Unit tests (build-time)

| Test | What it validates |
|------|-------------------|
| `test_cta_rules` | SMA computation, trend score at each MA cross, delta calculation. Use synthetic price series where the answer is known. |
| `test_vol_rules` | Realized vol computation, regime thresholds, trajectory classification. Use synthetic price series with known vol. |
| `test_bsm` | Gamma formula: call gamma = put gamma, gamma peaks ATM, gamma > 0 always, scale check. Put-call parity on delta. |
| `test_gex` | Synthetic 3-strike chain → verify GEX sign and magnitude. Verify flip finder on a simple profile. Verify regime classification at thresholds. |
| `test_combined` | All combinations of cta_score/vol_score/gamma_score → verify combined_read output. |

### Manual validation (first 2 weeks of use)

Each morning after the report runs:
1. Check CTA proxy against observable market behavior. If trend_score is +3 but market is selling off hard with no news catalyst, ask: did CTAs miss, or is this a countertrend day?
2. Check vol regime against VIX behavior. If vol_regime is "LOW" but VIX is spiking intraday, the regime may be transitioning.
3. Check gamma levels against actual price action. Did price reject near the call wall? Did it accelerate through the put wall?
4. Note in a simple log: `date | cta_read | vol_read | gamma_read | combined | actual_session_type | notes`

This manual log, maintained for 20-30 sessions, is the minimum viable validation. If the combined read is wrong more than it's right, revisit the rules. If it's useful, consider whether structured logging is worth automating.

### What we explicitly do NOT build for validation

- No automated event-study framework
- No backtesting engine
- No historical database of gamma levels
- No statistical significance tests
- No hold-rate analysis
- No regime-vs-realized-vol correlation study

All of these are Phase 3+ if the tool proves useful. Building validation infrastructure before validating the tool manually is backwards.

---

## 9. Deferred Features

Listed in rough priority order. None of these are in v1.

| Feature | Why deferred | When to consider |
|---------|-------------|------------------|
| **SPY / QQQ / ES** | Multi-symbol adds complexity to every function. SPX is the most important index for systematic flow analysis. | After v1 is stable and useful for 30+ days |
| **Vanna / charm overlay** | Adds modeling complexity with low-confidence output. Vanna matters for vol regime transitions but the vol-control proxy already covers that regime. | If gamma overlay proves useful and user wants more greek granularity |
| **Intraday polling** | Requires always-on process, rate limit management, framework overhead. Daily is sufficient for premarket context. | If intraday regime shifts become a pain point |
| **Dashboard / UI** | Premature. The report is ~30 lines of text. A UI adds weeks of build for marginal UX improvement. | If the tool is used daily for 60+ days and the text format becomes limiting |
| **Historical database** | JSON files in `output/` are sufficient for basic lookback. Structured storage only matters if we build research tooling. | If manual validation log suggests the signals have edge worth quantifying |
| **0DTE gamma** | Requires real-time volume data (not available for free). EOD OI is stale for 0DTE by definition. Including it would degrade confidence. | Only with IBKR or equivalent real-time data ($10/mo) |
| **Vol-adjusted CTA sizing** | More realistic CTA model: `position_size ∝ target_vol / realized_vol`. Adds another dimension to the CTA proxy. | If CTA proxy is useful but misses vol-driven deleveraging |
| **Covered-call OI adjustment** | Discount call OI by ~15-20% to account for systematic call-overwriting (QYLD, XYLD, JEPQ). | If gamma overlay is useful and call wall seems systematically too high |
| **CFTC COT integration** | Weekly Commitment of Traders data shows commercial vs speculative positioning in ES futures. Adds a 4th signal component. | If futures positioning becomes relevant to the user's trading |
| **Alerting (email/Slack)** | Daily cron already runs premarket. Adding push delivery is trivial but not needed if the user checks the terminal. | If the user wants delivery instead of pull |

---

## 10. Implementation Roadmap

### Phase 1: CTA + Vol-Control Script (3-4 days)

**Goal:** Manual script that prints the CTA and vol-control sections of the report. No options data yet.

**Files:**
- Create: `src/data.py` (yfinance + FRED fetchers)
- Create: `src/signals.py` (CTA proxy + vol-control proxy + combined read)
- Create: `src/report.py` (plain-text formatter)
- Create: `src/main.py` (entry point)
- Create: `tests/test_signals.py`
- Create: `pyproject.toml`

**Tasks:**

#### Task 1: Project setup

- [ ] Create `pyproject.toml` with dependencies
- [ ] Create directory structure (`src/`, `tests/`, `output/`)
- [ ] `pip install -e ".[dev]"` and verify
- [ ] Commit

#### Task 2: Data fetchers

- [ ] Write test: `test_fetch_spx_prices` — mock yfinance, verify returns pandas Series of 200+ floats
- [ ] Write test: `test_fetch_vix` — mock FRED API, verify returns float
- [ ] Run tests, verify fail
- [ ] Implement `data.fetch_spx_prices()` using yfinance `^GSPC`
- [ ] Implement `data.fetch_vix()` using FRED API (VIXCLS series)
- [ ] Run tests, verify pass
- [ ] Manual test: run fetchers, print output, sanity check values
- [ ] Commit

#### Task 3: CTA proxy

- [ ] Write tests:
  ```python
  def test_cta_all_bullish():
      # Price above all MAs → score +3, FULL LONG
      prices = pd.Series([100 + i*0.5 for i in range(200)])  # steady uptrend
      signal = cta_proxy(prices)
      assert signal.trend_score == 3
      assert signal.cta_regime == "FULL LONG"

  def test_cta_all_bearish():
      # Price below all MAs → score -3, FULL SHORT
      prices = pd.Series([300 - i*0.5 for i in range(200)])  # steady downtrend
      signal = cta_proxy(prices)
      assert signal.trend_score == -3
      assert signal.cta_regime == "FULL SHORT"

  def test_cta_mixed():
      # Price above 10d MA but below 50d and 200d
      # ... construct appropriate series
      signal = cta_proxy(prices)
      assert signal.trend_score == -1
      assert signal.cta_regime == "MOSTLY SHORT"

  def test_cta_flow_direction():
      # Score changed from +1 to +3 in 5 days → ADDING
      # ... test with two snapshots
  ```
- [ ] Run tests, verify fail
- [ ] Implement `signals.cta_proxy(prices: pd.Series) -> CTASignal`
- [ ] Run tests, verify pass
- [ ] Commit

#### Task 4: Vol-control proxy

- [ ] Write tests:
  ```python
  def test_vol_low_regime():
      # Construct prices with ~8% annualized vol
      signal = vol_proxy(prices, vix=14.0)
      assert signal.vol_regime == "VERY_LOW"
      assert signal.allocation_direction == "SUPPORTIVE"

  def test_vol_elevated_rising():
      # Construct prices with ~25% vol, 21d > 63d
      signal = vol_proxy(prices, vix=28.0)
      assert signal.vol_regime == "ELEVATED"
      assert signal.vol_trajectory == "RISING"
      assert signal.allocation_direction == "DELEVERAGING"

  def test_vrp_computation():
      signal = vol_proxy(prices, vix=20.0)
      # VRP = VIX - rvol_21d*100
      assert abs(signal.vrp - (20.0 - signal.rvol_21d * 100)) < 0.01
  ```
- [ ] Run tests, verify fail
- [ ] Implement `signals.vol_proxy(prices: pd.Series, vix: float) -> VolSignal`
- [ ] Run tests, verify pass
- [ ] Commit

#### Task 5: Combined read + report

- [ ] Write tests for combined scoring logic (all 27 combinations of 3×3×3 are reducible; test the boundaries)
- [ ] Run tests, verify fail
- [ ] Implement `signals.combined_read(cta, vol, gamma) -> CombinedSignal`
- [ ] Implement `report.format_text(cta, vol, gamma, combined) -> str`
- [ ] Implement `report.format_json(cta, vol, gamma, combined) -> dict`
- [ ] Run tests, verify pass
- [ ] Implement `main.py` entry point (fetch → compute → print)
- [ ] Manual end-to-end run: `python src/main.py`
- [ ] Verify output matches the report format in Section 6 (gamma section will show "N/A — not yet implemented")
- [ ] Commit

**Phase 1 exit criteria:** `python src/main.py` prints a useful premarket report with CTA and vol-control signals. Gamma section is stubbed out. All tests pass.

---

### Phase 2: Add SPX Gamma Overlay (4-5 days)

**Goal:** Add the options positioning overlay to the report. Validate Tradier data quality. Schedule daily runs.

**Files:**
- Create: `src/gamma.py` (BSM greeks + GEX computation + regime)
- Create: `tests/test_gamma.py`
- Modify: `src/data.py` (add Tradier + OCC fetchers)
- Modify: `src/main.py` (integrate gamma signal)
- Modify: `src/report.py` (add gamma + caveats sections)

**Tasks:**

#### Task 6: Tradier data validation (Phase 0 spike, embedded)

- [ ] Get Tradier sandbox API key (free signup, no brokerage needed)
- [ ] Write a throwaway script: fetch SPX chain for 1 expiry, print 10 rows
- [ ] Check: does it return OI? IV? Greeks (delta, gamma)?
- [ ] Cross-check: compare Tradier OI for 3 strikes against OCC daily OI
- [ ] Document findings. If Tradier is bad, plan yfinance fallback (OI+IV only, compute greeks via BSM)
- [ ] Commit findings as a note in the repo

#### Task 7: Tradier + OCC fetchers

- [ ] Write test: `test_parse_tradier_chain` — use fixture JSON, verify produces list of OptionContract
- [ ] Write test: `test_parse_occ_oi` — use fixture tab-delimited text, verify produces dict of strike→OI
- [ ] Run tests, verify fail
- [ ] Implement `data.fetch_spx_chain()` — Tradier API client
- [ ] Implement `data.fetch_occ_oi()` — OCC parser
- [ ] Run tests, verify pass
- [ ] Commit

#### Task 8: BSM greeks

- [ ] Write tests:
  ```python
  def test_gamma_symmetry():
      # Call gamma == put gamma at same strike/expiry/IV
      gc = bsm_gamma(S=5200, K=5200, T=0.05, r=0.043, q=0.013, sigma=0.18)
      gp = bsm_gamma(S=5200, K=5200, T=0.05, r=0.043, q=0.013, sigma=0.18)
      assert gc == gp  # Gamma is the same for calls and puts

  def test_put_call_parity_delta():
      dc = bsm_delta_call(S=5200, K=5200, T=0.05, r=0.043, q=0.013, sigma=0.18)
      dp = bsm_delta_put(S=5200, K=5200, T=0.05, r=0.043, q=0.013, sigma=0.18)
      assert abs((dc - dp) - math.exp(-0.013 * 0.05)) < 1e-6

  def test_gamma_positive():
      # Gamma must always be > 0
      for K in [4800, 5000, 5200, 5400, 5600]:
          g = bsm_gamma(S=5200, K=K, T=0.05, r=0.043, q=0.013, sigma=0.20)
          assert g > 0

  def test_gamma_scale():
      # ATM gamma for SPX should be in a reasonable range
      g = bsm_gamma(S=5200, K=5200, T=0.08, r=0.043, q=0.013, sigma=0.16)
      # GEX for 10000 OI: g * 10000 * 100 * 5200^2 * 0.01 should be in billions
      gex = g * 10000 * 100 * 5200**2 * 0.01
      assert 1e8 < gex < 1e11  # Sanity range
  ```
- [ ] Run tests, verify fail
- [ ] Implement `gamma.bsm_gamma()`, `gamma.bsm_delta_call()`, `gamma.bsm_delta_put()`
- [ ] Run tests, verify pass
- [ ] Commit

#### Task 9: GEX computation + regime

- [ ] Write tests:
  ```python
  def test_simple_gex():
      # Single call at K=5200, OI=10000, compute GEX
      chain = [OptionContract(strike=5200, expiry=..., type="call", oi=10000, iv=0.18)]
      result = compute_gex(chain, spot=5200, r=0.043, q=0.013)
      assert result.strikes[5200].call_gex > 0
      assert result.strikes[5200].put_gex == 0
      assert result.strikes[5200].net_gex > 0

  def test_flip_finder():
      # Profile that crosses zero
      profile = [(5100, -1e9), (5150, -0.5e9), (5180, 0.2e9), (5200, 1e9)]
      flip = find_gamma_flip(profile)
      assert 5150 < flip < 5180

  def test_regime_positive():
      result = classify_regime(total_gex=5e9, spot=5200, flip=5150)
      assert result == "POSITIVE"
  ```
- [ ] Run tests, verify fail
- [ ] Implement `gamma.compute_gex()`, `gamma.find_gamma_flip()`, `gamma.classify_regime()`
- [ ] Implement `gamma.spx_gamma_overlay()` — orchestrates chain → GEX → regime → GammaSignal
- [ ] Run tests, verify pass
- [ ] Commit

#### Task 10: Integration + scheduling

- [ ] Update `main.py` to call gamma overlay (replace stub)
- [ ] Update `report.py` to render gamma section + caveats
- [ ] End-to-end manual run: `python src/main.py` — verify full report
- [ ] Set up cron job: `30 6 * * 1-5` (6:30 AM ET weekdays)
- [ ] Run for 1 week, check output each morning
- [ ] Commit

**Phase 2 exit criteria:** Full premarket report runs daily via cron at 6:30 AM ET. All three signal components populated. Caveats displayed. Tests pass.

---

### Phase 3: Validation + Optional Improvements (only if useful)

**Gate:** Do not start Phase 3 unless the report has been used for 20+ trading sessions and the user finds it useful enough to invest more time.

**Possible additions (pick based on what's actually needed):**

- [ ] Structured daily log: append each day's signals + session outcome to a CSV
- [ ] Simple lookback script: "show me the last 10 days' combined reads"
- [ ] OCC fetch time fix: if OCC data isn't available at 6:30 AM, retry at 7:15 AM
- [ ] Vol-adjusted CTA sizing: add `position_size ∝ target_vol / rvol_21d` factor
- [ ] SPY/QQQ expansion: add to report if SPX overlay proves useful
- [ ] Lightweight web page: single-page HTML rendered from JSON (not a React app — just `jinja2` template)
- [ ] Alerting: pipe JSON to a Slack webhook

**What to measure during the 20-session trial:**
1. How often does the combined read match the session character? (rough: tailwind days should be orderly/up, headwind days should be volatile/down)
2. Which signal component is most informative vs most noisy?
3. Is the gamma overlay adding useful context beyond CTA + vol, or is it just adding uncertainty?
4. Are the thresholds right, or do they need recalibration?
