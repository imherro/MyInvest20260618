from __future__ import annotations

from statistics import pstdev
from typing import Mapping, Sequence


PRIMARY_HORIZON = 120
SHORT_HORIZON = 60


def _round(value: object, digits: int = 6) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _event(value: object, threshold: float, *, op: str) -> bool:
    number = _round(value)
    if number is None:
        return False
    if op == "le":
        return number <= threshold
    if op == "ge":
        return number >= threshold
    raise ValueError(f"unsupported op: {op}")


def future_environment_label(metrics: Mapping[str, object]) -> str:
    if not metrics.get("future_window_complete"):
        return "incomplete_future_window"
    if _event(metrics.get("max_drawdown_120d"), -0.15, op="le") or _event(
        metrics.get("max_drawdown_60d"), -0.10, op="le"
    ):
        return "drawdown_stress"
    if _event(metrics.get("realized_volatility_60d"), 0.25, op="ge") and _event(
        metrics.get("max_drawdown_60d"), -0.06, op="le"
    ):
        return "high_volatility"
    if _event(metrics.get("forward_return_120d"), 0.12, op="ge") and not _event(
        metrics.get("max_drawdown_60d"), -0.08, op="le"
    ):
        return "strong_uptrend"
    if _event(metrics.get("forward_return_120d"), 0.04, op="ge"):
        return "positive_range"
    if _event(metrics.get("forward_return_120d"), -0.04, op="le"):
        return "weak_or_flat"
    return "range_mixed"


def future_environment_flags(metrics: Mapping[str, object]) -> dict[str, bool]:
    if not metrics.get("future_window_complete"):
        return {
            "future_window_complete": False,
            "high_risk_event": False,
            "strong_opportunity_event": False,
            "future_drawdown_gt_15": False,
            "future_return_gt_12": False,
        }
    future_drawdown_gt_15 = _event(metrics.get("max_drawdown_120d"), -0.15, op="le")
    high_risk_event = future_drawdown_gt_15 or _event(metrics.get("max_drawdown_60d"), -0.10, op="le") or (
        _event(metrics.get("realized_volatility_60d"), 0.25, op="ge")
        and _event(metrics.get("max_drawdown_60d"), -0.06, op="le")
    )
    future_return_gt_12 = _event(metrics.get("forward_return_120d"), 0.12, op="ge")
    strong_opportunity_event = future_return_gt_12 and not high_risk_event
    return {
        "future_window_complete": True,
        "high_risk_event": high_risk_event,
        "strong_opportunity_event": strong_opportunity_event,
        "future_drawdown_gt_15": future_drawdown_gt_15,
        "future_return_gt_12": future_return_gt_12,
    }


def policy_alignment(policy_mode: str, flags: Mapping[str, bool]) -> str:
    if not flags.get("future_window_complete"):
        return "not_evaluated"
    control_modes = {"participate_with_control", "late_cycle_control", "protect_capital", "defensive"}
    participation_modes = {"participate", "participate_selectively", "rebuild_risk"}
    if policy_mode in control_modes and flags.get("high_risk_event"):
        return "aligned_risk_control"
    if policy_mode in control_modes and flags.get("strong_opportunity_event"):
        return "possible_over_control"
    if policy_mode in participation_modes and flags.get("high_risk_event"):
        return "under_control"
    if policy_mode in participation_modes and flags.get("strong_opportunity_event"):
        return "aligned_participation"
    return "neutral_mixed"


def policy_contradictions(row: Mapping[str, object]) -> list[dict[str, object]]:
    if not row.get("future_window_complete"):
        return []

    mode = str(row.get("policy_mode") or "unknown")
    risk_state = str(row.get("risk_state") or "unknown")
    metrics = row.get("future_metrics") if isinstance(row.get("future_metrics"), Mapping) else {}
    flags = row.get("future_flags") if isinstance(row.get("future_flags"), Mapping) else {}
    contradictions: list[dict[str, object]] = []

    if row.get("policy_alignment") == "under_control":
        contradictions.append(
            {
                "type": "under_control_before_future_risk",
                "severity": "high",
                "evidence": {
                    "policy_mode": mode,
                    "risk_state": risk_state,
                    "max_drawdown_120d": metrics.get("max_drawdown_120d"),
                    "future_drawdown_gt_15": flags.get("future_drawdown_gt_15"),
                },
            }
        )

    if row.get("policy_alignment") == "possible_over_control":
        severity = "high" if mode in {"protect_capital", "defensive"} else "medium"
        contradictions.append(
            {
                "type": "possible_over_control_before_future_opportunity",
                "severity": severity,
                "evidence": {
                    "policy_mode": mode,
                    "forward_return_120d": metrics.get("forward_return_120d"),
                    "max_drawdown_60d": metrics.get("max_drawdown_60d"),
                },
            }
        )

    if risk_state in {"CROWDED", "HIGH_RISK"} and flags.get("strong_opportunity_event"):
        contradictions.append(
            {
                "type": "risk_state_false_positive_review",
                "severity": "medium",
                "evidence": {
                    "risk_state": risk_state,
                    "forward_return_120d": metrics.get("forward_return_120d"),
                    "max_drawdown_60d": metrics.get("max_drawdown_60d"),
                },
            }
        )

    if risk_state not in {"CROWDED", "HIGH_RISK"} and flags.get("high_risk_event"):
        contradictions.append(
            {
                "type": "risk_state_missed_future_risk",
                "severity": "high",
                "evidence": {
                    "risk_state": risk_state,
                    "max_drawdown_120d": metrics.get("max_drawdown_120d"),
                    "realized_volatility_60d": metrics.get("realized_volatility_60d"),
                },
            }
        )

    return contradictions


def realized_volatility(returns: Sequence[float]) -> float | None:
    clean = [float(value) for value in returns if value is not None]
    if len(clean) < 2:
        return None
    return round(pstdev(clean) * (252**0.5), 6)
