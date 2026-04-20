# Dealer Gamma Exposure (GEX) Technical Report

## Computing GEX, Net Gamma, Call/Put Walls, Gamma Flip, and Vanna Exposure from Public Options Data

**Target instruments:** SPX, SPY, ES, QQQ
**Purpose:** Internal trading tool reference implementation

---

## Table of Contents

1. [Gamma Exposure by Strike](#1-gamma-exposure-by-strike)
2. [Net Gamma Exposure (GEX)](#2-net-gamma-exposure-gex)
3. [Call Wall / Put Wall](#3-call-wall--put-wall)
4. [Dealer Gamma Regime](#4-dealer-gamma-regime)
5. [Vanna Exposure](#5-vanna-exposure)
6. [Charm / Expiration Effects](#6-charm--expiration-effects)
7. [Key Modeling Decisions](#7-key-modeling-decisions)
8. [Known Failure Modes](#8-known-failure-modes)
9. [Pseudocode](#9-pseudocode)

---

## 1. Gamma Exposure by Strike

### 1.1 Definition of Gamma

Gamma is the second derivative of option price with respect to the underlying:

```
Gamma = d^2(V) / d(S)^2
```

Under Black-Scholes for a European option with continuous dividend yield `q`:

```
Gamma = phi(d1) * exp(-q * T) / (S * sigma * sqrt(T))
```

where:
- `phi(d1)` is the standard normal PDF evaluated at `d1`
- `S` = spot price of the underlying
- `sigma` = implied volatility (annualized)
- `T` = time to expiration in years
- `d1 = (ln(S/K) + (r - q + sigma^2/2) * T) / (sigma * sqrt(T))`
- `r` = risk-free rate
- `q` = continuous dividend yield
- `K` = strike price

Gamma is identical for a call and a put at the same strike and expiry (put-call parity ensures this because the difference between a call and put is a forward, which has zero gamma).

### 1.2 Per-Contract Gamma Exposure

The dollar gamma exposure of a single option contract measures how many additional deltas the holder gains per $1 move in the underlying:

```
GEX_per_contract = Gamma * S * contract_multiplier
```

However, we want the dollar-denominated notional gamma, which tells us how many shares (or share-equivalents) the hedger must trade per $1 spot move. The standard formula used in practice is:

```
GEX_per_contract = Gamma * OI * contract_multiplier * S
```

More precisely, for a single strike/expiry/type combination:

```
GEX(K, T, type) = Gamma(K, T) * OI(K, T, type) * multiplier * S * sign(type)
```

where `sign(type)` encodes the dealer-side sign convention (see below).

Some implementations use a slightly different normalization. The key variants are:

**Variant A (Dollar gamma per 1% move):**
```
GEX_pct = Gamma * OI * multiplier * S^2 * 0.01
```
This answers: "How many dollars of delta hedging occurs for a 1% spot move?"

**Variant B (Share-equivalent gamma per $1 move):**
```
GEX_dollar = Gamma * OI * multiplier * S
```
This answers: "How many share-equivalents must be traded per $1 spot move?"

**Variant C (Delta-dollar gamma):**
```
GEX_notional = Gamma * OI * multiplier * S^2
```
This answers: "How many notional dollars of hedging per 1-point spot move, scaled by spot level?"

Variant A (with the `S^2 * 0.01` factor) is the most common in published GEX tools (e.g., SpotGamma, SqueezeMetrics). Variant B is the most intuitive for implementation. **Choose one and be consistent.** This report uses **Variant A** as the canonical form:

```
GEX(K, T, type) = Gamma(K, T) * OI(K, T, type) * multiplier * S^2 * 0.01 * sign(type)
```

### 1.3 Sign Convention: Dealer Side vs Customer Side

The critical question: whose gamma are we measuring?

**Customer perspective:**
- Customer long a call -> customer is long gamma
- Customer long a put -> customer is long gamma
- Gamma is always positive for the option holder

**Dealer perspective (what we want):**
- If the customer is long a call, the dealer is short that call -> dealer is **short gamma** from that call
- If the customer is long a put, the dealer is short that put -> dealer is **short gamma** from that put

Under the standard assumption ("all open interest is customer-long"), the dealer sign convention is:

```
For calls:  dealer_sign = +1   (dealer hedging a short call must BUY when S rises, SELL when S falls)
For puts:   dealer_sign = -1   (dealer hedging a short put must SELL when S rises, BUY when S falls)
```

Wait -- this needs careful explanation because it is the single most confusing aspect of GEX computation.

**Why calls get +1 and puts get -1:**

When the dealer is short a call:
- As S increases, the call delta increases, meaning the dealer's short position becomes more negative delta.
- To remain delta-neutral, the dealer must **buy** shares as S rises and **sell** as S falls.
- This is **stabilizing** flow (negative feedback). Dealer acts as a liquidity provider.
- We assign sign = **+1** so that positive GEX at a strike indicates stabilizing hedging flow.

When the dealer is short a put:
- As S increases, the put delta becomes less negative (closer to zero), meaning the dealer's short put position becomes less positive delta.
- To remain delta-neutral, the dealer must **sell** shares as S rises and **buy** as S falls.
- This is also **stabilizing** flow.
- However, by convention, we assign sign = **-1** to put GEX so that the put gamma *subtracts* from call gamma in the net calculation.

**The full sign logic:**

```
dealer_GEX(K, T) = Gamma_call(K, T) * OI_call(K, T) * multiplier * S^2 * 0.01
                  - Gamma_put(K, T)  * OI_put(K, T)  * multiplier * S^2 * 0.01
```

This nets out because:
- Above the "gamma flip" level, call gamma dominates -> net dealer gamma is positive -> stabilizing
- Below the "gamma flip" level, put gamma dominates -> net dealer gamma is negative -> destabilizing

**Important nuance:** The sign convention above assumes dealers are **short** all options. When dealers are **long** options (which does happen -- see Section 1.5), the signs flip.

### 1.4 Aggregation Across Strikes and Expiries

Total GEX at a given strike K, aggregated across all expiries:

```
GEX_total(K) = SUM over all T of [ GEX_call(K, T) - GEX_put(K, T) ]
```

Total portfolio GEX (single number):

```
GEX_portfolio = SUM over all K, T of [ GEX_call(K, T) - GEX_put(K, T) ]
```

### 1.5 The "Customer Long" Assumption

**Standard assumption:** All open interest represents a position where the customer is long and the dealer is short. This means for every contract of OI, the dealer is short one contract.

**Why this is used:**
- OI data only tells us the total number of open contracts, not who holds which side
- CBOE and exchanges do not publish directional OI (long vs short by participant type)
- Historically, retail and institutional customers are net option buyers (for hedging, speculation, yield enhancement)
- Market makers (dealers) are the natural counterparty

**Why this is wrong:**

1. **Covered call sellers:** Many large asset managers and retail investors sell calls against stock positions. Here the customer is short the call, so the dealer is long gamma on those calls. This is massive -- estimated 10-20% of SPY call OI is covered call writing.

2. **Put spreads and complex orders:** A customer buying a put spread is long one put and short another. The OI reflects both legs, but the dealer's gamma exposure nets partially.

3. **Interdealer trading:** Market makers trade with each other. This OI appears in the data but represents no customer-dealer directional flow.

4. **Institutional overwriters:** Large systematic strategies (e.g., QYLD, XYLD, JPMorgan Hedged Equity funds) sell options as part of their fund mandate. The OI from these funds represents customer-short positions.

5. **0DTE speculation:** In the 0DTE regime (2022+), both sides of the trade may be speculative. Retail sells 0DTE puts for premium; dealer is long gamma on those.

**When the assumption breaks:**
- On names with heavy call-overwriting flow (SPY, QQQ especially)
- At specific strikes that are known to be pinned by structured products
- During OPEX week when complex rolls happen
- On 0DTE where positioning is mixed

**Partial fix:** Some vendors (SqueezeMetrics, SpotGamma) use volume-weighted or heuristic adjustments:
- Use the sign of (call volume at ask - call volume at bid) as a proxy for customer direction
- Use put/call volume ratio as a scaling factor
- Apply known positions from 13F/institutional disclosures
- Use CFTC Commitments of Traders (for futures options)

### 1.6 Weighting by Expiry

Near-term options have higher gamma than far-term options (gamma is inversely proportional to `sqrt(T)`). This means:

- 0DTE and weekly options dominate the GEX landscape despite potentially lower OI
- Monthly and quarterly options contribute less gamma per contract but may have massive OI

**Practical approaches:**

1. **No weighting (raw sum):** Simply sum GEX across all expiries. This is the most common approach and what the formula already does (since gamma naturally decays with time, this implicitly weights near-term more).

2. **Expiry bucketing:** Compute GEX separately for 0DTE, weekly (1-7 DTE), monthly (7-45 DTE), and LEAPS (>45 DTE). Display as stacked charts.

3. **DTE-weighted:** Apply a weight function `w(T) = exp(-lambda * T)` or `w(T) = 1/sqrt(T)` to further emphasize near-term. Generally unnecessary because gamma already does this.

4. **Exclude distant expiries:** Only include options with DTE < 60 (or 45, or 30). Far-dated options contribute negligible gamma and add noise.

**Recommendation:** Use raw aggregation (approach 1) for the headline GEX number. Show expiry-bucketed GEX as supplementary information. For 0DTE-sensitive analysis, compute a separate 0DTE-only GEX.

---

## 2. Net Gamma Exposure (GEX)

### 2.1 GEX as a Function of Spot Price

The key insight: gamma changes as spot moves. A GEX snapshot at current spot is useful but incomplete. The **GEX profile** shows how net dealer gamma would evolve across a range of hypothetical spot prices.

For each hypothetical spot price `S_h`:

```
GEX_profile(S_h) = SUM over all K, T of [
    Gamma_call(S_h, K, T, sigma_call) * OI_call(K, T) * multiplier * S_h^2 * 0.01
  - Gamma_put(S_h, K, T, sigma_put)  * OI_put(K, T)  * multiplier * S_h^2 * 0.01
]
```

where `Gamma(S_h, K, T, sigma)` is recalculated at each hypothetical spot `S_h` using the BSM formula with the implied volatility for that specific option.

**Key decision:** Do you hold IV constant or adjust it as you sweep `S_h`?

- **Constant IV (sticky strike):** Each option keeps its current IV as you move `S_h`. Simple but unrealistic for large moves.
- **Sticky delta:** IV adjusts along the skew surface as `S_h` changes. More realistic but requires modeling the skew dynamics.
- **Sticky moneyness:** IV stays constant for a given moneyness `K/S`. Compromise approach.

**Recommendation:** Use sticky strike for simplicity. The GEX profile is already an approximation; adding skew dynamics adds complexity without proportional accuracy gain unless you have a reliable local vol or SABR model.

### 2.2 The GEX Profile Curve

The GEX profile typically looks like this for SPX/SPY:

```
GEX
 ^
 |        /\
 |       /  \
 |      /    \___
 |     /         \
 |----/-----------|--------> Spot Price
 |  /             |
 | /    Negative  | Positive
 |/     Gamma     | Gamma
 +------|---------|--------->
      put wall   flip   call wall
```

- **Left side (below flip):** Put gamma dominates. Net dealer gamma is negative. Dealers must hedge in a destabilizing way (sell into drops, buy into rallies within the negative zone).
- **Right side (above flip):** Call gamma dominates. Net dealer gamma is positive. Dealers hedge in a stabilizing way (buy dips, sell rips).
- **Gamma flip point:** Where the curve crosses zero.

### 2.3 Identifying the Gamma Flip Point

The gamma flip level is the spot price `S*` where:

```
GEX_profile(S*) = 0
```

Numerically: sweep `S_h` from some lower bound to upper bound, compute `GEX_profile(S_h)` at each point, and find where it crosses zero. Use bisection or interpolation.

In practice, the gamma flip is usually:
- Near the highest-concentration put strike (put wall vicinity)
- Below current spot during a bull market
- Near or above current spot during a bear market or high-vol regime
- Typically 1-5% below ATM in normal conditions for SPX

### 2.4 Sensitivity of the Flip Point

The flip point is sensitive to:

1. **OI changes:** A large put buyer at a new strike can shift the flip up significantly.
2. **The customer-long assumption:** If 20% of call OI is actually customer-short (covered calls), the flip point moves lower because call GEX is overstated.
3. **0DTE inclusion/exclusion:** 0DTE gamma is enormous but disappears by EOD. Including it can distort the multi-day flip level.
4. **IV levels:** Higher IV -> gamma spreads out (flatter peak) -> flip point can shift.
5. **DTE of nearby expiration:** The day before monthly OPEX, the about-to-expire options dominate everything.

---

## 3. Call Wall / Put Wall

### 3.1 Definitions

There are multiple definitions in use. Each captures something different.

**Definition 1: Highest OI Strike**
```
Call_Wall_OI = argmax_K { OI_call(K) }     (summed across all expiries)
Put_Wall_OI  = argmax_K { OI_put(K) }
```

**Definition 2: Highest Gamma Strike**
```
Call_Wall_Gamma = argmax_K { SUM_T [ Gamma_call(K,T) * OI_call(K,T) ] }
Put_Wall_Gamma  = argmax_K { SUM_T [ Gamma_put(K,T)  * OI_put(K,T)  ] }
```

**Definition 3: Highest GEX Strike (dollar gamma)**
```
Call_Wall_GEX = argmax_K { SUM_T [ Gamma_call(K,T) * OI_call(K,T) * S^2 * 0.01 * multiplier ] }
Put_Wall_GEX  = argmax_K { SUM_T [ Gamma_put(K,T)  * OI_put(K,T)  * S^2 * 0.01 * multiplier ] }
```

**Definition 4: Highest Net GEX Strike (SpotGamma-style)**
```
Key_Gamma_Strike = argmax_K { |GEX_total(K)| }
```

### 3.2 Which Definition to Use

| Definition | Pros | Cons |
|---|---|---|
| Highest OI | Simple, stable, doesn't depend on greeks | Ignores moneyness; a deep OTM strike with huge OI may not matter |
| Highest Gamma | Weights by how much hedging actually occurs | Sensitive to spot; changes intraday |
| Highest GEX ($) | Proper dollar-weighted measure | Same sensitivity + depends on S^2 scaling |

**Recommendation for a trading tool:**

- Use **Definition 2 (Gamma-weighted)** as the primary call/put wall
- Display **Definition 1 (OI-based)** as a supplementary reference
- Only consider strikes within a reasonable range (e.g., +/- 10% of spot for SPX)
- Filter to near-term expiries (< 45 DTE) for the wall computation; far-dated OI distorts the picture

### 3.3 Behavioral Interpretation

**Call Wall:** Acts as a **resistance / magnet** level. As spot approaches the call wall:
- Dealer short call delta increases -> dealers buy shares -> but as gamma increases near the strike, the delta hedging intensifies
- This creates a pinning effect if the call wall is near expiry
- More precisely: the call wall is where dealer gamma hedging flow is highest, creating a mean-reversion attractor

**Put Wall:** Acts as a **support** level via the same mechanism, but:
- If the put wall breaks (spot falls below), the positive dealer gamma from puts flips into negative territory and accelerates the selloff (dealers sell into the decline)
- This is why put wall breaks are more violent than call wall breaks

---

## 4. Dealer Gamma Regime

### 4.1 Positive Gamma Regime

When net dealer gamma is positive (typical when spot > gamma flip):

- Dealers are short calls with large gamma
- As spot rises: call delta increases -> dealer is shorter delta -> dealer must **buy** stock
- As spot falls: call delta decreases -> dealer must **sell** stock
- Net effect: **Mean-reverting.** Dealer hedging dampens moves.
- Realized volatility tends to be **lower** than implied
- Intraday: expect range-bound, low-vol, orderly tape
- Overnight gaps get faded

**Quantitative signature:** When GEX is positive and large (> $5B notional for SPX), daily realized vol often compresses 20-40% below implied vol.

### 4.2 Negative Gamma Regime

When net dealer gamma is negative (typical when spot < gamma flip):

- Dealers are short puts with large gamma
- As spot falls: put delta becomes more negative -> dealer's short put position has increasingly positive delta -> dealer must **sell** stock to hedge
- As spot rises: put delta becomes less negative -> dealer must **buy** stock
- Net effect: **Trend-amplifying.** Dealer hedging adds fuel to moves.
- Realized volatility tends to be **higher** than implied
- Intraday: expect trending, volatile, dislocated tape
- Gaps get extended, not faded

**Quantitative signature:** When GEX is negative (< -$2B for SPX), daily ranges expand 50-100%+ versus positive gamma days.

### 4.3 Regime Classification

```
if GEX_portfolio > threshold_positive:
    regime = "POSITIVE_GAMMA"          # Stabilizing, low vol expected
elif GEX_portfolio < threshold_negative:
    regime = "NEGATIVE_GAMMA"          # Destabilizing, high vol expected
else:
    regime = "NEUTRAL_GAMMA"           # Transitional, mixed signals
```

**Threshold calibration:** These thresholds are instrument-specific and evolve over time as the options market grows. For SPX as of 2024-2025:
- Positive: GEX > +$5 billion notional
- Strongly positive: GEX > +$10 billion
- Negative: GEX < -$2 billion
- Strongly negative: GEX < -$5 billion
- Neutral: between -$2B and +$5B

These numbers should be re-calibrated quarterly by examining the distribution of your computed GEX values.

### 4.4 Historical Reliability

The gamma regime classification has historically been:

- **Most reliable** for predicting realized vol compression in positive gamma (hit rate ~65-70%)
- **Moderately reliable** for predicting vol expansion in negative gamma (hit rate ~55-65%)
- **Unreliable** for predicting direction (GEX tells you about vol, not direction)
- **Very reliable** for predicting OPEX pinning when a strike has dominant gamma and expires soon
- **Least reliable** during major macro events (Fed, earnings for ETFs, geopolitical shocks) where fundamental flows overwhelm gamma flows

Key failure periods:
- Feb 2018 (Volmageddon): GEX was positive but the vol-selling unwind overwhelmed dealer hedging
- March 2020: GEX went extremely negative and correctly predicted vol explosion, but the magnitude was unprecedented
- 2022 bear market: GEX was often negative, correctly identifying the volatile regime, but the flip point was unstable
- 0DTE era (2023+): Intraday gamma shifts so rapidly that EOD GEX snapshots miss intraday regime transitions

---

## 5. Vanna Exposure

### 5.1 Definition of Vanna

Vanna is the sensitivity of delta to changes in implied volatility (or equivalently, the sensitivity of vega to changes in spot):

```
Vanna = d(Delta)/d(sigma) = d(Vega)/d(S) = d^2(V) / (d(S) * d(sigma))
```

Under Black-Scholes (with continuous dividend yield `q`):

```
Vanna = -phi(d1) * exp(-q * T) * d2 / sigma

where:
    d1 = (ln(S/K) + (r - q + sigma^2/2) * T) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)
    phi(d1) = standard normal PDF at d1
```

**Sign behavior:**
- For OTM calls (S < K): d2 is typically negative -> Vanna is positive
- For OTM puts (S > K): d2 is typically positive -> Vanna is negative
- ATM options: Vanna is near zero (d2 ~ 0)
- Vanna peaks for slightly OTM options

### 5.2 How Vanna Creates Directional Flows

When IV falls (e.g., VIX drops):

- OTM call delta **decreases** (vanna effect: lower vol -> OTM calls become more OTM in probability space)
- Actually, let's be precise: for dealer-short OTM calls, lower IV -> call delta decreases -> dealer needs less hedge -> dealer **sells** stock

Wait -- this requires careful analysis of the full chain:

**IV decrease scenario (vol crush):**

For a dealer who is **short** calls (customer long calls):
- Lower IV -> call delta decreases -> dealer's negative delta exposure decreases -> dealer is now over-hedged (too long stock)
- Dealer must **sell** shares to re-hedge
- This creates selling pressure

For a dealer who is **short** puts (customer long puts):
- Lower IV -> put delta becomes less negative (closer to zero) -> dealer's positive delta exposure decreases -> dealer is now under-hedged
- Dealer must **sell** shares to re-hedge
- This also creates selling pressure

Wait, this is counterintuitive. Let's re-derive:

Dealer is short a put with delta = -0.30. Dealer's delta from the short put = -1 * (-0.30) = +0.30. To hedge, dealer shorts 0.30 shares. Now IV drops, put delta goes to -0.20. Dealer's delta = +0.20. Dealer's short stock position of 0.30 is too much. Dealer **buys** 0.10 shares.

Let me redo this correctly:

**For dealer short calls (standard assumption):**
- Dealer delta from short call at delta +0.40 = -0.40
- Dealer hedges by buying 0.40 shares
- IV drops: call delta decreases to +0.30 -> dealer delta = -0.30
- Dealer is overhedged by 0.10 -> dealer **sells** 0.10 shares
- **Net effect: IV drop -> selling pressure from call vanna**

**For dealer short puts (standard assumption):**
- Dealer delta from short put at delta -0.30 = +0.30
- Dealer hedges by selling (shorting) 0.30 shares
- IV drops: put delta goes to -0.20 -> dealer delta = +0.20
- Dealer is overhedged (too short) by 0.10 -> dealer **buys** 0.10 shares
- **Net effect: IV drop -> buying pressure from put vanna**

**Combined vanna flow from IV decrease:**
- Call vanna effect: selling pressure
- Put vanna effect: buying pressure
- Net depends on relative size

Since there are typically more OTM puts than OTM calls in terms of vanna-weighted OI (due to the skew and higher put OI for hedging), the **put vanna effect usually dominates**. This means:

**IV drop -> net buying pressure from vanna (dealers buy to re-hedge)**
**IV rise -> net selling pressure from vanna (dealers sell to re-hedge)**

This creates the well-known "vanna tailwind" in a falling-vol environment: as VIX drops, dealer hedging via vanna creates mechanical buying pressure, reinforcing the rally that caused VIX to drop in the first place (positive feedback loop, unlike gamma which is negative feedback in positive gamma).

### 5.3 Computing Vanna Exposure from Chain Data

```
Vanna_exposure(K, T, type) = Vanna(K, T) * OI(K, T, type) * multiplier * S * 0.01
```

The sign convention for dealer vanna:

```
Dealer_Vanna(K, T) =
    - Vanna_call(K, T) * OI_call(K, T) * multiplier * S * 0.01
    - Vanna_put(K, T)  * OI_put(K, T)  * multiplier * S * 0.01
```

(Negative because dealer is assumed short; the vanna of a short position is the negative of the long position's vanna.)

Alternatively, to get the flow direction for a given IV change:

```
Dealer_delta_change_from_IV = - SUM over all K, T, type [
    Vanna(K, T, type) * OI(K, T, type) * multiplier * delta_IV
] * dealer_sign(type)
```

### 5.4 Vanna-Spot Interaction

Vanna is strongest for options that are slightly OTM (roughly 10-25 delta). As spot moves:

- Spot rallies -> OTM puts move further OTM -> their vanna decreases; OTM calls move closer to ATM -> their vanna profile shifts
- The vanna exposure is therefore path-dependent and changes with spot

For a practical tool: recompute vanna exposure at each spot level in the profile (similar to the GEX profile).

---

## 6. Charm / Expiration Effects

### 6.1 Definition of Charm

Charm (delta decay) is the rate of change of delta with respect to time:

```
Charm = d(Delta)/d(T) = -d(Theta)/d(S)
```

Under Black-Scholes:

```
Charm_call = -phi(d1) * [ 2(r-q)T - d2 * sigma * sqrt(T) ] / [ 2 * T * sigma * sqrt(T) ]

Charm_put = Charm_call + q * exp(-qT)     (for continuous dividend)
```

A simpler intuition: as time passes, an OTM option's delta decays toward zero, and an ITM option's delta converges toward +/-1.

### 6.2 Charm Flows Near Expiration

As expiration approaches (T -> 0):

- ATM options: gamma spikes, delta is ~0.50 and very unstable
- Slightly OTM options: delta decays rapidly toward 0
- Slightly ITM options: delta converges rapidly toward 1.0 (calls) or -1.0 (puts)

**Dealer hedging flow from charm:**

For a dealer short an OTM call that will expire worthless:
- Delta was +0.20 yesterday, now +0.10 today (charm decay)
- Dealer had bought 0.20 shares to hedge; now only needs 0.10
- Dealer **sells** 0.10 shares
- This happens every day but accelerates into expiration

For a dealer short an ITM call:
- Delta was +0.80, now +0.90
- Dealer must **buy** 0.10 more shares

Net charm flow depends on the OI distribution around ATM.

### 6.3 Why OPEX Days Are Different

On OPEX (options expiration) day:

1. **Massive gamma spike at ATM strikes:** Gamma for ATM near-expiration options approaches infinity as T->0 (in theory). In practice, it's just very large.

2. **Pin risk:** The ATM gamma concentration creates a pinning effect. Any move away from the pinned strike triggers disproportionate hedging that pushes price back.

3. **Gamma collapse at 3:00 PM ET (SPX) / 4:00 PM ET (SPY):** When options expire, all their gamma vanishes instantly. The removal of this gamma can cause the underlying to "unpin" and move sharply.

4. **Mechanical roll flows:** Dealers and structured product managers roll expiring positions to the next monthly/quarterly expiry. This creates predictable flow patterns.

5. **0DTE exacerbation:** With 0DTE options now trading every day (SPX), every day is a mini-OPEX. This has structurally changed the gamma landscape since 2022.

### 6.4 Modeling Expiration Roll-Off

To model how the gamma map changes as options expire:

```
For each expiry T_i that is expiring today:
    GEX_post_expiry(K) = GEX_current(K) - GEX_from_expiry_T_i(K)
```

Compute the gamma map for tomorrow by:
1. Remove all options with DTE = 0
2. Decrease T by 1/365 for all remaining options
3. Recompute gamma for all remaining options at the new T
4. Re-aggregate

This "gamma map tomorrow" is useful for anticipating the post-OPEX regime shift. A common trade setup: if current regime is positive gamma due to large near-expiry OI, and removing that OI would flip the regime to negative gamma, then post-OPEX is likely to see a vol expansion.

---

## 7. Key Modeling Decisions

### 7.1 Black-Scholes vs Other Models

**Black-Scholes (BSM):**
- Standard for computing greeks from IV
- Sufficient for gamma/vanna/charm computation because we are using the market IV (which already incorporates skew/smile)
- The greeks are analytic (closed-form), making computation fast

**Binomial/trinomial trees:**
- Needed for American exercise options (SPY, QQQ) if you want exact delta/gamma that accounts for early exercise
- For SPX (European), BSM is exact
- In practice, the difference between BSM greeks and proper American greeks for SPY is small except for deep ITM options near expiry

**Local volatility / SABR:**
- Relevant if you want to sweep spot and adjust IV consistently
- Overkill for a first implementation
- Can be added later for the GEX profile curve

**Recommendation:** Use BSM for all greek computations. For SPY/QQQ, use the Bjerksund-Stensland (2002) approximation if you want American-adjusted greeks, or simply use BSM and accept the small error. The error is largest for deep ITM puts with high IV and long DTE -- a minor contribution to the GEX map.

### 7.2 Computing Greeks When Not Provided

Many data sources (CBOE delayed data, Yahoo Finance, Polygon.io, Tradier) provide IV but not all greeks. In this case:

**Step 1:** Extract the implied volatility `sigma` for each option.

**Step 2:** Compute greeks analytically:

```
d1 = (ln(S/K) + (r - q + sigma^2/2) * T) / (sigma * sqrt(T))
d2 = d1 - sigma * sqrt(T)

Gamma = phi(d1) / (S * sigma * sqrt(T))

Vanna = -phi(d1) * d2 / sigma
       = (Vega / S) * (1 - d1 / (sigma * sqrt(T)))

Charm_call = -phi(d1) * (2*(r-q)*T - d2*sigma*sqrt(T)) / (2*T*sigma*sqrt(T))
```

where `phi(x) = exp(-x^2/2) / sqrt(2*pi)`.

**Step 3:** If IV is not provided either, you must solve for it from the option mid-price using a root-finding algorithm (Newton-Raphson or Brent's method on the BSM pricing formula). This is slow but necessary.

### 7.3 American vs European Exercise

| Underlying | Style | Settlement | Multiplier | Notes |
|---|---|---|---|---|
| SPX | European | Cash | 100 | AM-settled for monthly, PM-settled for weeklies/0DTE |
| SPY | American | Physical | 100 | Dividend matters for early exercise |
| ES (futures) | American | Physical (futures) | 50 | Options on futures; delta is with respect to futures price |
| QQQ | American | Physical | 100 | Similar to SPY |
| XSP | European | Cash | 100 | Mini-SPX, same as SPX but 1/10th |

**For ES futures options:** The underlying is the ES futures contract, not the spot SPX. The BSM formula for options on futures (Black-76 model) should be used:

```
d1 = (ln(F/K) + (sigma^2/2) * T) / (sigma * sqrt(T))
d2 = d1 - sigma * sqrt(T)

Gamma_futures = phi(d1) * exp(-r*T) / (F * sigma * sqrt(T))
```

where `F` is the futures price and `r` is the risk-free rate used for discounting.

### 7.4 Risk-Free Rate and Dividend Assumptions

**Risk-free rate `r`:**
- Use the SOFR rate or Treasury yield matching the option's DTE
- For simplicity: use the 3-month T-bill rate for all options (currently ~4.3% as of 2025)
- The sensitivity of gamma to `r` is very small; a constant approximation is fine

**Dividend yield `q`:**
- SPY: ~1.2-1.5% annualized (varies). Use the trailing 12-month dividend yield.
- QQQ: ~0.5-0.7% annualized
- SPX: Same as SPY in terms of implied dividend
- ES: No dividend adjustment needed (futures price already incorporates dividends via cost-of-carry)

For precise computation, use discrete dividends if you have the ex-dates, but continuous yield approximation is standard.

### 7.5 Normalizing Across Instruments

To compare GEX across SPX, SPY, ES, and QQQ, normalize to a common unit. The standard is "SPX-equivalent notional":

```
SPX notional per contract = multiplier * S_spx

SPY to SPX: SPY_GEX * (S_spx / S_spy) * (100/100) = SPY_GEX * 10
    (since S_spx ~ 10 * S_spy, and both have multiplier 100)

ES to SPX: ES_GEX * (100/50) * (S_spx / S_es)
    (ES multiplier is 50; S_es ~ S_spx for front-month)
    Simplified: ES_GEX * 2   (approximately)

QQQ: Not directly comparable to SPX; keep separate or convert to dollar notional
```

A simpler and more robust approach: **convert everything to dollar notional**.

```
Dollar_GEX(K, T) = Gamma(K, T) * OI(K, T) * multiplier * S^2 * 0.01
```

This is already in dollar terms and is directly comparable across instruments if you sum them.

---

## 8. Known Failure Modes

### 8.1 Unknowable Dealer Positioning

The fundamental limitation: **we do not know who is on each side of each contract.** All GEX analysis rests on assumptions about dealer positioning. FINRA short interest, CFTC COT, and 13F data provide fragments but not a complete picture. No public data source disaggregates OI by long/short and by participant type at the strike level.

### 8.2 When the "Customer Long" Assumption Breaks

Specific known breakdowns:

1. **Systematic covered call ETFs:** QYLD, XYLD, JEPQ, JEPI, and similar funds sell massive amounts of call OI every month. This OI is customer-short. SpotGamma estimates this can be 15-25% of near-ATM call OI on SPY/QQQ.

2. **Collar funds:** Risk-reversal strategies (buy puts, sell calls) create OI where the customer is long puts but short calls. The call OI should have reversed sign.

3. **Dealer inventory accumulation:** During high-vol periods, dealers may accumulate long option inventory (they buy puts from panicking customers at rich levels and hold them). This inverts the standard assumption.

4. **Interdealer:** Up to 10-15% of OI may be interdealer, which should be excluded entirely.

### 8.3 0DTE Distortions

The explosion of 0DTE trading (SPX 0DTE volume now regularly exceeds total monthly OPEX volume) creates unique problems:

1. **OI is stale:** 0DTE OI is reported T+1. By the time you see it, those options have expired. You must use real-time volume data, not OI, for 0DTE analysis.

2. **Intraday gamma shifts:** A large 0DTE put sale at 10:00 AM creates a gamma pocket that didn't exist at the open. Your EOD GEX map misses this entirely.

3. **Gamma concentration at ATM:** 0DTE options have extreme gamma near ATM. A few thousand contracts can create more GEX than the entire monthly OI at that strike.

4. **Direction is mixed:** Unlike monthly options where customers are predominantly long, 0DTE has significant short-side retail and prop flow.

### 8.4 Stale OI (T+1 Reporting)

OCC reports open interest as of end-of-day, available the next morning. This means:

- At market open, your OI is from yesterday's close
- New positions opened today don't appear in OI until tomorrow
- Positions closed today still appear in today's OI
- Intraday, the true OI can differ by 10-30% from reported OI on active strikes

**Mitigation:** Use today's volume as a correction. If volume at a strike exceeds OI, significant OI change is occurring. Heuristic adjustment:

```
estimated_OI_intraday(K) = OI_reported(K) + alpha * (volume_today(K) - some_baseline)
```

This is imprecise. Better approach: use OI for the structural GEX map (multi-day) and volume for intraday tactical signals.

### 8.5 Intraday Volume vs OI Mismatch

On high-volume days, the relationship between volume and OI changes breaks down:

- High volume + OI increase = new positions being opened (directional signal)
- High volume + OI decrease = positions being closed (unwind signal)
- High volume + flat OI = day-trading / rolling (neutral signal)

You can't know which is happening intraday because OI updates overnight.

### 8.6 Skew and Smile Effects

The implied volatility skew affects gamma computation:

1. **OTM puts have higher IV than ATM calls.** This means OTM put gamma is computed with a different vol than ATM call gamma. This is correct behavior -- you should use each option's own IV.

2. **When sweeping spot for the GEX profile**, holding IV constant (sticky strike) means you ignore the fact that IV would change if spot actually moved. In reality, a 5% SPX drop would increase put IVs significantly, increasing put gamma and making the negative gamma regime worse than the sticky-strike model predicts.

3. **Skew steepening/flattening:** Rapid skew changes (e.g., VIX term structure inversion) change the gamma map without any change in OI or spot. Your model should re-pull IV data frequently.

### 8.7 Historical Failures of GEX Estimates

Notable periods where GEX-based signals misled:

1. **Feb 5, 2018 (Volmageddon):** GEX was moderately positive. The XIV/SVXY unwind triggered a vol spike that overwhelmed dealer gamma hedging. Lesson: GEX doesn't account for vol-product feedback loops.

2. **Sept 2020 (SoftBank):** Massive call buying created a positive GEX reading that should have been stabilizing, but the flow was one-directional and overwhelmed market makers' capacity. Lesson: GEX assumes continuous hedging; in practice, market makers hit limits.

3. **Jan 2021 (GME):** GEX computations on single stocks are far less reliable due to concentrated positioning and the assumption failures being more extreme.

4. **March 2023 (SVB/banking crisis):** GEX was moderately negative, correctly identifying vol risk, but the sector-specific nature meant SPX GEX was misleading for banking stocks.

5. **General rule:** GEX works best in "normal" markets where dealer hedging is the marginal flow. During tail events, exogenous flows (margin calls, fund liquidations, central bank intervention) dominate.

---

## 9. Pseudocode

### 9.1 Data Structures

```python
@dataclass
class OptionContract:
    strike: float           # K
    expiry: date            # Expiration date
    option_type: str        # "call" or "put"
    open_interest: int      # OI (contracts)
    implied_vol: float      # IV (annualized, e.g., 0.20 for 20%)
    volume: int             # Today's volume
    bid: float              # Bid price
    ask: float              # Ask price
    last: float             # Last trade price

@dataclass
class UnderlyingInfo:
    symbol: str             # "SPX", "SPY", "ES", "QQQ"
    spot: float             # Current spot price
    multiplier: int         # Contract multiplier (100 for SPX/SPY/QQQ, 50 for ES)
    style: str              # "european" or "american"
    dividend_yield: float   # Continuous dividend yield (annualized)
    risk_free_rate: float   # Risk-free rate (annualized)

@dataclass
class StrikeGEX:
    strike: float
    call_gex: float         # Dollar GEX from calls at this strike
    put_gex: float          # Dollar GEX from puts at this strike
    net_gex: float          # call_gex - put_gex (dealer convention)
    call_oi: int            # Total call OI at this strike
    put_oi: int             # Total put OI at this strike
    call_vanna: float       # Vanna exposure from calls
    put_vanna: float        # Vanna exposure from puts
    net_vanna: float        # Net dealer vanna
```

### 9.2 BSM Greeks Computation

```python
from math import log, sqrt, exp, pi

def norm_pdf(x: float) -> float:
    """Standard normal probability density function."""
    return exp(-0.5 * x * x) / sqrt(2.0 * pi)

def norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function."""
    # Use a library implementation (scipy.stats.norm.cdf or equivalent)
    ...

def compute_d1_d2(S, K, T, r, q, sigma):
    """Compute d1 and d2 for BSM model."""
    if T <= 0 or sigma <= 0:
        return None, None
    d1 = (log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)
    return d1, d2

def bsm_gamma(S, K, T, r, q, sigma):
    """
    Compute BSM gamma (same for calls and puts).

    Returns gamma in units of: delta change per $1 change in S.
    """
    d1, d2 = compute_d1_d2(S, K, T, r, q, sigma)
    if d1 is None:
        return 0.0
    return norm_pdf(d1) * exp(-q * T) / (S * sigma * sqrt(T))

def bsm_vanna(S, K, T, r, q, sigma):
    """
    Compute BSM vanna = d(delta)/d(sigma) = d(vega)/d(S).

    Vanna = -phi(d1) * exp(-qT) * d2 / sigma
    """
    d1, d2 = compute_d1_d2(S, K, T, r, q, sigma)
    if d1 is None:
        return 0.0
    return -norm_pdf(d1) * exp(-q * T) * d2 / sigma

def bsm_charm_call(S, K, T, r, q, sigma):
    """
    Compute BSM charm for a call = d(delta_call)/d(t) where t is calendar time.

    The full continuous-dividend call charm formula is:
        charm_call = -q * exp(-qT) * N(d1)
                     + exp(-qT) * phi(d1) * [2(r-q)T - d2*sigma*sqrt(T)]
                       / [2*T*sigma*sqrt(T)]

    Rearranging with a leading negative on the phi term:
        charm_call = -exp(-qT) * phi(d1) * [2(r-q)T - d2*sigma*sqrt(T)]
                      / [2*T*sigma*sqrt(T)]
                     + q * exp(-qT) * N(d1)

    NOTE: Verify numerically against a reference implementation (e.g.,
    QuantLib or Wolfram Alpha) during Task 3. The sign depends on whether
    the [2(r-q)T - d2*sigma*sqrt(T)] numerator is positive or negative.
    """
    d1, d2 = compute_d1_d2(S, K, T, r, q, sigma)
    if d1 is None:
        return 0.0
    charm = -exp(-q * T) * (
        norm_pdf(d1) * (2 * (r - q) * T - d2 * sigma * sqrt(T))
        / (2 * T * sigma * sqrt(T))
    ) + q * exp(-q * T) * norm_cdf(d1)
    return charm

def bsm_delta_call(S, K, T, r, q, sigma):
    """BSM call delta."""
    d1, _ = compute_d1_d2(S, K, T, r, q, sigma)
    if d1 is None:
        return 1.0 if S > K else 0.0
    return exp(-q * T) * norm_cdf(d1)

def bsm_delta_put(S, K, T, r, q, sigma):
    """BSM put delta."""
    d1, _ = compute_d1_d2(S, K, T, r, q, sigma)
    if d1 is None:
        return -1.0 if S < K else 0.0
    return exp(-q * T) * (norm_cdf(d1) - 1.0)
```

### 9.3 Computing Per-Strike Gamma Exposure

```python
def compute_strike_gex(
    options: list[OptionContract],
    underlying: UnderlyingInfo,
    today: date,
) -> dict[float, StrikeGEX]:
    """
    Compute GEX, vanna exposure, and OI for each strike,
    aggregated across all expiries.

    Returns a dict mapping strike -> StrikeGEX.
    """
    S = underlying.spot
    r = underlying.risk_free_rate
    q = underlying.dividend_yield
    mult = underlying.multiplier

    gex_by_strike: dict[float, StrikeGEX] = {}

    for opt in options:
        K = opt.strike
        T = max((opt.expiry - today).days / 365.0, 1.0 / 365.0)  # Floor at 1 day
        sigma = opt.implied_vol

        if sigma <= 0.001 or opt.open_interest == 0:
            continue

        # Compute greeks
        gamma = bsm_gamma(S, K, T, r, q, sigma)
        vanna = bsm_vanna(S, K, T, r, q, sigma)

        # Dollar GEX for this contract group (per 1% spot move)
        contract_gex = gamma * opt.open_interest * mult * S * S * 0.01

        # Vanna exposure (dollar delta change per 1% IV change)
        contract_vanna = vanna * opt.open_interest * mult * S * 0.01

        # Initialize strike entry if needed
        if K not in gex_by_strike:
            gex_by_strike[K] = StrikeGEX(
                strike=K,
                call_gex=0.0, put_gex=0.0, net_gex=0.0,
                call_oi=0, put_oi=0,
                call_vanna=0.0, put_vanna=0.0, net_vanna=0.0,
            )

        entry = gex_by_strike[K]

        if opt.option_type == "call":
            entry.call_gex += contract_gex
            entry.call_oi += opt.open_interest
            entry.call_vanna += contract_vanna
        else:  # put
            entry.put_gex += contract_gex
            entry.put_oi += opt.open_interest
            entry.put_vanna += contract_vanna

    # Compute net GEX and net vanna (dealer convention)
    for entry in gex_by_strike.values():
        # Dealer short calls -> positive GEX contribution (stabilizing when hedging)
        # Dealer short puts  -> negative GEX contribution (subtract put gamma)
        entry.net_gex = entry.call_gex - entry.put_gex

        # Dealer vanna: short calls + short puts (both contribute with sign)
        # For dealer short call: vanna effect is -(call_vanna)
        # For dealer short put:  vanna effect is -(put_vanna)
        entry.net_vanna = -(entry.call_vanna + entry.put_vanna)

    return gex_by_strike
```

### 9.4 Computing the GEX Profile as a Function of Spot

```python
def compute_gex_profile(
    options: list[OptionContract],
    underlying: UnderlyingInfo,
    today: date,
    spot_range_pct: float = 0.10,   # +/- 10% from current spot
    spot_steps: int = 200,
) -> list[tuple[float, float]]:
    """
    Compute net dealer GEX at each hypothetical spot price.

    Uses sticky-strike IV assumption (each option keeps its current IV).

    Returns list of (spot_price, net_gex_dollars) tuples.
    """
    S_current = underlying.spot
    r = underlying.risk_free_rate
    q = underlying.dividend_yield
    mult = underlying.multiplier

    S_low = S_current * (1 - spot_range_pct)
    S_high = S_current * (1 + spot_range_pct)
    spot_grid = [S_low + i * (S_high - S_low) / spot_steps for i in range(spot_steps + 1)]

    # Pre-filter options
    valid_options = [
        opt for opt in options
        if opt.implied_vol > 0.001 and opt.open_interest > 0
    ]

    # Pre-compute time-to-expiry
    option_T = {
        id(opt): max((opt.expiry - today).days / 365.0, 1.0 / 365.0)
        for opt in valid_options
    }

    profile = []

    for S_h in spot_grid:
        net_gex = 0.0

        for opt in valid_options:
            K = opt.strike
            T = option_T[id(opt)]
            sigma = opt.implied_vol

            gamma = bsm_gamma(S_h, K, T, r, q, sigma)
            contract_gex = gamma * opt.open_interest * mult * S_h * S_h * 0.01

            if opt.option_type == "call":
                net_gex += contract_gex     # Calls add to dealer GEX
            else:
                net_gex -= contract_gex     # Puts subtract from dealer GEX

        profile.append((S_h, net_gex))

    return profile
```

### 9.5 Finding the Gamma Flip Point

```python
def find_gamma_flip(
    gex_profile: list[tuple[float, float]],
) -> list[float]:
    """
    Find zero-crossing(s) of the GEX profile.

    Returns list of spot prices where net dealer gamma crosses zero.
    Multiple crossings are possible (return all).
    """
    flip_points = []

    for i in range(len(gex_profile) - 1):
        s1, g1 = gex_profile[i]
        s2, g2 = gex_profile[i + 1]

        # Check for sign change
        if g1 * g2 < 0:
            # Linear interpolation to find the zero crossing
            # g1 + (g2 - g1) * (s_flip - s1) / (s2 - s1) = 0
            # s_flip = s1 - g1 * (s2 - s1) / (g2 - g1)
            s_flip = s1 - g1 * (s2 - s1) / (g2 - g1)
            flip_points.append(s_flip)

    return flip_points


def find_primary_gamma_flip(
    gex_profile: list[tuple[float, float]],
    current_spot: float,
) -> float | None:
    """
    Find the gamma flip point closest to and below the current spot.

    This is the most tactically relevant flip level.
    """
    flips = find_gamma_flip(gex_profile)
    if not flips:
        return None

    # Prefer the flip point closest to and below current spot
    below_spot = [f for f in flips if f <= current_spot]
    if below_spot:
        return max(below_spot)  # Closest one below

    # If all flip points are above spot, return the closest one
    return min(flips, key=lambda f: abs(f - current_spot))
```

### 9.6 Identifying Call Wall, Put Wall, Key Gamma Strike

```python
def find_walls_and_key_strikes(
    gex_by_strike: dict[float, StrikeGEX],
    current_spot: float,
    range_pct: float = 0.10,  # Only consider strikes within +/- 10% of spot
) -> dict:
    """
    Identify call wall, put wall, and key gamma strike.

    Returns dict with:
        call_wall_gamma: strike with highest call gamma exposure
        put_wall_gamma:  strike with highest put gamma exposure
        call_wall_oi:    strike with highest call OI
        put_wall_oi:     strike with highest put OI
        key_gamma_strike: strike with highest absolute net GEX
        top_call_strikes: top 5 call gamma strikes
        top_put_strikes:  top 5 put gamma strikes
    """
    S = current_spot
    S_low = S * (1 - range_pct)
    S_high = S * (1 + range_pct)

    # Filter to relevant range
    strikes = {
        K: entry for K, entry in gex_by_strike.items()
        if S_low <= K <= S_high
    }

    if not strikes:
        return {}

    entries = list(strikes.values())

    # Call wall (gamma-weighted): highest call GEX strike
    call_wall_gamma = max(entries, key=lambda e: e.call_gex).strike

    # Put wall (gamma-weighted): highest put GEX strike
    put_wall_gamma = max(entries, key=lambda e: e.put_gex).strike

    # Call wall (OI-based): highest call OI strike
    call_wall_oi = max(entries, key=lambda e: e.call_oi).strike

    # Put wall (OI-based): highest put OI strike
    put_wall_oi = max(entries, key=lambda e: e.put_oi).strike

    # Key gamma strike: highest absolute net GEX
    key_gamma_strike = max(entries, key=lambda e: abs(e.net_gex)).strike

    # Top N strikes for each
    top_call = sorted(entries, key=lambda e: e.call_gex, reverse=True)[:5]
    top_put = sorted(entries, key=lambda e: e.put_gex, reverse=True)[:5]

    return {
        "call_wall_gamma": call_wall_gamma,
        "put_wall_gamma": put_wall_gamma,
        "call_wall_oi": call_wall_oi,
        "put_wall_oi": put_wall_oi,
        "key_gamma_strike": key_gamma_strike,
        "top_call_strikes": [(e.strike, e.call_gex, e.call_oi) for e in top_call],
        "top_put_strikes": [(e.strike, e.put_gex, e.put_oi) for e in top_put],
    }
```

### 9.7 Classifying Dealer Regime

```python
@dataclass
class GammaRegime:
    regime: str                     # "POSITIVE", "NEGATIVE", "NEUTRAL"
    net_gex: float                  # Total net dealer GEX in dollars
    gamma_flip: float | None        # Gamma flip level (spot price)
    spot_vs_flip: str               # "ABOVE", "BELOW", "AT"
    flip_distance_pct: float        # Distance from spot to flip as % of spot
    call_wall: float                # Call wall strike
    put_wall: float                 # Put wall strike
    regime_strength: str            # "STRONG", "MODERATE", "WEAK"
    expected_vol_bias: str          # "LOW", "HIGH", "NEUTRAL"

def classify_regime(
    gex_by_strike: dict[float, StrikeGEX],
    gex_profile: list[tuple[float, float]],
    underlying: UnderlyingInfo,
    # Thresholds (calibrate these for your instrument)
    strong_positive_threshold: float = 10e9,     # $10B for SPX
    positive_threshold: float = 5e9,             # $5B for SPX
    negative_threshold: float = -2e9,            # -$2B for SPX
    strong_negative_threshold: float = -5e9,     # -$5B for SPX
) -> GammaRegime:
    """
    Classify the current dealer gamma regime.
    """
    S = underlying.spot

    # Total net GEX
    net_gex = sum(entry.net_gex for entry in gex_by_strike.values())

    # Find gamma flip
    gamma_flip = find_primary_gamma_flip(gex_profile, S)

    # Spot vs flip
    if gamma_flip is None:
        spot_vs_flip = "UNKNOWN"
        flip_distance_pct = 0.0
    elif S > gamma_flip * 1.001:
        spot_vs_flip = "ABOVE"
        flip_distance_pct = (S - gamma_flip) / S
    elif S < gamma_flip * 0.999:
        spot_vs_flip = "BELOW"
        flip_distance_pct = (gamma_flip - S) / S
    else:
        spot_vs_flip = "AT"
        flip_distance_pct = 0.0

    # Walls
    walls = find_walls_and_key_strikes(gex_by_strike, S)
    call_wall = walls.get("call_wall_gamma", 0)
    put_wall = walls.get("put_wall_gamma", 0)

    # Classify regime
    if net_gex >= strong_positive_threshold:
        regime = "POSITIVE"
        strength = "STRONG"
        vol_bias = "LOW"
    elif net_gex >= positive_threshold:
        regime = "POSITIVE"
        strength = "MODERATE"
        vol_bias = "LOW"
    elif net_gex <= strong_negative_threshold:
        regime = "NEGATIVE"
        strength = "STRONG"
        vol_bias = "HIGH"
    elif net_gex <= negative_threshold:
        regime = "NEGATIVE"
        strength = "MODERATE"
        vol_bias = "HIGH"
    else:
        regime = "NEUTRAL"
        strength = "WEAK"
        vol_bias = "NEUTRAL"

    # Override with flip-based classification if contradictory
    # (e.g., net GEX is slightly positive but spot is below flip)
    if spot_vs_flip == "BELOW" and regime == "POSITIVE" and strength == "WEAK":
        regime = "NEUTRAL"
        vol_bias = "NEUTRAL"

    return GammaRegime(
        regime=regime,
        net_gex=net_gex,
        gamma_flip=gamma_flip,
        spot_vs_flip=spot_vs_flip,
        flip_distance_pct=flip_distance_pct,
        call_wall=call_wall,
        put_wall=put_wall,
        regime_strength=strength,
        expected_vol_bias=vol_bias,
    )
```

### 9.8 Full Pipeline

```python
def run_gex_analysis(
    options_chain: list[OptionContract],
    underlying: UnderlyingInfo,
    today: date,
) -> dict:
    """
    Full GEX analysis pipeline.

    Returns a comprehensive dict with all computed values.
    """
    # Step 1: Per-strike GEX
    gex_by_strike = compute_strike_gex(options_chain, underlying, today)

    # Step 2: GEX profile (sweep spot)
    gex_profile = compute_gex_profile(
        options_chain, underlying, today,
        spot_range_pct=0.10,
        spot_steps=200,
    )

    # Step 3: Walls and key strikes
    walls = find_walls_and_key_strikes(gex_by_strike, underlying.spot)

    # Step 4: Regime classification
    regime = classify_regime(gex_by_strike, gex_profile, underlying)

    # Step 5: Vanna summary
    total_vanna = sum(entry.net_vanna for entry in gex_by_strike.values())

    # Step 6: Expiry bucketing
    dte_buckets = {"0DTE": 0.0, "weekly": 0.0, "monthly": 0.0, "far": 0.0}
    for opt in options_chain:
        dte = (opt.expiry - today).days
        if dte <= 0:
            bucket = "0DTE"
        elif dte <= 7:
            bucket = "weekly"
        elif dte <= 45:
            bucket = "monthly"
        else:
            bucket = "far"

        K = opt.strike
        T = max(dte / 365.0, 1.0 / 365.0)
        sigma = opt.implied_vol
        if sigma <= 0.001 or opt.open_interest == 0:
            continue

        gamma = bsm_gamma(underlying.spot, K, T,
                          underlying.risk_free_rate,
                          underlying.dividend_yield, sigma)
        gex = gamma * opt.open_interest * underlying.multiplier * underlying.spot**2 * 0.01
        sign = 1.0 if opt.option_type == "call" else -1.0
        dte_buckets[bucket] += gex * sign

    return {
        "spot": underlying.spot,
        "symbol": underlying.symbol,
        "timestamp": today.isoformat(),
        "net_gex": regime.net_gex,
        "regime": regime.regime,
        "regime_strength": regime.regime_strength,
        "gamma_flip": regime.gamma_flip,
        "spot_vs_flip": regime.spot_vs_flip,
        "flip_distance_pct": regime.flip_distance_pct,
        "call_wall": regime.call_wall,
        "put_wall": regime.put_wall,
        "expected_vol_bias": regime.expected_vol_bias,
        "total_dealer_vanna": total_vanna,
        "gex_by_dte_bucket": dte_buckets,
        "gex_profile": gex_profile,
        "strikes": gex_by_strike,
        "walls": walls,
    }
```

---

## Appendix A: Verification Checklist

Before trusting your implementation, verify:

1. **Gamma symmetry:** Gamma for a call and put at the same strike/expiry/IV should be identical. If they differ, your BSM implementation has a bug.

2. **Put-call parity on delta:** `delta_call - delta_put = exp(-qT)`. If this fails, check your dividend/rate handling.

3. **GEX sign at known strikes:** At a strike with large call OI and negligible put OI, the net GEX should be positive. At a strike with large put OI and negligible call OI, the net GEX should be negative.

4. **GEX scale sanity:** For SPX, total net GEX should typically be in the range of -$10B to +$15B. If you get numbers in the trillions or in the thousands, check your multiplier and S^2 factor.

5. **Gamma flip location:** The flip should typically be within 0-8% below spot in normal markets. If it's way above spot, either the market is in a strong negative gamma regime (plausible during crashes) or your signs are wrong.

6. **Expiry gamma decay:** Gamma should increase as DTE approaches 0 for ATM options. If your near-term gamma is lower than far-term at the same strike, check your T floor.

---

## Appendix B: Data Sources

| Source | OI | Volume | IV | Greeks | Real-time | Notes |
|---|---|---|---|---|---|---|
| CBOE DataShop | Yes | Yes | Yes | No | Delayed 15 min | Official exchange data |
| Polygon.io | Yes | Yes | Yes | Yes | Depends on plan | Good API, greeks may be stale |
| Tradier | Yes | Yes | Yes | Yes | Depends on plan | Free tier available |
| IBKR TWS | Yes | Yes | Yes | Yes | Real-time | Best for live trading integration |
| Yahoo Finance | Yes | Yes | Yes | No | Delayed | Free but rate-limited, no API guarantee |
| OCC | Yes | No | No | No | T+1 | Official OI source |
| OptionMetrics (IvyDB) | Yes | Yes | Yes | Yes | EOD | Academic/institutional; gold standard for research |
| Quandl/Nasdaq Data Link | Yes | Yes | Some | Some | EOD | Depends on dataset |
| ORATS | Yes | Yes | Yes | Yes | Near real-time | Purpose-built for options analytics |

---

## Appendix C: Notation Reference

| Symbol | Meaning |
|---|---|
| S | Spot price of underlying |
| K | Strike price |
| T | Time to expiration (years) |
| r | Risk-free rate (annualized, continuous) |
| q | Dividend yield (annualized, continuous) |
| sigma | Implied volatility (annualized) |
| phi(x) | Standard normal PDF |
| Phi(x) | Standard normal CDF |
| OI | Open interest (number of contracts) |
| GEX | Gamma exposure (dollar-denominated) |
| d1, d2 | BSM intermediate variables |
| mult | Contract multiplier (100 for SPX/SPY/QQQ, 50 for ES) |
