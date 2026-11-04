from __future__ import annotations

from pathlib import Path

import pandas as pd


def load_universe(path: str | Path) -> list[dict[str, object]]:
    frame = pd.read_csv(path)
    rows: list[dict[str, object]] = []
    for item in frame.to_dict("records"):
        if str(item.get("enabled", "true")).strip().lower() not in {"true", "1", "yes", "y"}:
            continue
        if not str(item.get("symbol", "")).strip():
            continue
        rows.append(item)
    return rows
