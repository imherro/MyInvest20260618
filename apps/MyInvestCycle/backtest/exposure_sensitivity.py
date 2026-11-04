from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from adaptive_allocation.allocation_engine import build_allocation_intent_snapshot
from backtest.allocation_backtest_engine import RISK_BUDGET_EXPOSURE, run_v2_allocation_backtest
from backtest.allocation_policy_analyzer import analyze_policy_contribution
from config import DATA_DIR


DEFAULT_BASELINE_PATH = DATA_DIR / "v2_allocation_backtest.json"
POLICY_VARIANTS: dict[str, dict[str, object]] = {
    "baseline": {
        "label": "A baseline",
        "description": "当前默认映射，风险预算偏均衡。",
        "exposure_map": dict(RISK_BUDGET_EXPOSURE),
    },
    "higher_participation": {
        "label": "B higher participation",
        "description": "提高 medium/medium_high/high 的权益参与度，测试结构牛期间是否改善收益。",
        "exposure_map": {
            "defensive": 0.15,
            "low": 0.45,
            "medium": 0.70,
            "medium_high": 0.85,
            "high": 0.95,
        },
    },
    "conservative": {
        "label": "C conservative",
        "description": "降低中高风险预算映射，测试更防守方案的回撤收益比。",
        "exposure_map": {
            "defensive": 0.10,
            "low": 0.30,
            "medium": 0.50,
            "medium_high": 0.65,
            "high": 0.80,
        },
    },
}


def _summary_score(summary: Mapping[str, object], primary_key: str) -> float:
    value = summary.get(primary_key)
    return float(value) if isinstance(value, (int, float)) else float("-inf")


def _best_variant(results: Mapping[str, Mapping[str, object]], key: str) -> dict[str, object] | None:
    if not results:
        return None
    best_id, payload = max(results.items(), key=lambda item: _summary_score(item[1].get("summary", {}), key))
    return {
        "variant_id": best_id,
        "label": payload.get("label"),
        "metric": key,
        "value": payload.get("summary", {}).get(key),
    }


def _snapshot_builder_from_baseline(path: str | Path):
    baseline_path = Path(path)
    if not baseline_path.exists():
        return None, {"source": str(baseline_path), "available": False, "reason": "baseline artifact missing"}
    payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    signals = payload.get("signals") or []
    by_date = {str(item.get("date")): item for item in signals if isinstance(item, Mapping) and item.get("date")}
    if not by_date:
        return None, {"source": str(baseline_path), "available": False, "reason": "no signal history in baseline artifact"}

    def builder(date_text: str) -> dict[str, object]:
        signal = by_date.get(str(date_text))
        if not signal:
            return build_allocation_intent_snapshot(date_text, cache_only=True)
        return {
            "as_of": signal.get("as_of") or date_text,
            "structural_state": signal.get("structural_state"),
            "allocation_structural_state": signal.get("allocation_structural_state"),
            "allocation_intent": {
                "risk_budget": signal.get("risk_budget"),
                "style_preference": signal.get("style_preference") or [],
            },
            "risk_adjustments": {
                "theme_risk_level": signal.get("theme_risk_level"),
                "allocation_structural_state": signal.get("allocation_structural_state"),
            },
            "evidence": {
                "macro": {"state": signal.get("macro_state")},
                "market_structure": {"state": signal.get("market_structure_state")},
            },
            "explanation": signal.get("explanation") or [],
        }

    return builder, {
        "source": str(baseline_path),
        "available": True,
        "signal_count": len(by_date),
        "start": min(by_date),
        "end": max(by_date),
    }


def run_exposure_sensitivity(
    *,
    start_date: str = "20240101",
    end_date: str = "20991231",
    rebalance_every_sessions: int = 20,
    baseline_path: str | Path = DEFAULT_BASELINE_PATH,
) -> dict[str, object]:
    builder, builder_status = _snapshot_builder_from_baseline(baseline_path)
    results: dict[str, dict[str, object]] = {}
    for variant_id, variant in POLICY_VARIANTS.items():
        payload = run_v2_allocation_backtest(
            start_date=start_date,
            end_date=end_date,
            rebalance_every_sessions=rebalance_every_sessions,
            cache_only=True,
            snapshot_builder=builder,
            exposure_map=variant["exposure_map"],
        )
        results[variant_id] = {
            "variant_id": variant_id,
            "label": variant["label"],
            "description": variant["description"],
            "exposure_map": variant["exposure_map"],
            "summary": payload["summary"],
            "performance_metrics": payload["performance_metrics"],
            "policy_contribution": analyze_policy_contribution(payload),
            "validation": payload["validation"],
        }
    return {
        "engine": "V2.5.2 Allocation Policy Calibration & Exposure Sensitivity",
        "requested_window": {"start_date": start_date, "end_date": end_date},
        "rebalance_every_sessions": rebalance_every_sessions,
        "signal_history": builder_status,
        "variants": results,
        "best_by": {
            "annualized_return": _best_variant(results, "v2_annualized_return"),
            "max_drawdown": _best_variant(results, "v2_max_drawdown"),
            "calmar": _best_variant(results, "v2_calmar"),
            "sharpe": _best_variant(results, "v2_sharpe"),
        },
        "constraints": {
            "calibration_only": True,
            "no_etf_selection": True,
            "no_single_stock": True,
            "no_trade_execution": True,
            "no_order": True,
            "no_new_alpha_factor": True,
        },
    }
