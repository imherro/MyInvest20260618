from __future__ import annotations

from typing import Mapping


SOURCE_LABELS = {
    "bull": ("bull_support", "bull_drag"),
    "range": ("range_support", "range_cost"),
    "bear": ("bear_protection", "bear_cost"),
    "transition": ("transition_support", "transition_cost"),
}


def _source_key(regime: str, contribution: float) -> str:
    positive_key, negative_key = SOURCE_LABELS.get(regime, (f"{regime}_support", f"{regime}_cost"))
    return positive_key if contribution >= 0 else negative_key


def _round(value: object, digits: int = 6) -> float:
    return round(float(value), digits)


def _regime_name(regime: str) -> str:
    labels = {
        "bull": "bull",
        "range": "range",
        "bear": "bear",
        "transition": "transition",
    }
    return labels.get(regime, regime)


def _interpretation(attribution: Mapping[str, object], sources: Mapping[str, float]) -> list[str]:
    summary = attribution.get("summary") if isinstance(attribution.get("summary"), Mapping) else {}
    largest_drag = summary.get("largest_drag_regime")
    largest_positive = summary.get("largest_positive_regime")
    drawdown_reduction = float(summary.get("drawdown_reduction", 0.0) or 0.0)
    total_alpha = float(summary.get("total_alpha", 0.0) or 0.0)

    lines = []
    if total_alpha < 0:
        lines.append("The shadow system underperformed the 510500 benchmark on cumulative alpha.")
    elif total_alpha > 0:
        lines.append("The shadow system outperformed the 510500 benchmark on cumulative alpha.")
    else:
        lines.append("The shadow system matched the 510500 benchmark on cumulative alpha.")

    if largest_drag:
        lines.append(f"The largest drag came from {_regime_name(str(largest_drag))} regime exposure.")
    if largest_positive:
        lines.append(f"The largest positive contribution came from {_regime_name(str(largest_positive))} regime exposure.")
    if drawdown_reduction > 0:
        lines.append("The system's measurable value is drawdown reduction rather than raw return alpha.")
    if not sources:
        lines.append("No regime source contribution was available.")
    return lines


def build_alpha_decomposition(attribution: Mapping[str, object]) -> dict[str, object]:
    regimes = attribution.get("regime_performance")
    if not isinstance(regimes, Mapping):
        raise ValueError("attribution missing regime_performance")

    sources: dict[str, float] = {}
    for regime, payload in regimes.items():
        if not isinstance(payload, Mapping):
            continue
        contribution = _round(payload.get("daily_alpha_contribution", 0.0))
        source_key = _source_key(str(regime), contribution)
        sources[source_key] = round(sources.get(source_key, 0.0) + contribution, 6)

    positive_sources = {
        source: value for source, value in sources.items() if value > 0
    }
    negative_sources = {
        source: value for source, value in sources.items() if value < 0
    }
    largest_positive = max(positive_sources.items(), key=lambda item: item[1], default=(None, 0.0))
    largest_negative = min(negative_sources.items(), key=lambda item: item[1], default=(None, 0.0))
    summary = attribution.get("summary") if isinstance(attribution.get("summary"), Mapping) else {}

    return {
        "total_alpha": _round(summary.get("total_alpha", 0.0)),
        "additive_daily_alpha": _round(summary.get("additive_daily_alpha", 0.0)),
        "sources": sources,
        "positive_sources": positive_sources,
        "negative_sources": negative_sources,
        "largest_positive_source": {
            "source": largest_positive[0],
            "contribution": round(float(largest_positive[1]), 6),
        },
        "largest_negative_source": {
            "source": largest_negative[0],
            "contribution": round(float(largest_negative[1]), 6),
        },
        "risk_adjusted": {
            "max_drawdown_shadow": _round(summary.get("max_drawdown_shadow", 0.0)),
            "max_drawdown_benchmark": _round(summary.get("max_drawdown_benchmark", 0.0)),
            "drawdown_reduction": _round(summary.get("drawdown_reduction", 0.0)),
        },
        "interpretation": _interpretation(attribution, sources),
    }
