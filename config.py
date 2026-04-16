"""
CTA Trend Proxy — Configuration

Futures universe, signal parameters, CFTC COT mappings, and benchmark definitions.
Baseline model mirrors SG Trend Indicator methodology where possible.
"""

# ---------------------------------------------------------------------------
# Futures universe
#
# Each entry maps a short code to:
#   ticker          — yfinance symbol (continuous front-month or spot proxy)
#   name            — human-readable name
#   sector          — asset class for equal-risk sector weighting
#   cot_code        — CFTC contract code for COT lookups
#   cot_report      — "TFF" (financials → Leveraged Funds) or
#                     "DISAGG" (physical commodities → Managed Money)
#   cot_category    — the trader category to pull from that report
#
# NOTE on cot_report mapping:
#   Financial futures (equity indices, bonds, FX, rates) use the Traders in
#   Financial Futures (TFF) framework. CTA-like participants are classified
#   under "Leveraged Funds" in TFF, NOT "Managed Money."
#   Physical commodities (energy, metals, agriculture) use the Disaggregated
#   report where the relevant category is "Managed Money."
#   Source: https://www.cftc.gov/idc/groups/public/%40commitmentsoftraders/documents/file/tfmexplanatorynotes.pdf
# ---------------------------------------------------------------------------
FUTURES_UNIVERSE = {
    # --- Equity Indices (TFF → Leveraged Funds) ---
    "ES": {
        "ticker": "ES=F",
        "name": "S&P 500 E-mini",
        "sector": "Equity Index",
        "cot_code": "13874A",
        "cot_report": "TFF",
        "cot_category": "Lev_Money_Positions",
        "contract_multiplier": 50.0,
        "contract_unit": "index points",
        "quote_currency": "USD",
    },
    "NQ": {
        "ticker": "NQ=F",
        "name": "Nasdaq 100 E-mini",
        "sector": "Equity Index",
        "cot_code": "209742",
        "cot_report": "TFF",
        "cot_category": "Lev_Money_Positions",
        "contract_multiplier": 20.0,
        "contract_unit": "index points",
        "quote_currency": "USD",
    },
    "YM": {
        "ticker": "YM=F",
        "name": "Dow Jones E-mini",
        "sector": "Equity Index",
        "cot_code": "124603",
        "cot_report": "TFF",
        "cot_category": "Lev_Money_Positions",
        "contract_multiplier": 5.0,
        "contract_unit": "index points",
        "quote_currency": "USD",
    },
    "RTY": {
        "ticker": "RTY=F",
        "name": "Russell 2000 E-mini",
        "sector": "Equity Index",
        "cot_code": "239742",
        "cot_report": "TFF",
        "cot_category": "Lev_Money_Positions",
        "contract_multiplier": 50.0,
        "contract_unit": "index points",
        "quote_currency": "USD",
    },

    # --- Fixed Income (TFF → Leveraged Funds) ---
    "ZB": {
        "ticker": "ZB=F",
        "name": "US 30Y T-Bond",
        "sector": "Fixed Income",
        "cot_code": "020601",
        "cot_report": "TFF",
        "cot_category": "Lev_Money_Positions",
        "contract_multiplier": 1000.0,
        "contract_unit": "price points",
        "quote_currency": "USD",
    },
    "ZN": {
        "ticker": "ZN=F",
        "name": "US 10Y T-Note",
        "sector": "Fixed Income",
        "cot_code": "043602",
        "cot_report": "TFF",
        "cot_category": "Lev_Money_Positions",
        "contract_multiplier": 1000.0,
        "contract_unit": "price points",
        "quote_currency": "USD",
    },
    "ZF": {
        "ticker": "ZF=F",
        "name": "US 5Y T-Note",
        "sector": "Fixed Income",
        "cot_code": "044601",
        "cot_report": "TFF",
        "cot_category": "Lev_Money_Positions",
        "contract_multiplier": 1000.0,
        "contract_unit": "price points",
        "quote_currency": "USD",
    },

    # --- Energy (Disaggregated → Managed Money) ---
    "CL": {
        "ticker": "CL=F",
        "name": "Crude Oil WTI",
        "sector": "Energy",
        "cot_code": "067651",
        "cot_report": "DISAGG",
        "cot_category": "M_Money_Positions",
        "contract_multiplier": 1000.0,
        "contract_unit": "barrels",
        "quote_currency": "USD",
    },
    "NG": {
        "ticker": "NG=F",
        "name": "Natural Gas",
        "sector": "Energy",
        "cot_code": "023651",
        "cot_report": "DISAGG",
        "cot_category": "M_Money_Positions",
        "contract_multiplier": 10000.0,
        "contract_unit": "mmBtu",
        "quote_currency": "USD",
    },
    "RB": {
        "ticker": "RB=F",
        "name": "RBOB Gasoline",
        "sector": "Energy",
        "cot_code": "111659",
        "cot_report": "DISAGG",
        "cot_category": "M_Money_Positions",
        "contract_multiplier": 42000.0,
        "contract_unit": "gallons",
        "quote_currency": "USD",
    },

    # --- Metals (Disaggregated → Managed Money) ---
    "GC": {
        "ticker": "GC=F",
        "name": "Gold",
        "sector": "Metals",
        "cot_code": "088691",
        "cot_report": "DISAGG",
        "cot_category": "M_Money_Positions",
        "contract_multiplier": 100.0,
        "contract_unit": "troy ounces",
        "quote_currency": "USD",
    },
    "SI": {
        "ticker": "SI=F",
        "name": "Silver",
        "sector": "Metals",
        "cot_code": "084691",
        "cot_report": "DISAGG",
        "cot_category": "M_Money_Positions",
        "contract_multiplier": 5000.0,
        "contract_unit": "troy ounces",
        "quote_currency": "USD",
    },
    "HG": {
        "ticker": "HG=F",
        "name": "Copper",
        "sector": "Metals",
        "cot_code": "085692",
        "cot_report": "DISAGG",
        "cot_category": "M_Money_Positions",
        "contract_multiplier": 25000.0,
        "contract_unit": "pounds",
        "quote_currency": "USD",
    },

    # --- Agriculture (Disaggregated → Managed Money) ---
    "ZC": {
        "ticker": "ZC=F",
        "name": "Corn",
        "sector": "Agriculture",
        "cot_code": "002602",
        "cot_report": "DISAGG",
        "cot_category": "M_Money_Positions",
        "contract_multiplier": 5000.0,
        "contract_unit": "bushels",
        "quote_currency": "USD",
    },
    "ZS": {
        "ticker": "ZS=F",
        "name": "Soybeans",
        "sector": "Agriculture",
        "cot_code": "005602",
        "cot_report": "DISAGG",
        "cot_category": "M_Money_Positions",
        "contract_multiplier": 5000.0,
        "contract_unit": "bushels",
        "quote_currency": "USD",
    },
    "ZW": {
        "ticker": "ZW=F",
        "name": "Wheat",
        "sector": "Agriculture",
        "cot_code": "001602",
        "cot_report": "DISAGG",
        "cot_category": "M_Money_Positions",
        "contract_multiplier": 5000.0,
        "contract_unit": "bushels",
        "quote_currency": "USD",
    },

    # --- FX (TFF → Leveraged Funds) ---
    "6E": {
        "ticker": "6E=F",
        "name": "Euro FX",
        "sector": "FX",
        "cot_code": "099741",
        "cot_report": "TFF",
        "cot_category": "Lev_Money_Positions",
        "contract_multiplier": 125000.0,
        "contract_unit": "euros",
        "quote_currency": "USD",
    },
    "6J": {
        "ticker": "6J=F",
        "name": "Japanese Yen",
        "sector": "FX",
        "cot_code": "097741",
        "cot_report": "TFF",
        "cot_category": "Lev_Money_Positions",
        "contract_multiplier": 12500000.0,
        "contract_unit": "yen",
        "quote_currency": "USD",
    },
    "6B": {
        "ticker": "6B=F",
        "name": "British Pound",
        "sector": "FX",
        "cot_code": "096742",
        "cot_report": "TFF",
        "cot_category": "Lev_Money_Positions",
        "contract_multiplier": 62500.0,
        "contract_unit": "pounds sterling",
        "quote_currency": "USD",
    },
    "6A": {
        "ticker": "6A=F",
        "name": "Australian Dollar",
        "sector": "FX",
        "cot_code": "232741",
        "cot_report": "TFF",
        "cot_category": "Lev_Money_Positions",
        "contract_multiplier": 100000.0,
        "contract_unit": "australian dollars",
        "quote_currency": "USD",
    },
    "DX": {
        "ticker": "DX-Y.NYB",
        "name": "US Dollar Index",
        "sector": "FX",
        "cot_code": "098662",
        "cot_report": "TFF",
        "cot_category": "Lev_Money_Positions",
        "contract_multiplier": 1000.0,
        "contract_unit": "index points",
        "quote_currency": "USD",
    },
}

# Sector list for equal-risk weighting
SECTORS = sorted(set(v["sector"] for v in FUTURES_UNIVERSE.values()))

# ---------------------------------------------------------------------------
# Trend model parameters — SG Trend Indicator baseline
#
# SG uses a short-term (20d) and long-term (120d) moving average.
# Signal is binary per horizon: +1 if price > MA, -1 if price < MA.
# Composite = equal weight of both horizons → {-1, 0, +1}.
#
# The 5-horizon blend (20/60/125/250/500) is a future enhancement,
# added only if the baseline underperforms out-of-sample.
# ---------------------------------------------------------------------------
TREND_PARAMS = {
    "short_window": 20,    # ~1 month
    "long_window": 120,    # ~6 months
}

# ---------------------------------------------------------------------------
# Volatility parameters
#
# SG methodology: 3-month EWMA volatility, 15% annualized vol target.
# Source: SG Trend Indicator Methodology Summary
# ---------------------------------------------------------------------------
VOL_PARAMS = {
    "ewma_span": 63,            # 3-month EWMA (~63 trading days)
    "target_vol": 0.15,         # 15% annualized vol target per position
    "trading_days_per_year": 252,
}

# ---------------------------------------------------------------------------
# Portfolio construction
# ---------------------------------------------------------------------------
PORTFOLIO_PARAMS = {
    "sector_weight_method": "equal_risk",  # equal risk budget across sectors
    "rebalance_freq": "M",                 # monthly rebalancing
    "max_leverage": 5.0,                   # hard cap on gross leverage (legacy alias)
    "max_gross_multiple": 5.0,             # explicit name for headroom cap
}

# ---------------------------------------------------------------------------
# Composite validation scoring — weights for each validator
# ---------------------------------------------------------------------------
VALIDATION_WEIGHTS = {
    "signal": 0.40,    # SG signal agreement (highest when available)
    "position": 0.35,  # COT directional agreement
    "return": 0.25,    # Benchmark ETF correlation
}

# ---------------------------------------------------------------------------
# Threshold distance buckets — actionable zones for distance-to-flip
# ---------------------------------------------------------------------------
THRESHOLD_BUCKETS = {
    "very_near": 1.0,   # < 1% from flip
    "near": 2.5,        # 1-2.5%
    "moderate": 5.0,    # 2.5-5%
    # > 5% = "far"
}

# ---------------------------------------------------------------------------
# Crowding percentile — lookback for historical ranking
# ---------------------------------------------------------------------------
CROWDING_LOOKBACK_DAYS = 252  # 1 year for percentile ranking

# ---------------------------------------------------------------------------
# SG Trend Index 2026 Constituents — for reference and context
# Source: https://wholesale.banking.societegenerale.com/fileadmin/indices_feeds/SG_Trend_Index_Constituents.pdf
# ---------------------------------------------------------------------------
SG_TREND_INDEX_FUNDS = [
    {"name": "Man AHL",          "program": "Man AHL Alpha",              "aum_bn_approx": 30.0},
    {"name": "Graham Capital",   "program": "Tactical Trend",             "aum_bn_approx": 16.0},
    {"name": "AQR Capital",      "program": "Managed Futures",            "aum_bn_approx": 14.0},
    {"name": "Aspect Capital",   "program": "Core Diversified",           "aum_bn_approx":  9.0},
    {"name": "Winton Capital",   "program": "Winton Trend",               "aum_bn_approx":  7.5},
    {"name": "Transtrend",       "program": "DTP Enhanced Risk USD",      "aum_bn_approx":  6.0},
    {"name": "Lynx Asset Mgmt",  "program": "Lynx Program Bermuda D",    "aum_bn_approx":  5.5},
    {"name": "PIMCO",            "program": "Trends Managed Futures",     "aum_bn_approx":  5.0},
    {"name": "AlphaSimplex",     "program": "ASG Managed Futures",        "aum_bn_approx":  5.0},
    {"name": "iSAM",             "program": "Vector",                     "aum_bn_approx":  4.8},
]

# ---------------------------------------------------------------------------
# Benchmark ETFs — for portfolio-level return validation
#
# DBMF: Replicates SG CTA Index via regression (monthly rebalance)
# KMLM: Rules-based trend following (KFA MLM Index, 22 futures)
# CTA:  Simplify's faster-reacting trend model
#
# These are useful for "does our aggregate return shape look plausible?"
# They are NOT useful for "is CTA X long copper today?"
# ---------------------------------------------------------------------------
BENCHMARK_ETFS = {
    "DBMF": {"name": "iMGP DBi Managed Futures Strategy ETF",            "approach": "SG CTA Index replication"},
    "KMLM": {"name": "KraneShares Mount Lucas Managed Futures Index ETF", "approach": "rules-based trend following"},
    "CTA":  {"name": "Simplify Managed Futures Strategy ETF",             "approach": "fast trend following"},
}

# ---------------------------------------------------------------------------
# Agent-friendly run profiles
# ---------------------------------------------------------------------------
RUN_PROFILES = {
    "daily_note": {
        "description": "Live markdown summary for agents and daily sharing",
        "quick": True,
        "live": True,
        "refresh": True,
        "summary_only": True,
        "summary_format": "markdown",
        "llm_summary": True,
    },
}

# ---------------------------------------------------------------------------
# Data source configuration
# ---------------------------------------------------------------------------
DATA_PARAMS = {
    "price_history_years": 3,       # fetch 3 years for MA calculations (need 500+ days for ultra-long)
    "yfinance_interval": "1d",
    "yfinance_live_period": "2d",
    "yfinance_live_interval": "5m",
    "cache_dir": ".cache",
}
