from __future__ import annotations

from typing import Mapping


def rank_opportunities(rows: list[Mapping[str, object]]) -> list[dict[str, object]]:
    sorted_rows = sorted(
        (dict(row) for row in rows),
        key=lambda item: (float(item.get("score") or 0.0), str(item.get("code") or "")),
        reverse=True,
    )
    for index, row in enumerate(sorted_rows, start=1):
        row["rank"] = index
    return sorted_rows
