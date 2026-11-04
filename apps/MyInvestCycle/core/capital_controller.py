from __future__ import annotations

from pathlib import Path
from typing import Mapping

from config import BASE_DIR
from core.risk_score_engine import _clip


DEFAULT_PORTFOLIO_POLICY_PATH = BASE_DIR / "rules" / "portfolio_policy.yaml"
REGIME_KEYS = ("bull", "range", "bear", "transition")


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


def load_portfolio_policy(path: str | Path = DEFAULT_PORTFOLIO_POLICY_PATH) -> dict[str, dict[str, object]]:
    policy_path = Path(path)
    if not policy_path.exists():
        raise FileNotFoundError(f"portfolio policy not found: {policy_path}")

    policy: dict[str, dict[str, object]] = {}
    current_regime: str | None = None
    current_nested: str | None = None

    for raw_line in policy_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue

        indent = len(raw_line) - len(raw_line.lstrip(" "))
        stripped = line.strip()

        if indent == 0 and stripped.endswith(":"):
            current_regime = stripped[:-1]
            policy[current_regime] = {}
            current_nested = None
            continue

        if current_regime is None:
            raise ValueError(f"Invalid policy line outside regime section: {raw_line!r}")

        if ":" not in stripped:
            raise ValueError(f"Invalid policy line: {raw_line!r}")

        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()

        if indent == 2 and value == "":
            policy[current_regime][key] = {}
            current_nested = key
            continue

        if indent == 2:
            policy[current_regime][key] = _parse_scalar(value)
            current_nested = None
            continue

        if indent == 4 and current_nested:
            nested = policy[current_regime].setdefault(current_nested, {})
            if not isinstance(nested, dict):
                raise ValueError(f"Policy key is not a nested mapping: {current_nested}")
            nested[key] = _parse_scalar(value)
            continue

        raise ValueError(f"Unsupported policy indentation: {raw_line!r}")

    validate_portfolio_policy(policy)
    return policy


def validate_portfolio_policy(policy: Mapping[str, Mapping[str, object]]) -> None:
    missing = [regime for regime in REGIME_KEYS if regime not in policy]
    if missing:
        raise ValueError(f"Missing portfolio policy regimes: {missing}")

    for regime in REGIME_KEYS:
        regime_policy = policy[regime]
        for key in ("base_exposure", "max_exposure", "min_cash", "strategy_allocation"):
            if key not in regime_policy:
                raise ValueError(f"Missing {regime}.{key} in portfolio policy")

        base_exposure = float(regime_policy["base_exposure"])
        max_exposure = float(regime_policy["max_exposure"])
        min_cash = float(regime_policy["min_cash"])
        if not 0.0 <= min_cash <= 1.0:
            raise ValueError(f"{regime}.min_cash must be between 0 and 1")
        if not 0.0 <= max_exposure <= 1.0:
            raise ValueError(f"{regime}.max_exposure must be between 0 and 1")
        if not 0.0 <= base_exposure <= 1.0:
            raise ValueError(f"{regime}.base_exposure must be between 0 and 1")
        if max_exposure > 1.0 - min_cash + 1e-9:
            raise ValueError(f"{regime}.max_exposure violates min_cash")

        strategy_allocation = regime_policy["strategy_allocation"]
        if not isinstance(strategy_allocation, Mapping) or not strategy_allocation:
            raise ValueError(f"{regime}.strategy_allocation must be a non-empty mapping")
        total_weight = sum(float(weight) for weight in strategy_allocation.values())
        if total_weight <= 0.0:
            raise ValueError(f"{regime}.strategy_allocation weights must be positive")
        for strategy, weight in strategy_allocation.items():
            if float(weight) < 0.0:
                raise ValueError(f"{regime}.{strategy} strategy weight must not be negative")


def regime_portfolio_policy(
    policy: Mapping[str, Mapping[str, object]],
    regime: str,
) -> Mapping[str, object]:
    if regime not in policy:
        raise KeyError(f"Missing portfolio policy for regime: {regime}")
    return policy[regime]


def build_capital_control(
    risk_decision: Mapping[str, object],
    *,
    policy: Mapping[str, Mapping[str, object]] | None = None,
) -> dict[str, object]:
    resolved_policy = load_portfolio_policy() if policy is None else policy
    regime = str(risk_decision["regime"])
    regime_policy = regime_portfolio_policy(resolved_policy, regime)

    base_exposure = float(regime_policy["base_exposure"])
    risk_score = _clip(float(risk_decision["risk_score"]))
    max_exposure = min(float(regime_policy["max_exposure"]), 1.0 - float(regime_policy["min_cash"]))
    target_exposure = base_exposure * (1.0 - risk_score)
    total_exposure = _clip(target_exposure, 0.0, max_exposure)
    cash_ratio = round(1.0 - total_exposure, 6)

    return {
        "regime": regime,
        "risk_score": round(risk_score, 6),
        "base_exposure": round(base_exposure, 6),
        "target_exposure": round(target_exposure, 6),
        "total_exposure": round(total_exposure, 6),
        "cash_ratio": cash_ratio,
        "max_exposure": round(max_exposure, 6),
        "min_cash": round(float(regime_policy["min_cash"]), 6),
        "constraints": {
            "cash_plus_exposure": round(cash_ratio + total_exposure, 6),
            "min_cash_satisfied": cash_ratio + 1e-9 >= float(regime_policy["min_cash"]),
            "max_exposure_satisfied": total_exposure <= max_exposure + 1e-9,
        },
    }
