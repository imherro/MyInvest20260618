from __future__ import annotations

from typing import Mapping


TOP_N_VALUES = (3, 5)


def select_top_n(rows: list[Mapping[str, object]], top_n: int) -> list[dict[str, object]]:
    ordered = sorted(
        (dict(row) for row in rows),
        key=lambda row: (float(row.get("score") or 0.0), str(row.get("code") or "")),
        reverse=True,
    )
    return ordered[:top_n]


def selection_codes(rows: list[Mapping[str, object]]) -> set[str]:
    return {str(row["code"]) for row in rows}


def turnover_proxy(previous_codes: set[str] | None, current_codes: set[str]) -> float | None:
    if previous_codes is None or not current_codes:
        return None
    overlap = len(previous_codes & current_codes)
    return round(1.0 - overlap / len(current_codes), 6)
