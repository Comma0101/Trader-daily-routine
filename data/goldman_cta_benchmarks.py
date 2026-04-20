"""Public Goldman CTA note snapshots used for calibration.

These are manually curated from public summaries and are not official Goldman
research documents. They provide benchmark points for direction, thresholds,
and scenario magnitudes where enough public detail exists.
"""

PUBLIC_GOLDMAN_CTA_NOTES = [
    {
        "id": "gs_2024_01_08_spx_every_scenario_sell",
        "published_date": "2024-01-08",
        "title": "CTAs likely to sell S&P 500 in every scenario next week",
        "source_url": "https://www.investing.com/news/stock-market-news/ctas-likely-to-sell-sp-500-in-every-scenario-next-week-goldman-warns-432SI-3255426",
        "reference_symbol": "ES",
        "position": {
            "scope": "global_equities",
            "usd": 106_000_000_000.0,
            "direction": "LONG",
            "note": "Public summary cited CTAs long about $106B of global equities and $47B of US stocks.",
        },
        "thresholds": {
            "short_term": 4471.0,
            "medium_term": 4407.0,
            "long_term": 4377.0,
        },
        "scenario_targets": [
            {
                "label": "flat",
                "scenario_key": "flat",
                "symbol": "ES",
                "flow_usd": -436_000_000.0,
                "horizon": "1w",
                "precision": "exact",
            },
            {
                "label": "up_tape",
                "scenario_key": "up_2pct",
                "symbol": "ES",
                "flow_usd": -1_300_000_000.0,
                "horizon": "1w",
                "precision": "bucket_proxy",
            },
            {
                "label": "down_tape",
                "scenario_key": "down_2pct",
                "symbol": "ES",
                "flow_usd": -1_900_000_000.0,
                "horizon": "1w",
                "precision": "bucket_proxy",
            },
        ],
    },
    {
        "id": "gs_2024_04_15_spx_sell_20_42b",
        "published_date": "2024-04-15",
        "title": "Trend hedge funds could sell up to $42B in US shares",
        "source_url": "https://www.investing.com/news/stock-market-news/trend-hedge-funds-could-sell-up-to-42-billion-in-us-shares-says-goldman-3378981",
        "reference_symbol": "ES",
        "thresholds": {
            "short_term": 5135.0,
        },
        "scenario_targets": [
            {
                "label": "down_3p2pct",
                "scenario_key": "down_2pct",
                "symbol": "ES",
                "flow_usd": -20_000_000_000.0,
                "horizon": "1m",
                "precision": "move_proxy",
                "source_move_pct": -0.032,
            },
            {
                "label": "deep_downside",
                "scenario_key": "down_5pct",
                "symbol": "ES",
                "flow_usd": -42_000_000_000.0,
                "horizon": "1m",
                "precision": "bucket_proxy",
            },
        ],
    },
    {
        "id": "gs_2025_03_18_spx_buy_if_bounce_strong",
        "published_date": "2025-03-18",
        "title": "CTA buying could come in big if bounce is strong",
        "source_url": "https://www.investing.com/news/stock-market-news/sp-500-goldman-says-says-cta-buying-could-come-in-big-if-bounce-is-strong-93CH-3933847",
        "reference_symbol": "ES",
        "scenario_targets": [
            {
                "label": "up_strong",
                "scenario_key": "up_5pct",
                "symbol": "ES",
                "flow_usd": 45_000_000_000.0,
                "horizon": "1m",
                "precision": "bucket_proxy",
            },
        ],
    },
    {
        "id": "gs_2025_11_04_equities_sell_all_scenarios",
        "published_date": "2025-11-04",
        "title": "CTAs to sell equities under all scenarios",
        "source_url": "https://www.investing.com/news/stock-market-news/ctas-to-sell-equities-under-all-scenarios-goldman-sachs-says-93CH-4329311",
        "reference_symbol": "ES",
        "position": {
            "scope": "equities",
            "direction": "LONG",
            "note": "Public summary described positioning as still high, at the 94th percentile.",
        },
        "thresholds": {
            "short_term": 6679.0,
            "medium_term": 6386.0,
        },
        "scenario_targets": [
            {
                "label": "down_tape",
                "scenario_key": "down_2pct",
                "symbol": None,
                "flow_usd": -32_000_000_000.0,
                "horizon": "1w",
                "precision": "bucket_proxy",
                "scope": "equities_total",
            },
        ],
    },
    {
        "id": "gs_2025_11_20_equities_sell_40b_below_6725",
        "published_date": "2025-11-20",
        "title": "Goldman projects $40B stock selling scenario over the next week",
        "source_url": "https://www.investing.com/news/economy-news/goldman-projects-40-billion-stock-selling-scenario-over-the-next-week-4371032",
        "reference_symbol": "ES",
        "position": {
            "scope": "global_equities",
            "usd": 150_000_000_000.0,
            "direction": "LONG",
        },
        "thresholds": {
            "short_term": 6725.0,
        },
        "scenario_targets": [
            {
                "label": "trigger_break",
                "scenario_key": "down_2pct",
                "symbol": None,
                "flow_usd": -40_000_000_000.0,
                "horizon": "1w",
                "precision": "bucket_proxy",
                "scope": "equities_total",
            },
        ],
    },
    {
        "id": "gs_2026_04_09_spx_buy_34b_current_levels",
        "published_date": "2026-04-09",
        "title": "Goldman sees CTAs poised to buy $34B of S&P 500 stock next week",
        "source_url": "https://za.investing.com/news/stock-market-news/goldman-sees-ctas-poised-to-buy-34b-of-sp-500-stock-next-week-93CH-4205076",
        "reference_symbol": "ES",
        "position": {
            "scope": "SPX",
            "usd": -30_000_000_000.0,
            "direction": "SHORT",
        },
        "thresholds": {
            "short_term": 6713.0,
            "medium_term": 6734.0,
            "long_term": 6400.0,
        },
        "scenario_targets": [
            {
                "label": "current_tape",
                "scenario_key": "flat",
                "symbol": "ES",
                "flow_usd": 34_000_000_000.0,
                "horizon": "1w",
                "precision": "current_levels",
                "note": "Goldman described this as projected buying at current market levels, not a pure flat-tape delta.",
            },
        ],
    },
    {
        "id": "gs_2026_04_17_equities_buy_70b_next_5d",
        "published_date": "2026-04-17",
        "title": "Systematic funds buy stocks at record pace, adding $86B",
        "source_url": "https://finance.yahoo.com/markets/stocks/articles/systematic-funds-buy-stocks-record-122530261.html",
        "reference_symbol": "ES",
        "position": {
            "scope": "equities_total",
            "direction": "LONG",
            "note": "Goldman said systematic funds bought $86B over the prior 5 sessions and could buy another $70B over the next 5 sessions.",
        },
        "scenario_targets": [
            {
                "label": "current_tape",
                "scenario_key": "flat",
                "symbol": None,
                "flow_usd": 70_000_000_000.0,
                "horizon": "5d",
                "precision": "current_levels",
                "scope": "equities_total",
            },
        ],
    },
]
