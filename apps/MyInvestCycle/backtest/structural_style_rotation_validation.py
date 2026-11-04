from __future__ import annotations

from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Mapping

from backtest.style_attribution_validation import DEFAULT_HORIZONS, TOP_N, build_style_validation
from config import DATA_DIR
from style_allocation.structural_style_validation import (
    compact_structural_samples,
    structural_bull_rows,
    style_drift_analysis,
)


DEFAULT_OUTPUT_PATH = DATA_DIR / "structural_style_validation.json"


def _risk_metrics(rows: list[Mapping[str, object]], return_key: str) -> dict[str, object]:
    returns = [
        float(row[return_key]) for row in sorted(rows, key=lambda item: str(item.get("date")))
        if row.get(return_key) is not None
    ]
    if not returns:
        return {
            "observation_count": 0,
            "mean_return": None,
            "volatility": None,
            "max_drawdown": None,
            "total_compounded_return": None,
            "positive_rate": None,
        }
    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for value in returns:
        equity *= 1.0 + value
        peak = max(peak, equity)
        drawdown = equity / peak - 1.0
        max_drawdown = min(max_drawdown, drawdown)
    mean_return = sum(returns) / len(returns)
    volatility = 0.0
    if len(returns) >= 2:
        variance = sum((value - mean_return) ** 2 for value in returns) / (len(returns) - 1)
        volatility = math.sqrt(variance)
    return {
        "observation_count": len(returns),
        "mean_return": round(mean_return, 6),
        "volatility": round(volatility, 6),
        "max_drawdown": round(max_drawdown, 6),
        "total_compounded_return": round(equity - 1.0, 6),
        "positive_rate": round(sum(1 for value in returns if value > 0) / len(returns), 6),
    }


def _summary_for_rows(rows: list[Mapping[str, object]]) -> dict[str, object]:
    spreads = [float(row["relative_to_baseline"]) for row in rows if row.get("relative_to_baseline") is not None]
    hits = [
        1.0 if float(row["style_aware_return"]) > float(row["baseline_return"]) else 0.0
        for row in rows
        if row.get("style_aware_return") is not None and row.get("baseline_return") is not None
    ]
    ics = [float(row["style_ic"]) for row in rows if row.get("style_ic") is not None]
    return {
        "date_count": len({str(row.get("date")) for row in rows}),
        "observation_count": len(rows),
        "baseline": _risk_metrics(rows, "baseline_return"),
        "style_aware": _risk_metrics(rows, "style_aware_return"),
        "spread": None if not spreads else round(sum(spreads) / len(spreads), 6),
        "hit_rate": None if not hits else round(sum(hits) / len(hits), 6),
        "style_ic": None if not ics else round(sum(ics) / len(ics), 6),
        "positive_ic_rate": None if not ics else round(sum(1 for value in ics if value > 0) / len(ics), 6),
    }


def build_structural_style_validation(
    *,
    start_date: str | int = "20150105",
    end_date: str | int = "20991231",
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    step_sessions: int = 20,
    top_n: int = TOP_N,
) -> dict[str, object]:
    base = build_style_validation(
        start_date=start_date,
        end_date=end_date,
        horizons=horizons,
        step_sessions=step_sessions,
        top_n=top_n,
    )
    structural_results: dict[str, object] = {}
    for mode, horizon_rows in (base.get("observations") or {}).items():
        structural_results[mode] = {}
        for horizon, rows in (horizon_rows or {}).items():
            filtered = structural_bull_rows(rows)
            structural_results[mode][horizon] = {
                "summary": _summary_for_rows(filtered),
                "style_drift": style_drift_analysis(filtered),
                "sample_observations": compact_structural_samples(filtered),
            }

    tradable_20 = ((structural_results.get("tradable_etf") or {}).get("20d") or {}).get("summary") or {}
    tradable_60 = ((structural_results.get("tradable_etf") or {}).get("60d") or {}).get("summary") or {}
    spread_20 = tradable_20.get("spread")
    spread_60 = tradable_60.get("spread")
    status = "inconclusive"
    if spread_20 is not None and spread_60 is not None:
        hit_20 = tradable_20.get("hit_rate")
        hit_60 = tradable_60.get("hit_rate")
        ic_20 = tradable_20.get("style_ic")
        ic_60 = tradable_60.get("style_ic")
        if (
            float(spread_20) > 0
            and float(spread_60) > 0
            and hit_20 is not None
            and hit_60 is not None
            and float(hit_20) > 0.5
            and float(hit_60) > 0.5
            and ic_20 is not None
            and ic_60 is not None
            and float(ic_20) > 0
            and float(ic_60) > 0
        ):
            status = "structural_bull_confirmed"
        elif float(spread_20) > 0 and float(spread_60) > 0:
            status = "positive_spread_not_robust"
        elif float(spread_20) > 0:
            status = "short_horizon_only"
        else:
            status = "weak_or_negative"

    return {
        "metadata": {
            "engine": "V3.5.3 Structural Bull Style Rotation Validation",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "window": base["metadata"]["window"],
            "source_engine": base["metadata"]["engine"],
            "score_date_count": base["metadata"]["score_date_count"],
            "step_sessions": step_sessions,
            "horizons": list(horizons),
            "top_n": top_n,
            "validation_scope": "STRUCTURAL_BULL_ONLY",
        },
        "summary": {
            "edge_status": status,
            "tradable_20d": tradable_20,
            "tradable_60d": tradable_60,
            "interpretation": (
                "This validation isolates STRUCTURAL_BULL dates from V3.5.2. "
                "Positive spread is only a structural-bull-specific hypothesis until hit rate, IC and drawdown are also robust."
            ),
        },
        "results": structural_results,
        "constraints": {
            "research_validation_only": True,
            "structural_bull_only": True,
            "style_preference_formula_unchanged_from_v3_5_2": True,
            "decision_inputs_only_use_same_day_or_prior_data": True,
            "future_returns_used_only_for_validation_labels": True,
            "no_future_function_in_signal": True,
            "no_style_weight": True,
            "no_etf_allocation": True,
            "no_position_sizing": True,
            "no_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
            "no_parameter_optimization": True,
            "failure_result_is_acceptable": True,
        },
    }


def write_structural_style_validation(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
