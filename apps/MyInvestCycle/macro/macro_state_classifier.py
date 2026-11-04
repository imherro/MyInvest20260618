from __future__ import annotations

from typing import Mapping


MACRO_STATES = ("BEAR", "BOTTOMING", "RECOVERY", "BULL", "OVERHEATED", "RANGE")


def _score(components: Mapping[str, object], name: str) -> float | None:
    item = components.get(name)
    if isinstance(item, Mapping):
        value = item.get("score")
        return None if value is None else float(value)
    return None


def classify_macro_state(macro_score: float | None, components: Mapping[str, object]) -> str:
    if macro_score is None:
        return "RANGE"

    valuation = _score(components, "valuation")
    credit = _score(components, "credit")
    economy = _score(components, "economy")
    external = _score(components, "external")

    if valuation is not None and valuation >= 85 and credit is not None and credit < 55:
        return "OVERHEATED"
    if macro_score <= 38 or (credit is not None and credit <= 35 and economy is not None and economy <= 45):
        return "BEAR"
    if 38 < macro_score < 55 and credit is not None and credit >= 45:
        return "BOTTOMING"
    if valuation is None and macro_score >= 58 and (credit is None or credit >= 50):
        return "RECOVERY"
    if macro_score >= 72 and (credit is None or credit >= 60) and (external is None or external >= 45):
        return "BULL"
    if macro_score >= 58 and (credit is None or credit >= 50):
        return "RECOVERY"
    return "RANGE"
