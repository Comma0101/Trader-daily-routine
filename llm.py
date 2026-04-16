"""Optional Gemini summary rewrite for deterministic CTA summary facts."""

import json
import os
from pathlib import Path

import requests


DEFAULT_GEMINI_MODEL = "gemini-3-pro-preview"
DEFAULT_GEMINI_FALLBACK_MODEL = "gemini-2.5-flash"
GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_TIMEOUT_SECONDS = 45


class GeminiConfigError(RuntimeError):
    """Raised when Gemini configuration is missing."""


class GeminiRequestError(RuntimeError):
    """Raised when Gemini returns an invalid or unsuccessful response."""


def generate_gemini_summary(facts, output_format="terminal", model_override=None):
    """Rewrite already-computed facts into a more natural summary."""
    config = load_gemini_config()
    model_name = model_override or config["model"]
    try:
        response = requests.post(
            GEMINI_ENDPOINT.format(model=model_name),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": config["api_key"],
            },
            json=build_gemini_request_payload(
                facts,
                output_format=output_format,
                model_name=model_name,
            ),
            timeout=GEMINI_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise GeminiRequestError(f"Gemini request failed: {exc}") from exc

    try:
        response.raise_for_status()
    except requests.RequestException as exc:
        raise GeminiRequestError(f"Gemini request failed: {exc}") from exc

    return parse_gemini_response(response.json())


def load_gemini_config():
    """Load Gemini settings from the environment."""
    file_values = _load_repo_env_values()

    api_key = os.getenv("GEMINI_API_KEY") or file_values.get("GEMINI_API_KEY")
    if not api_key:
        raise GeminiConfigError("GEMINI_API_KEY is not set")

    return {
        "api_key": api_key,
        "model": os.getenv("GEMINI_MODEL") or file_values.get("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL,
        "fallback_model": (
            os.getenv("GEMINI_FALLBACK_MODEL")
            or file_values.get("GEMINI_FALLBACK_MODEL")
            or DEFAULT_GEMINI_FALLBACK_MODEL
        ),
    }


def build_gemini_request_payload(facts, output_format="terminal", model_name=None):
    """Build a constrained Gemini prompt from deterministic facts."""
    max_output_tokens = 3072 if output_format == "markdown" else 600
    generation_config = {
        "temperature": 0.2,
        "topP": 0.9,
        "maxOutputTokens": max_output_tokens,
    }
    # Gemini 3 requires thinking mode — cannot be disabled.
    # Use LOW to minimize token consumption while keeping the request valid.
    if _uses_gemini_three(model_name):
        generation_config["thinkingConfig"] = {
            "thinkingLevel": "LOW",
        }
    elif _uses_gemini_two_five(model_name):
        generation_config["thinkingConfig"] = {
            "thinkingBudget": 0,
        }

    return {
        "contents": [
            {
                "parts": [
                    {
                        "text": _prompt_text(facts, output_format=output_format),
                    }
                ]
            }
        ],
        "generationConfig": generation_config,
    }


def parse_gemini_response(payload):
    """Extract plain text from Gemini's response payload.

    Filters out thinking parts ({"thought": true, "text": "..."}) that
    Gemini 3 models return when thinking is enabled. Only actual output
    parts are included in the returned text.
    """
    for candidate in payload.get("candidates", []):
        content = candidate.get("content", {})
        parts = content.get("parts", [])
        # Skip thinking parts — they have "thought": true
        output_parts = [part for part in parts if not part.get("thought")]
        text = "".join(part.get("text", "") for part in output_parts).strip()
        if text:
            return text

    raise GeminiRequestError("Gemini response did not include summary text")


def _prompt_text(facts, output_format="terminal"):
    compact_facts_json = json.dumps(
        _compact_facts_for_prompt(facts),
        sort_keys=True,
        indent=2,
        ensure_ascii=True,
    )

    selected_count = facts.get("scope", {}).get("selected_market_count", "N")

    rules = (
        "You are a senior CTA strategist writing a professional daily CTA note.\n"
        "This note will be shared externally and must read like a sell-side daily research note.\n"
        "RULES:\n"
        "- Use ONLY the facts in the JSON payload. Do not invent numbers, markets, dates, or conclusions.\n"
        "- If validation is weak or caveated, say so plainly.\n"
        "- State the validation grade explicitly. If grade is D or F, lead with a confidence caveat.\n"
        "- Draw on thesis, drivers, interpretation, why_now, confidence, capital, and actions when available.\n"
        "- Explain what the data means and why it matters now.\n"
        "- Mention assumptions when present, including CTA AUM assumptions for proxy flow.\n"
        "- Do not describe deployed risk as cash spent.\n"
        f"- This is a PROXY model covering {selected_count} of ~100+ liquid futures markets. "
        "It does not represent the full CTA industry.\n"
        "- All flow figures are model-implied target notional changes, not observed market transactions.\n"
    )

    if output_format == "markdown":
        style = (
            "OUTPUT FORMAT — produce a professional daily CTA note with this structure EXACTLY:\n"
            "\n"
            "## CTA Daily Note — {date}\n"
            "\n"
            "[2-3 sentence executive summary: overall positioning stance, conviction level, key risk]\n"
            "\n"
            "### Investment Overview\n"
            "- **AUM Basis:** ...\n"
            "- **Risk Deployed:** ... gross / ... net\n"
            "- **Remaining Headroom:** ...\n"
            "\n"
            "### Positioning Snapshot\n"
            "[1-2 sentences on long/short/flat split, strongest convictions, crowding level]\n"
            "\n"
            "### Flow Activity (5-Day)\n"
            "- **Top Notional Increases:** [market ($notional), market ($notional)]\n"
            "- **Top Notional Decreases:** [market ($notional), market ($notional)]\n"
            "- **Sector Rotation:** [net sector moves]\n"
            "\n"
            "### Key Risks\n"
            "- [Nearest reversal risk with distance %]\n"
            "- [Crowding risk]\n"
            "- [Validation gaps]\n"
            "\n"
            "### Assumptions & Caveats\n"
            "- [CTA AUM assumption used]\n"
            "- [Validation limitations]\n"
            "- [Data mode: live nowcast vs daily close]\n"
            "\n"
            "EXAMPLE of correct output:\n"
            "## CTA Daily Note — 2026-04-16\n"
            "\n"
            "CTAs remain net long across 4 tracked markets with high crowding and elevated reversal risk "
            "in Euro FX. Conviction is strongest in S&P 500 (32% weight) and Gold short (29% weight). "
            "The key risk is Euro FX sitting just 0.76% from a signal flip.\n"
            "\n"
            "### Investment Overview\n"
            "- **AUM Basis:** $112.8B (SG Trend Index tracked-fund basket)\n"
            "- **Risk Deployed:** $95.2B gross (0.95x) / $21.0B net (0.21x)\n"
            "- **Remaining Headroom:** $405.0B (4.05x)\n"
            "\n"
            "### Positioning Snapshot\n"
            "The model is 3 long, 1 short, and 0 flat. S&P 500 and Crude Oil are max long; "
            "Gold is max short. Crowding is HIGH with 4/4 markets at max signal.\n"
            "\n"
            "### Flow Activity (5-Day)\n"
            "- **Top Notional Increases:** Euro FX (+$53.9B est.), S&P 500 (+$7.0B est.)\n"
            "- **Top Notional Decreases:** Crude Oil (-$384M est.)\n"
            "- **Sector Rotation:** Net increase in FX (+$53.9B), net decrease in Energy (-$384M)\n"
            "\n"
            "### Key Risks\n"
            "- Euro FX is 0.76% from reversal — closest flip risk across all markets\n"
            "- HIGH crowding (4/4 at max signal) elevates correlated unwind risk\n"
            "- SG signal validation unavailable; COT coverage limited to weekly lag\n"
            "\n"
            "### Assumptions & Caveats\n"
            "- CTA AUM assumption: $112.8B (SG tracked-fund basket, not full industry)\n"
            "- SG Trend Indicator confirmation not yet available\n"
            "- Data mode: live nowcast over 2026-04-15 official close\n"
            "\n"
            "IMPORTANT: Include all five ### subsections. Keep the full note under 400 words. "
            "No tables. Write in professional sell-side research tone."
        )
    elif output_format == "terminal":
        style = (
            "OUTPUT FORMAT — write exactly five short lines with these labels:\n"
            "Data: (what data was used)\n"
            "Method: (how signals were calculated)\n"
            "Capital: (AUM, deployed risk, headroom, top notional increase/decrease)\n"
            "Conclusion: (the main finding)\n"
            "Suggestion: (what to do next)\n"
            "No bullets, no markdown, no intro, no extra lines."
        )
    else:
        style = "Write a concise summary."

    return f"{rules}\n{style}\n\nCompact Facts JSON:\n{compact_facts_json}"


def _uses_gemini_three(model_name):
    normalized = (model_name or DEFAULT_GEMINI_MODEL).strip().lower()
    return normalized.startswith("gemini-3")


def _uses_gemini_two_five(model_name):
    normalized = (model_name or "").strip().lower()
    return normalized.startswith("gemini-2.5")


def _compact_facts_for_prompt(facts):
    flow = facts.get("flow", {})
    capital = facts.get("capital", {})
    crowding = facts.get("crowding", {})
    validation = facts.get("validation", {})

    investment_overview = facts.get("investment_overview", {})

    # Trim all_market_flows to top 5 increases + top 5 decreases by absolute 5D notional change
    all_flows = list(investment_overview.get("all_market_flows", []))
    increases_sorted = sorted(
        [f for f in all_flows if (f.get("delta_weight_5d") or 0) > 0],
        key=lambda f: -(f.get("estimated_notional_change_usd_5d") or f.get("delta_weight_5d") or 0),
    )[:5]
    decreases_sorted = sorted(
        [f for f in all_flows if (f.get("delta_weight_5d") or 0) < 0],
        key=lambda f: (f.get("estimated_notional_change_usd_5d") or f.get("delta_weight_5d") or 0),
    )[:5]
    trimmed_flows = increases_sorted + decreases_sorted

    compact = {
        "report_date": facts.get("report_date"),
        "scope": {
            "selected_market_count": facts.get("scope", {}).get("selected_market_count"),
            "universe_market_count": facts.get("scope", {}).get("universe_market_count"),
        },
        "position_counts": facts.get("position_counts"),
        "crowding": {
            "classification": crowding.get("classification"),
            "crowded_market_count": crowding.get("crowded_market_count"),
            "total_market_count": crowding.get("total_market_count"),
            "percentile": crowding.get("percentile"),
            "percentile_context": crowding.get("percentile_context"),
        },
        "investment_overview": {
            "aum_basis_label": investment_overview.get("aum_basis_label"),
            "aum_usd": _round_number(investment_overview.get("aum_usd")),
            "gross_deployed_pct": _round_number(investment_overview.get("gross_deployed_pct")),
            "gross_deployed_usd": _round_number(investment_overview.get("gross_deployed_usd")),
            "net_deployed_pct": _round_number(investment_overview.get("net_deployed_pct")),
            "net_deployed_usd": _round_number(investment_overview.get("net_deployed_usd")),
            "remaining_headroom_pct": _round_number(investment_overview.get("remaining_headroom_pct")),
            "remaining_headroom_usd": _round_number(investment_overview.get("remaining_headroom_usd")),
            "top_market_flows": _compact_market_items(
                trimmed_flows,
                limit=10,
                fields=("symbol", "market", "sector", "direction", "weight", "delta_weight_5d", "estimated_notional_change_usd_5d"),
            ),
            "sector_flows_5d": {
                sector: {k: _round_number(v) for k, v in vals.items()}
                for sector, vals in investment_overview.get("sector_flows_5d", {}).items()
            },
        },
        "data_used": facts.get("data_used"),
        "calculation_method": facts.get("calculation_method"),
        "thesis": facts.get("thesis"),
        "interpretation": facts.get("interpretation"),
        "why_now": facts.get("why_now"),
        "confidence": facts.get("confidence"),
        "drivers": {
            "strongest_convictions": _compact_market_items(
                facts.get("strongest_convictions", []),
                limit=3,
                fields=("symbol", "market", "direction", "weight", "days_in_position"),
            ),
            "recent_flips": _compact_market_items(
                facts.get("recent_flips", []),
                limit=3,
                fields=("symbol", "market", "date", "from_label", "to_label", "price"),
            ),
            "nearest_flip_risks": _compact_market_items(
                facts.get("nearest_flip_risks", []),
                limit=3,
                fields=("symbol", "market", "direction", "distance_pct", "distance_bucket"),
            ),
            "top_notional_increase_5d": _compact_market_items(
                flow.get("top_notional_increase_5d", []),
                limit=5,
                fields=("symbol", "market", "estimated_notional_change_usd_5d", "delta_weight_5d"),
            ),
            "top_notional_decrease_5d": _compact_market_items(
                flow.get("top_notional_decrease_5d", []),
                limit=5,
                fields=("symbol", "market", "estimated_notional_change_usd_5d", "delta_weight_5d"),
            ),
        },
        "flow": {
            "estimation_label": flow.get("estimation_label"),
            "assumed_cta_aum_usd": _round_number(flow.get("assumed_cta_aum_usd")),
        },
        "capital": {
            "aum_basis_label": capital.get("aum_basis", {}).get("label"),
            "aum_usd": _round_number(capital.get("aum_basis", {}).get("aum_usd")),
            "gross_risk_deployed_pct_of_aum": _round_number(capital.get("gross_risk_deployed_pct_of_aum")),
            "net_risk_deployed_pct_of_aum": _round_number(capital.get("net_risk_deployed_pct_of_aum")),
            "remaining_gross_headroom_pct_of_aum": _round_number(
                capital.get("remaining_gross_headroom_pct_of_aum")
            ),
            "estimated_gross_risk_deployed_usd": _round_number(
                capital.get("estimated_gross_risk_deployed_usd")
            ),
            "estimated_remaining_gross_headroom_usd": _round_number(
                capital.get("estimated_remaining_gross_headroom_usd")
            ),
            "note": capital.get("note"),
        },
        "validation": {
            "signal": _compact_validation_item(validation.get("signal", {})),
            "position": _compact_validation_item(validation.get("position", {})),
            "return": _compact_validation_item(validation.get("return", {})),
        },
        "validation_composite": {
            "score": validation.get("composite", {}).get("composite_score"),
            "grade": validation.get("composite", {}).get("grade"),
            "note": validation.get("composite", {}).get("note"),
        },
        "actions": list(facts.get("actions", [])[:3]),
    }

    benchmark_etfs = facts.get("benchmark_etfs")
    if benchmark_etfs:
        compact["benchmark_etfs"] = _compact_market_items(
            benchmark_etfs,
            limit=3,
            fields=("symbol", "return_5d", "return_20d", "return_ytd"),
        )

    return compact


def _compact_market_items(items, limit, fields):
    compact_items = []
    for item in list(items)[:limit]:
        compact_item = {}
        for field in fields:
            if field in item:
                compact_item[field] = _round_number(item.get(field))
        if compact_item:
            compact_items.append(compact_item)
    return compact_items


def _compact_validation_item(item):
    if not item:
        return {}

    keep_fields = (
        "status",
        "note",
        "agreement_rate",
        "agreement_pct",
        "coverage",
        "coverage_count",
        "summary",
        "signal_match_rate",
        "correlation_full",
        "correlation_60d",
        "days_overlap",
    )
    return {
        field: _round_number(item.get(field))
        for field in keep_fields
        if field in item and item.get(field) is not None
    }


def _round_number(value):
    if isinstance(value, float):
        return round(value, 4)
    return value


def _repo_env_path():
    return Path(__file__).resolve().parent / ".env"


def _load_repo_env_values():
    env_path = _repo_env_path()
    if not env_path.exists():
        return {}

    values = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        cleaned_value = value.strip().strip('"').strip("'")
        values[key.strip()] = cleaned_value

    return values
