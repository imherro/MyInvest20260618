from __future__ import annotations

from typing import Any

from engine.signal_confidence import calculate_signal_confidence
from engine.signal_gate import build_signal_decision
from engine.tradability_engine import assess_tradability


def build_final_signals(
    positions: list[dict[str, Any]],
    market_regime: dict[str, Any],
    correlation_risk: dict[str, Any],
    backtest_metrics: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    signals = []
    for position in positions:
        tradability = assess_tradability(position)
        confidence = calculate_signal_confidence(position, market_regime, tradability)
        correlation_context = _correlation_context(position, correlation_risk)
        decision = build_signal_decision(
            position=position,
            tradability=tradability,
            confidence=confidence,
            market_regime=market_regime,
            correlation_context=correlation_context,
            backtest_context=_signal_backtest_context(market_regime, backtest_metrics or {}),
        )
        signals.append(
            {
                "code": position.get("code"),
                "name": position.get("name"),
                "industry": position.get("industry"),
                "weight": position.get("weight"),
                "final_score": position.get("final_score"),
                "score": position.get("score"),
                "risk_adjust_factor": position.get("risk_adjust_factor"),
                "regime_multiplier": position.get("regime_multiplier"),
                "factor_health_score": position.get("factor_health_score"),
                "exchange_risk_multiplier": position.get("exchange_risk_multiplier"),
                "liquidity_risk_multiplier": position.get("liquidity_risk_multiplier"),
                "factors": position.get("factors", {}),
                "metrics": position.get("metrics", {}),
                "action": decision["action"],
                "operation_state": decision["operation_state"],
                "confidence": decision["confidence"],
                "position_size": decision["position_size"],
                "position_policy": decision["position_policy"],
                "gate_reasons": decision["gate_reasons"],
                "tradability": tradability,
                "signal_confidence": confidence,
                "reason": decision["reason"],
            }
        )
    return sorted(
        signals,
        key=lambda item: (
            _action_rank(str(item.get("action"))),
            -float(item.get("confidence") or 0),
            -float(item.get("final_score") or 0),
            str(item.get("code") or ""),
        ),
    )


def summarize_signals(signals: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {"BUY": 0, "HOLD": 0, "NO_TRADE": 0}
    operation_counts = {"buyable": 0, "watch": 0, "risk_blocked": 0, "research": 0}
    position_policy_counts: dict[str, int] = {}
    for signal in signals:
        action = str(signal.get("action") or "NO_TRADE")
        counts[action] = counts.get(action, 0) + 1
        operation_state = str(signal.get("operation_state") or "research")
        operation_counts[operation_state] = operation_counts.get(operation_state, 0) + 1
        position_policy = str(signal.get("position_policy") or "unknown")
        position_policy_counts[position_policy] = position_policy_counts.get(position_policy, 0) + 1
    buy_exposure = sum(
        float(signal.get("position_size") or 0)
        for signal in signals
        if signal.get("action") == "BUY"
    )
    average_confidence = (
        sum(float(signal.get("confidence") or 0) for signal in signals) / len(signals)
        if signals
        else 0.0
    )
    return {
        "counts": counts,
        "operation_counts": operation_counts,
        "position_policy_counts": position_policy_counts,
        "buy_exposure": round(buy_exposure, 6),
        "average_confidence": round(average_confidence, 4),
    }


def summarize_gate_status(
    signals: list[dict[str, Any]],
    backtest_metrics: dict[str, Any],
    market_regime: dict[str, Any],
) -> dict[str, Any]:
    if _full_shadow_mode(market_regime):
        backtest_context = _observed_backtest_context(backtest_metrics)
    else:
        backtest_context = _backtest_context(backtest_metrics)
    operation_counts = {"buyable": 0, "watch": 0, "risk_blocked": 0, "research": 0}
    reason_counts: dict[str, int] = {}
    for signal in signals:
        operation_state = str(signal.get("operation_state") or "research")
        operation_counts[operation_state] = operation_counts.get(operation_state, 0) + 1
        for reason in signal.get("gate_reasons", []):
            reason = str(reason)
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

    headline = _gate_headline(backtest_context, market_regime, operation_counts)
    return {
        "headline": headline,
        "backtest_gate": {
            "state": backtest_context["state"],
            "sharpe": backtest_context["sharpe"],
            "max_drawdown": backtest_context["max_drawdown"],
            "turnover": backtest_context.get("turnover"),
            "block_buy": backtest_context["block_buy"],
            "reduce_buy": backtest_context["reduce_buy"],
            "caution": backtest_context["caution"],
            "position_scale": backtest_context["position_scale"],
        },
        "market_gate": {
            "state": market_regime.get("state"),
            "confidence": market_regime.get("confidence"),
        },
        "operation_counts": operation_counts,
        "reason_counts": reason_counts,
    }


def _correlation_context(
    position: dict[str, Any],
    correlation_risk: dict[str, Any],
) -> dict[str, Any]:
    code = str(position.get("code") or "")
    for cluster in correlation_risk.get("clusters", []):
        codes = set(cluster.get("codes", []))
        if code in codes:
            avg_correlation = float(cluster.get("avg_correlation") or 0)
            return {
                "cluster_id": cluster.get("id"),
                "cluster_size": cluster.get("size"),
                "avg_correlation": round(avg_correlation, 4),
                "cluster_block": avg_correlation >= float(correlation_risk.get("threshold", 0.75)),
            }
    return {
        "cluster_id": None,
        "cluster_size": 0,
        "avg_correlation": 0.0,
        "cluster_block": False,
    }


def _backtest_context(metrics: dict[str, Any]) -> dict[str, Any]:
    sharpe = float(metrics.get("sharpe") or 0)
    max_drawdown = float(metrics.get("max_drawdown") or 0)
    block_buy = max_drawdown <= -0.12
    reduce_buy = (sharpe < 0 or max_drawdown <= -0.08) and not block_buy
    caution = sharpe < 0.50 or max_drawdown <= -0.05
    state = "normal"
    position_scale = 1.0
    if block_buy:
        state = "blocked"
        position_scale = 0.0
    elif reduce_buy:
        state = "reduced"
        position_scale = 0.25
    elif caution:
        state = "caution"
        position_scale = 0.5
    return {
        "sharpe": round(sharpe, 6),
        "max_drawdown": round(max_drawdown, 6),
        "turnover": metrics.get("turnover"),
        "state": state,
        "block_buy": block_buy,
        "reduce_buy": reduce_buy,
        "caution": caution,
        "position_scale": position_scale,
    }


def _signal_backtest_context(
    market_regime: dict[str, Any],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    if _full_shadow_mode(market_regime):
        return _observed_backtest_context(metrics)
    return _backtest_context(metrics)


def _observed_backtest_context(metrics: dict[str, Any]) -> dict[str, Any]:
    sharpe = float(metrics.get("sharpe") or 0)
    max_drawdown = float(metrics.get("max_drawdown") or 0)
    return {
        "sharpe": round(sharpe, 6),
        "max_drawdown": round(max_drawdown, 6),
        "turnover": metrics.get("turnover"),
        "state": "observed",
        "block_buy": False,
        "reduce_buy": False,
        "caution": False,
        "position_scale": 1.0,
    }


def _action_rank(action: str) -> int:
    return {"BUY": 0, "HOLD": 1, "NO_TRADE": 2}.get(action, 3)


def _gate_headline(
    backtest_context: dict[str, Any],
    market_regime: dict[str, Any],
    operation_counts: dict[str, int],
) -> str:
    buyable = operation_counts.get("buyable", 0)
    watch = operation_counts.get("watch", 0)
    risk_blocked = operation_counts.get("risk_blocked", 0)
    regime = str(market_regime.get("state") or "range")
    if regime in {"ignored", "full_shadow"}:
        return f"满仓影子组合模式：今日 {buyable} 只进入目标组合，{risk_blocked} 只因个股不可交易拦截。"
    if backtest_context.get("block_buy"):
        return (
            "今日无买入信号，因为回测闸门触发："
            f"Sharpe {backtest_context['sharpe']:.2f}, "
            f"最大回撤 {backtest_context['max_drawdown']:.2%}。"
        )
    if backtest_context.get("reduce_buy"):
        return (
            "回测闸门触发降仓："
            f"Sharpe {backtest_context['sharpe']:.2f}, "
            f"最大回撤 {backtest_context['max_drawdown']:.2%}；"
            "高置信候选仅允许小仓试探，其余进入观察。"
        )
    if regime in {"crash", "high_vol"}:
        return f"市场状态为 {regime}，先降低总暴露后再给出信号。"
    if buyable:
        return f"今日 {buyable} 只可买，{watch} 只观察，{risk_blocked} 只风险拦截。"
    return f"今日无买入信号：{watch} 只观察，{risk_blocked} 只风险拦截。"


def _full_shadow_mode(market_regime: dict[str, Any]) -> bool:
    return str(market_regime.get("state") or "") in {"ignored", "full_shadow"}
