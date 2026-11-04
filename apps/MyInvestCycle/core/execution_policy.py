from __future__ import annotations

from pathlib import Path
from typing import Mapping

from config import BASE_DIR


DEFAULT_EXECUTION_POLICY_PATH = BASE_DIR / "rules" / "execution_policy.yaml"
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


def _as_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def load_execution_policy(path: str | Path = DEFAULT_EXECUTION_POLICY_PATH) -> dict[str, dict[str, object]]:
    policy_path = Path(path)
    if not policy_path.exists():
        raise FileNotFoundError(f"execution policy not found: {policy_path}")

    policy: dict[str, dict[str, object]] = {}
    current_section: str | None = None
    for raw_line in policy_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        stripped = line.strip()
        indent = len(raw_line) - len(raw_line.lstrip(" "))

        if indent == 0 and stripped.endswith(":"):
            current_section = stripped[:-1]
            policy[current_section] = {}
            continue

        if current_section is None or indent != 2 or ":" not in stripped:
            raise ValueError(f"Invalid execution policy line: {raw_line!r}")
        key, value = stripped.split(":", 1)
        policy[current_section][key.strip()] = _parse_scalar(value)

    validate_execution_policy(policy)
    return policy


def validate_execution_policy(policy: Mapping[str, Mapping[str, object]]) -> None:
    missing = [regime for regime in REGIME_KEYS if regime not in policy]
    if missing:
        raise ValueError(f"Missing execution policy regimes: {missing}")
    if "risk" not in policy:
        raise ValueError("Missing risk section in execution policy")
    for regime in REGIME_KEYS:
        regime_policy = policy[regime]
        for key in ("execution_mode", "reference_exposure", "allow", "forbid"):
            if key not in regime_policy:
                raise ValueError(f"Missing {regime}.{key} in execution policy")
        reference_exposure = float(regime_policy["reference_exposure"])
        if reference_exposure < 0.0 or reference_exposure > 1.0:
            raise ValueError(f"{regime}.reference_exposure must be between 0 and 1")


def regime_execution_policy(
    policy: Mapping[str, Mapping[str, object]],
    regime: str,
) -> Mapping[str, object]:
    if regime not in policy:
        raise KeyError(f"Missing execution policy for regime: {regime}")
    return policy[regime]


def list_policy_value(policy: Mapping[str, object], key: str) -> list[str]:
    return _as_list(policy.get(key))
