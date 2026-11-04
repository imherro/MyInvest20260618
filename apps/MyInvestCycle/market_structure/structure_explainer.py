from __future__ import annotations

from typing import Mapping


STATE_LABELS = {
    "BULL_BROADENING": "指数趋势强且宽度扩散",
    "BULL_DIVERGENCE": "指数强但宽度不足",
    "BULL_PULLBACK": "长期趋势未破的牛市回撤",
    "STRUCTURAL_BULL_ROTATION": "宽基一般但行业/主题主线轮动",
    "BEAR_RALLY": "弱趋势中的反弹",
    "BEAR_BREAKDOWN": "趋势和宽度同步恶化",
    "RANGE_ACCUMULATION": "震荡蓄势或结构未确认",
}


def _score_text(name: str, value: object) -> str:
    if value is None:
        return f"{name}: missing."
    number = float(value)
    if number >= 70:
        return f"{name}: strong ({number:.1f})."
    if number >= 45:
        return f"{name}: neutral ({number:.1f})."
    return f"{name}: weak ({number:.1f})."


def explain_structure(state: str, metrics: Mapping[str, object]) -> list[str]:
    explanation = [f"structure_state={state}: {STATE_LABELS.get(state, state)}."]
    explanation.append(_score_text("index_trend", metrics.get("index_trend")))
    explanation.append(_score_text("breadth", metrics.get("breadth")))
    explanation.append(_score_text("liquidity", metrics.get("liquidity")))
    explanation.append(_score_text("pullback_health", metrics.get("pullback_health")))

    if metrics.get("industry_strength") is None:
        explanation.append("industry/theme strength is not available in V2.3.1; structural bull rotation requires V2.3.2 data.")
    else:
        explanation.append(_score_text("industry_strength", metrics.get("industry_strength")))

    missing = metrics.get("missing_inputs") or []
    if missing:
        explanation.append(f"Missing inputs reduce confidence: {', '.join(str(item) for item in missing)}.")
    return explanation
