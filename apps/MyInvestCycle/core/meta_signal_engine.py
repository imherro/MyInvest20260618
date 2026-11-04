from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

from config import BASE_DIR
from core.regime_risk_divergence import calculate_regime_risk_divergence


DEFAULT_META_EDGE_RULES_PATH = BASE_DIR / "rules" / "meta_edge_rules.yaml"
SIGNAL_KEYS = (
    "regime_risk_divergence",
    "hazard_mismatch",
    "portfolio_gap",
    "regime_age",
)


def _clip(value: float) -> float:
    return max(0.0, min(1.0, value))


def _parse_scalar(value: str) -> object:
    text = value.strip()
    if text.lower() == "true":
        return True
    if text.lower() == "false":
        return False
    try:
        return float(text)
    except ValueError:
        return text


def load_meta_edge_rules(path: str | Path = DEFAULT_META_EDGE_RULES_PATH) -> dict[str, dict[str, object]]:
    rules_path = Path(path)
    if not rules_path.exists():
        raise FileNotFoundError(f"meta edge rules not found: {rules_path}")

    rules: dict[str, dict[str, object]] = {}
    current_section: str | None = None
    for raw_line in rules_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        stripped = line.strip()
        if indent == 0 and stripped.endswith(":"):
            current_section = stripped[:-1]
            rules[current_section] = {}
            continue
        if current_section is None or ":" not in stripped:
            raise ValueError(f"Invalid meta edge rule line: {raw_line!r}")
        key, value = stripped.split(":", 1)
        rules[current_section][key.strip()] = _parse_scalar(value)

    return rules


def build_meta_edge_signal(
    *,
    regime_signal: Mapping[str, object],
    risk_decision: Mapping[str, object],
    portfolio: Mapping[str, object],
    strategy_route: Mapping[str, object],
    hazard_rows: Sequence[Mapping[str, object]] | None = None,
    survival_rows: Sequence[Mapping[str, object]] | None = None,
    rules: Mapping[str, Mapping[str, object]] | None = None,
) -> dict[str, object]:
    resolved_rules = load_meta_edge_rules() if rules is None else rules
    thresholds = resolved_rules.get("thresholds", {})
    weights = resolved_rules.get("weights", {})

    signal_details = {
        "regime_risk_divergence": calculate_regime_risk_divergence(regime_signal, risk_decision),
        "hazard_mismatch": _hazard_mismatch_signal(regime_signal, hazard_rows or (), resolved_rules),
        "portfolio_gap": _portfolio_strategy_gap_signal(portfolio, strategy_route),
        "regime_age": _regime_age_signal(regime_signal, survival_rows or ()),
    }
    signal_strengths = {
        key: round(float(detail["strength"]), 6)
        for key, detail in signal_details.items()
    }
    active_signals = [
        key
        for key in SIGNAL_KEYS
        if signal_strengths[key] >= float(thresholds.get(key, 1.0))
    ]
    total_weight = sum(float(weights.get(key, 1.0)) for key in SIGNAL_KEYS)
    weighted_score = sum(signal_strengths[key] * float(weights.get(key, 1.0)) for key in SIGNAL_KEYS)
    meta_edge_score = _clip(weighted_score / total_weight if total_weight > 0 else 0.0)

    return {
        "as_of": regime_signal.get("as_of"),
        "engine": "meta_signal_engine_v1",
        "meta_edge_score": round(meta_edge_score, 6),
        "meta_edge_level": _meta_edge_level(meta_edge_score),
        "signals": active_signals,
        "signal_strengths": signal_strengths,
        "signal_details": signal_details,
        "interpretation": _meta_edge_interpretation(meta_edge_score, active_signals),
        "constraints": {
            "prediction_engine": False,
            "stock_selection": False,
            "trade_execution": False,
            "read_only": True,
            "detects_system_inconsistency_only": True,
        },
    }


def _event_rate(rows: Sequence[Mapping[str, object]]) -> float:
    if not rows:
        return 0.0
    events = sum(1 for row in rows if int(row.get("label", row.get("event", 0))) == 1)
    return events / len(rows)


def _hazard_mismatch_signal(
    regime_signal: Mapping[str, object],
    hazard_rows: Sequence[Mapping[str, object]],
    rules: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    as_of = str(regime_signal.get("as_of", ""))
    regime = str(regime_signal.get("regime", "unknown"))
    windows = rules.get("windows", {})
    recent_window = int(float(windows.get("hazard_recent", 20)))
    baseline_window = int(float(windows.get("hazard_baseline", 80)))
    sorted_rows = sorted(
        [row for row in hazard_rows if str(row.get("date", "")) <= as_of],
        key=lambda row: str(row.get("date", "")),
    )
    recent_rows = sorted_rows[-recent_window:]
    baseline_rows = sorted_rows[-(baseline_window + recent_window):-recent_window] if len(sorted_rows) > recent_window else []
    recent_rate = _event_rate(recent_rows)
    baseline_rate = _event_rate(baseline_rows)
    increase = max(recent_rate - baseline_rate, 0.0)
    stable_regime = regime in {"bull", "range", "bear"}
    strength = _clip(increase if stable_regime else increase * 0.35)
    return {
        "name": "hazard_mismatch",
        "strength": round(strength, 6),
        "recent_event_rate": round(recent_rate, 6),
        "baseline_event_rate": round(baseline_rate, 6),
        "event_rate_increase": round(increase, 6),
        "recent_window": len(recent_rows),
        "baseline_window": len(baseline_rows),
        "stable_regime": stable_regime,
        "interpretation": (
            "hazard is accelerating while regime remains stable"
            if strength > 0
            else "hazard does not show current acceleration mismatch"
        ),
    }


def _portfolio_strategy_gap_signal(
    portfolio: Mapping[str, object],
    strategy_route: Mapping[str, object],
) -> dict[str, object]:
    portfolio_weights = {
        str(key): float(value)
        for key, value in (portfolio.get("strategy_allocation") or {}).items()
    }
    strategy_weights = {
        str(key): float(value)
        for key, value in (strategy_route.get("strategy_budget") or {}).items()
    }
    keys = sorted(set(portfolio_weights) | set(strategy_weights))
    l1_distance = sum(abs(portfolio_weights.get(key, 0.0) - strategy_weights.get(key, 0.0)) for key in keys)
    strength = _clip(l1_distance / 2.0)
    return {
        "name": "portfolio_gap",
        "strength": round(strength, 6),
        "l1_distance": round(l1_distance, 6),
        "portfolio_allocation": {key: round(portfolio_weights.get(key, 0.0), 6) for key in keys},
        "strategy_budget": {key: round(strategy_weights.get(key, 0.0), 6) for key in keys},
        "interpretation": (
            "portfolio allocation and strategy budget are materially different"
            if strength > 0.2
            else "portfolio allocation and strategy budget are aligned"
        ),
    }


def _regime_age_signal(
    regime_signal: Mapping[str, object],
    survival_rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    as_of = str(regime_signal.get("as_of", ""))
    current_regime = str(regime_signal.get("regime", "unknown"))
    sorted_rows = sorted(
        [row for row in survival_rows if str(row.get("date", "")) <= as_of],
        key=lambda row: str(row.get("date", "")),
    )
    latest = sorted_rows[-1] if sorted_rows else {}
    latest_features = latest.get("features") if isinstance(latest.get("features"), Mapping) else {}
    latest_regime = str(latest.get("structural_regime", latest.get("raw_regime", current_regime)))
    current_age = int(float(latest_features.get("structural_regime_age", latest.get("duration", 0)))) if latest else 0
    comparable_ages = []
    for row in sorted_rows:
        row_regime = str(row.get("structural_regime", row.get("raw_regime", "")))
        features = row.get("features") if isinstance(row.get("features"), Mapping) else {}
        age = int(float(features.get("structural_regime_age", row.get("duration", 0))))
        if row_regime == latest_regime and age > 0:
            comparable_ages.append(age)

    percentile = (
        sum(1 for age in comparable_ages if age <= current_age) / len(comparable_ages)
        if comparable_ages and current_age > 0
        else 0.0
    )
    strength = _clip(percentile)
    return {
        "name": "regime_age",
        "strength": round(strength, 6),
        "current_regime": current_regime,
        "survival_regime": latest_regime,
        "current_age": current_age,
        "historical_sample": len(comparable_ages),
        "age_percentile": round(percentile, 6),
        "interpretation": (
            "current regime age is historically stretched"
            if percentile >= 0.8
            else "current regime age is not historically stretched"
        ),
    }


def _meta_edge_level(score: float) -> str:
    if score >= 0.65:
        return "high"
    if score >= 0.35:
        return "medium"
    if score >= 0.15:
        return "low"
    return "quiet"


def _meta_edge_interpretation(score: float, active_signals: Sequence[str]) -> str:
    if score >= 0.65:
        return "system fragility is high; multiple layers are contradicting each other"
    if score >= 0.35:
        return "system fragility is increasing; review active meta signals before raising risk"
    if active_signals:
        return "isolated system inconsistencies are visible but not dominant"
    return "system layers are broadly aligned; no material meta edge signal is active"
