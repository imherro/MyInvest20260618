from __future__ import annotations

from pathlib import Path
from typing import Mapping

from config import BASE_DIR


DEFAULT_POLICY_PATH = BASE_DIR / "rules" / "risk_policy.yaml"


def _clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


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


def load_risk_policy(path: str | Path = DEFAULT_POLICY_PATH) -> dict[str, dict[str, object]]:
    policy_path = Path(path)
    if not policy_path.exists():
        raise FileNotFoundError(f"risk policy not found: {policy_path}")

    policy: dict[str, dict[str, object]] = {}
    current_section: str | None = None
    for raw_line in policy_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if not raw_line.startswith(" ") and line.endswith(":"):
            current_section = line[:-1].strip()
            policy[current_section] = {}
            continue
        if current_section is None:
            raise ValueError(f"Invalid policy line outside section: {raw_line!r}")
        if ":" not in line:
            raise ValueError(f"Invalid policy line: {raw_line!r}")
        key, value = line.split(":", 1)
        policy[current_section][key.strip()] = _parse_scalar(value)

    return policy


def calculate_risk_score(signal: Mapping[str, object]) -> dict[str, object]:
    trend_strength = _clip(float(signal["trend"]))
    breadth_strength = _clip(float(signal["breadth"]))
    liquidity_strength = _clip(float(signal["liquidity"]))
    volatility_stability = _clip(float(signal["volatility"]))

    volatility_stress = 1.0 - volatility_stability
    breadth_weakness = 1.0 - breadth_strength
    trend_weakness = 1.0 - trend_strength
    liquidity_weakness = 1.0 - liquidity_strength

    risk_score = _clip(
        0.35 * volatility_stress
        + 0.25 * breadth_weakness
        + 0.25 * trend_weakness
        + 0.15 * liquidity_weakness
    )

    return {
        "risk_score": round(risk_score, 6),
        "components": {
            "volatility_stress": round(volatility_stress, 6),
            "breadth_weakness": round(breadth_weakness, 6),
            "trend_weakness": round(trend_weakness, 6),
            "liquidity_weakness": round(liquidity_weakness, 6),
        },
    }


def classify_risk_level(risk_score: float, policy: Mapping[str, Mapping[str, object]]) -> str:
    thresholds = policy.get("risk", {})
    low_max = float(thresholds.get("low_max", 0.33))
    medium_max = float(thresholds.get("medium_max", 0.66))
    if risk_score <= low_max:
        return "low"
    if risk_score <= medium_max:
        return "medium"
    return "high"


def score_risk_signal(
    signal: Mapping[str, object],
    *,
    policy: Mapping[str, Mapping[str, object]] | None = None,
) -> dict[str, object]:
    resolved_policy = load_risk_policy() if policy is None else policy
    scored = calculate_risk_score(signal)
    risk_score = float(scored["risk_score"])
    return {
        **scored,
        "risk_level": classify_risk_level(risk_score, resolved_policy),
    }
