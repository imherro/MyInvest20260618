from __future__ import annotations

from typing import Mapping


def _component_text(name: str, score: float | None) -> str:
    if score is None:
        return f"{name}: missing, weight redistributed."
    if score >= 70:
        return f"{name}: supportive ({score:.1f})."
    if score >= 45:
        return f"{name}: neutral ({score:.1f})."
    return f"{name}: pressure ({score:.1f})."


def explain_macro_state(
    *,
    macro_state: str,
    macro_score: float | None,
    components: Mapping[str, Mapping[str, object]],
    data_quality: Mapping[str, object],
) -> list[str]:
    explanation = [
        f"macro_state={macro_state}, macro_score={'missing' if macro_score is None else round(macro_score, 1)}.",
    ]
    for component in ("valuation", "credit", "economy", "external"):
        score = components.get(component, {}).get("score")
        explanation.append(_component_text(component, None if score is None else float(score)))

    missing = data_quality.get("missing_indicators") or []
    if missing:
        explanation.append(f"Missing indicators reduce confidence: {', '.join(str(item) for item in missing)}.")

    estimated_ratio = data_quality.get("estimated_ratio")
    if isinstance(estimated_ratio, (float, int)) and estimated_ratio > 0:
        explanation.append(f"Estimated release dates/proxy records ratio: {estimated_ratio:.1%}.")

    return explanation
