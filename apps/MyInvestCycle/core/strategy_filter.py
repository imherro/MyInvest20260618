from __future__ import annotations

from pathlib import Path
from typing import Mapping

from config import BASE_DIR


DEFAULT_STRATEGY_POLICY_PATH = BASE_DIR / "rules" / "strategy_policy.yaml"
REGIME_KEYS = ("bull", "range", "bear", "transition")


def _parse_scalar(value: str) -> object:
    text = value.strip()
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [item.strip() for item in inner.split(",")]
    if text.lower() == "true":
        return True
    if text.lower() == "false":
        return False
    try:
        return float(text)
    except ValueError:
        return text


def load_strategy_policy(path: str | Path = DEFAULT_STRATEGY_POLICY_PATH) -> dict[str, dict[str, object]]:
    policy_path = Path(path)
    if not policy_path.exists():
        raise FileNotFoundError(f"strategy policy not found: {policy_path}")

    policy: dict[str, dict[str, object]] = {}
    current_section: str | None = None
    current_nested: str | None = None

    for raw_line in policy_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue

        indent = len(raw_line) - len(raw_line.lstrip(" "))
        stripped = line.strip()

        if indent == 0 and stripped.endswith(":"):
            current_section = stripped[:-1]
            policy[current_section] = {}
            current_nested = None
            continue

        if current_section is None or ":" not in stripped:
            raise ValueError(f"Invalid strategy policy line: {raw_line!r}")

        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()

        if indent == 2 and value == "":
            policy[current_section][key] = {}
            current_nested = key
            continue

        if indent == 2:
            policy[current_section][key] = _parse_scalar(value)
            current_nested = None
            continue

        if indent == 4 and current_nested:
            nested = policy[current_section].setdefault(current_nested, {})
            if not isinstance(nested, dict):
                raise ValueError(f"Strategy policy key is not nested: {current_nested}")
            nested[key] = _parse_scalar(value)
            continue

        raise ValueError(f"Unsupported strategy policy indentation: {raw_line!r}")

    validate_strategy_policy(policy)
    return policy


def _as_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def validate_strategy_policy(policy: Mapping[str, Mapping[str, object]]) -> None:
    missing = [regime for regime in REGIME_KEYS if regime not in policy]
    if missing:
        raise ValueError(f"Missing strategy policy regimes: {missing}")
    if "risk" not in policy:
        raise ValueError("Missing risk section in strategy policy")
    if "strategies" not in policy:
        raise ValueError("Missing strategies section in strategy policy")

    for regime in REGIME_KEYS:
        regime_policy = policy[regime]
        if "enabled" not in regime_policy or "disabled" not in regime_policy:
            raise ValueError(f"{regime} must define enabled and disabled strategy lists")

    for strategy, strategy_policy in policy["strategies"].items():
        if not isinstance(strategy_policy, Mapping):
            raise ValueError(f"Strategy config must be a mapping: {strategy}")
        penalty = float(strategy_policy.get("risk_penalty", 0.0))
        if penalty < 0.0 or penalty >= 1.0:
            raise ValueError(f"{strategy}.risk_penalty must be >= 0 and < 1")


def filter_strategies(
    portfolio_allocation: Mapping[str, object],
    *,
    policy: Mapping[str, Mapping[str, object]] | None = None,
) -> dict[str, object]:
    resolved_policy = load_strategy_policy() if policy is None else policy
    regime = str(portfolio_allocation["regime"])
    risk_score = float(portfolio_allocation["risk_score"])
    regime_policy = resolved_policy[regime]
    enabled_policy = set(_as_list(regime_policy.get("enabled")))
    disabled_policy = set(_as_list(regime_policy.get("disabled")))
    candidate_weights = portfolio_allocation.get("strategy_allocation", {})
    if not isinstance(candidate_weights, Mapping):
        raise ValueError("portfolio_allocation.strategy_allocation must be a mapping")

    high_risk_disabled: set[str] = set()
    risk_policy = resolved_policy.get("risk", {})
    high_risk_threshold = float(risk_policy.get("high_risk_threshold", 1.0))
    if risk_score > high_risk_threshold:
        high_risk_disabled = set(_as_list(risk_policy.get("high_risk_disabled")))

    candidates = set(str(strategy) for strategy in candidate_weights)
    observed = sorted(candidates | disabled_policy | high_risk_disabled)
    enabled_strategies: list[str] = []
    disabled_reason: dict[str, str] = {}

    for strategy in observed:
        if strategy in disabled_policy:
            disabled_reason[strategy] = f"{regime} regime"
            continue
        if strategy in high_risk_disabled:
            disabled_reason[strategy] = f"risk_score>{high_risk_threshold:g}"
            continue
        if enabled_policy and strategy not in enabled_policy:
            if strategy in candidates:
                disabled_reason[strategy] = f"not enabled for {regime}"
            continue
        if strategy in candidates:
            enabled_strategies.append(strategy)

    return {
        "regime": regime,
        "risk_score": round(risk_score, 6),
        "enabled_strategies": enabled_strategies,
        "disabled_strategies": sorted(disabled_reason),
        "disabled_reason": disabled_reason,
        "policy_enabled": sorted(enabled_policy),
        "policy_disabled": sorted(disabled_policy),
        "risk_gate_disabled": sorted(high_risk_disabled),
    }
