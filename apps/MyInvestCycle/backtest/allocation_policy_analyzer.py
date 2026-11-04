from __future__ import annotations

from typing import Mapping


def _round(value: float | None, digits: int = 6) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def analyze_policy_contribution(payload: Mapping[str, object]) -> dict[str, object]:
    attribution = payload.get("state_attribution")
    structural = {}
    if isinstance(attribution, Mapping):
        structural = attribution.get("structural_state") or {}
    rows = []
    for state, item in sorted(structural.items()):
        if not isinstance(item, Mapping):
            continue
        strategy_return = float(item.get("strategy_return") or 0.0)
        benchmark_return = float(item.get("benchmark_return") or 0.0)
        rows.append(
            {
                "state": str(state),
                "sessions": int(item.get("sessions") or 0),
                "average_exposure": _round(item.get("average_exposure")),
                "strategy_return": _round(strategy_return),
                "benchmark_return": _round(benchmark_return),
                "alpha": _round(strategy_return - benchmark_return),
                "missed_beta": _round(benchmark_return - strategy_return),
                "hit_rate": _round(item.get("hit_rate")),
            }
        )
    focus = next((row for row in rows if row["state"] == "STRUCTURAL_BULL_ROTATION"), None)
    return {
        "structural_state_contribution": rows,
        "structural_bull_rotation": focus,
        "interpretation": [
            "missed_beta = 510500 benchmark return - V2 strategy return within the same state bucket.",
            "Positive missed_beta means the policy under-participated versus the 510500 beta proxy.",
            "This is calibration evidence only; it is not a trade or ETF recommendation.",
        ],
    }
