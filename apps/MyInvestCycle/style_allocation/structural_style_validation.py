from __future__ import annotations

from collections import Counter
from typing import Mapping


def structural_bull_rows(rows: list[Mapping[str, object]]) -> list[dict[str, object]]:
    return [
        dict(row) for row in rows
        if str(row.get("validation_state")) == "STRUCTURAL_BULL"
    ]


def style_drift_analysis(rows: list[Mapping[str, object]]) -> dict[str, object]:
    ordered = sorted(
        {
            str(row.get("date")): str(row.get("dominant_style"))
            for row in rows
            if row.get("date") and row.get("dominant_style")
        }.items()
    )
    transitions: list[dict[str, object]] = []
    previous_style: str | None = None
    previous_date: str | None = None
    for date_text, style in ordered:
        if previous_style is not None and style != previous_style:
            transitions.append(
                {
                    "date": date_text,
                    "from": previous_style,
                    "to": style,
                    "previous_date": previous_date,
                }
            )
        previous_style = style
        previous_date = date_text
    distribution = Counter(style for _, style in ordered)
    return {
        "date_count": len(ordered),
        "dominant_style_distribution": dict(sorted(distribution.items())),
        "transition_count": len(transitions),
        "structural_bull_style_transition": transitions,
        "interpretation": (
            "Style drift is measured only inside STRUCTURAL_BULL validation dates. "
            "No transition means the frozen preference formula stayed on one dominant style in the sampled structural bull windows."
        ),
    }


def compact_structural_samples(rows: list[Mapping[str, object]], limit: int = 10) -> list[dict[str, object]]:
    result = []
    for row in sorted(rows, key=lambda item: str(item.get("date")))[-limit:]:
        result.append(
            {
                "date": row.get("date"),
                "dominant_style": row.get("dominant_style"),
                "baseline_codes": row.get("baseline_codes") or [],
                "style_aware_codes": row.get("style_aware_codes") or [],
                "baseline_return": row.get("baseline_return"),
                "style_aware_return": row.get("style_aware_return"),
                "relative_to_baseline": row.get("relative_to_baseline"),
                "style_ic": row.get("style_ic"),
                "style_scores": row.get("style_scores") or {},
            }
        )
    return result
