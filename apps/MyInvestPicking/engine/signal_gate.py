from __future__ import annotations

from typing import Any

BUY_THRESHOLD = 0.62
HOLD_THRESHOLD = 0.48
MIN_BUY_SCORE = 0.38
MIN_HOLD_SCORE = 0.30
HIGH_CONVICTION_SCORE = 0.55
HIGH_CONVICTION_CONFIDENCE = 0.80
BACKTEST_REDUCE_SCALE = 0.25
BACKTEST_CAUTION_SCALE = 0.50
HIGH_VOL_SCALE = 0.60
CRASH_SCALE = 0.30


def build_signal_decision(
    position: dict[str, Any],
    tradability: dict[str, Any],
    confidence: dict[str, Any],
    market_regime: dict[str, Any],
    correlation_context: dict[str, Any],
    backtest_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    final_score = _to_float(position.get("final_score"), 0.0)
    confidence_score = _to_float(confidence.get("confidence"), 0.0)
    action = _action(
        final_score=final_score,
        confidence_score=confidence_score,
        tradability=tradability,
        market_regime=market_regime,
        correlation_context=correlation_context,
        backtest_context=backtest_context or {},
    )
    operation_state = _operation_state(
        action=action,
        final_score=final_score,
        confidence_score=confidence_score,
        tradability=tradability,
        market_regime=market_regime,
        correlation_context=correlation_context,
        backtest_context=backtest_context or {},
    )
    position_policy = _position_policy(
        action=action,
        market_regime=market_regime,
        backtest_context=backtest_context or {},
    )
    gate_reasons = _gate_reasons(
        action=action,
        final_score=final_score,
        confidence_score=confidence_score,
        tradability=tradability,
        market_regime=market_regime,
        correlation_context=correlation_context,
        backtest_context=backtest_context or {},
    )
    position_size = _position_size(
        position=position,
        action=action,
        market_regime=market_regime,
        backtest_context=backtest_context or {},
    )
    return {
        "action": action,
        "operation_state": operation_state,
        "confidence": round(confidence_score, 4),
        "position_size": position_size,
        "position_policy": position_policy,
        "gate_reasons": gate_reasons,
        "reason": _reason_payload(
            position=position,
            tradability=tradability,
            confidence=confidence,
            market_regime=market_regime,
            correlation_context=correlation_context,
            backtest_context=backtest_context or {},
            action=action,
            operation_state=operation_state,
            position_policy=position_policy,
            gate_reasons=gate_reasons,
        ),
    }


def _action(
    final_score: float,
    confidence_score: float,
    tradability: dict[str, Any],
    market_regime: dict[str, Any],
    correlation_context: dict[str, Any],
    backtest_context: dict[str, Any],
) -> str:
    if not tradability.get("tradable"):
        return "NO_TRADE"
    if _full_shadow_mode(market_regime):
        return "BUY"
    if backtest_context.get("block_buy"):
        return "NO_TRADE"
    if str(market_regime.get("state") or "") == "crash" and confidence_score < 0.80:
        return "NO_TRADE"
    if correlation_context.get("cluster_block") and confidence_score < 0.75:
        return "HOLD"
    if backtest_context.get("reduce_buy"):
        if final_score >= HIGH_CONVICTION_SCORE and confidence_score >= HIGH_CONVICTION_CONFIDENCE:
            return "BUY"
        if final_score >= MIN_HOLD_SCORE and confidence_score >= HOLD_THRESHOLD:
            return "HOLD"
        return "NO_TRADE"
    if backtest_context.get("caution") and confidence_score < 0.75:
        return "HOLD"
    if final_score >= MIN_BUY_SCORE and confidence_score >= BUY_THRESHOLD:
        return "BUY"
    if final_score >= MIN_HOLD_SCORE and confidence_score >= HOLD_THRESHOLD:
        return "HOLD"
    return "NO_TRADE"


def _position_size(
    position: dict[str, Any],
    action: str,
    market_regime: dict[str, Any],
    backtest_context: dict[str, Any],
) -> float:
    if action != "BUY":
        return 0.0
    if _full_shadow_mode(market_regime):
        return round(_to_float(position.get("weight"), 0.0), 6)
    scale = 1.0
    if backtest_context.get("reduce_buy"):
        scale *= BACKTEST_REDUCE_SCALE
    elif backtest_context.get("caution"):
        scale *= BACKTEST_CAUTION_SCALE

    regime = str(market_regime.get("state") or "")
    if regime == "crash":
        scale *= CRASH_SCALE
    elif regime == "high_vol":
        scale *= HIGH_VOL_SCALE
    return round(_to_float(position.get("weight"), 0.0) * scale, 6)


def _operation_state(
    action: str,
    final_score: float,
    confidence_score: float,
    tradability: dict[str, Any],
    market_regime: dict[str, Any],
    correlation_context: dict[str, Any],
    backtest_context: dict[str, Any],
) -> str:
    if not tradability.get("tradable"):
        return "risk_blocked"
    if action == "BUY":
        return "buyable"
    if action == "HOLD":
        return "watch"
    if backtest_context.get("block_buy"):
        return "risk_blocked"
    if str(market_regime.get("state") or "") == "crash" and confidence_score < 0.80:
        return "risk_blocked"
    if correlation_context.get("cluster_block") and confidence_score < 0.75:
        return "risk_blocked"
    if final_score >= MIN_HOLD_SCORE:
        return "research"
    return "risk_blocked"


def _position_policy(
    action: str,
    market_regime: dict[str, Any],
    backtest_context: dict[str, Any],
) -> str:
    if action != "BUY":
        return "no_new_position"
    if _full_shadow_mode(market_regime):
        return "full_shadow"
    if backtest_context.get("reduce_buy"):
        return "probe_only"
    if backtest_context.get("caution"):
        return "reduced"
    if str(market_regime.get("state") or "") in {"crash", "high_vol"}:
        return "regime_reduced"
    return "normal"


def _gate_reasons(
    action: str,
    final_score: float,
    confidence_score: float,
    tradability: dict[str, Any],
    market_regime: dict[str, Any],
    correlation_context: dict[str, Any],
    backtest_context: dict[str, Any],
) -> list[str]:
    reasons = []
    if not tradability.get("tradable"):
        reasons.append("tradability_block")
    if _full_shadow_mode(market_regime):
        return reasons
    if backtest_context.get("block_buy"):
        reasons.append("backtest_block")
    elif backtest_context.get("reduce_buy"):
        reasons.append("backtest_reduce")
    elif backtest_context.get("caution"):
        reasons.append("backtest_caution")
    regime = str(market_regime.get("state") or "")
    if regime in {"crash", "high_vol"}:
        reasons.append(f"market_{regime}")
    if correlation_context.get("cluster_block"):
        reasons.append("correlation_cluster")
    if action == "NO_TRADE" and final_score < MIN_HOLD_SCORE:
        reasons.append("low_candidate_score")
    if action == "NO_TRADE" and confidence_score < HOLD_THRESHOLD:
        reasons.append("low_confidence")
    return reasons


def _reason_payload(
    position: dict[str, Any],
    tradability: dict[str, Any],
    confidence: dict[str, Any],
    market_regime: dict[str, Any],
    correlation_context: dict[str, Any],
    backtest_context: dict[str, Any],
    action: str,
    operation_state: str,
    position_policy: str,
    gate_reasons: list[str],
) -> dict[str, Any]:
    return {
        "decision": action,
        "operation_state": operation_state,
        "position_policy": position_policy,
        "gate_reasons": gate_reasons,
        "final_score": _to_float(position.get("final_score"), 0.0),
        "regime": market_regime.get("state"),
        "tradable": tradability.get("tradable"),
        "tradability_reasons": tradability.get("reasons", []),
        "confidence_components": confidence.get("components", {}),
        "correlation": correlation_context,
        "backtest": backtest_context,
    }


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _full_shadow_mode(market_regime: dict[str, Any]) -> bool:
    return str(market_regime.get("state") or "") in {"ignored", "full_shadow"}
