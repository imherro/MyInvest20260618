from __future__ import annotations

import math
from typing import Iterable, Mapping

import pandas as pd


FACTOR_KEYS = ("momentum", "relative_strength", "trend_quality", "risk_adjusted", "persistence")


def _mean(values: Iterable[float]) -> float | None:
    clean = [float(value) for value in values if not math.isnan(float(value))]
    if not clean:
        return None
    return sum(clean) / len(clean)


def spearman_ic(rows: list[Mapping[str, object]], score_key: str, return_key: str = "future_return") -> float | None:
    values = []
    for row in rows:
        try:
            score = float(row[score_key])
            future_return = float(row[return_key])
        except (TypeError, ValueError, KeyError):
            continue
        if math.isnan(score) or math.isnan(future_return):
            continue
        values.append((score, future_return))
    if len(values) < 3:
        return None
    frame = pd.DataFrame(values, columns=["score", "future_return"])
    corr = frame["score"].rank(method="average").corr(frame["future_return"].rank(method="average"))
    if pd.isna(corr):
        return None
    return round(float(corr), 6)


def grouped_return_spread(rows: list[Mapping[str, object]], *, score_key: str = "score") -> dict[str, object]:
    valid: list[dict[str, float]] = []
    for row in rows:
        try:
            valid.append({"score": float(row[score_key]), "future_return": float(row["future_return"])})
        except (TypeError, ValueError, KeyError):
            continue
    if len(valid) < 6:
        return {"top_bucket_return": None, "bottom_bucket_return": None, "spread": None, "bucket_size": 0}
    ordered = sorted(valid, key=lambda item: item["score"], reverse=True)
    bucket_size = max(1, round(len(ordered) * 0.10))
    top = _mean(item["future_return"] for item in ordered[:bucket_size])
    bottom = _mean(item["future_return"] for item in ordered[-bucket_size:])
    spread = None if top is None or bottom is None else top - bottom
    return {
        "top_bucket_return": None if top is None else round(top, 6),
        "bottom_bucket_return": None if bottom is None else round(bottom, 6),
        "spread": None if spread is None else round(spread, 6),
        "bucket_size": bucket_size,
    }


def summarize_forward_validation(observations: list[Mapping[str, object]]) -> dict[str, object]:
    by_date: dict[str, list[Mapping[str, object]]] = {}
    for row in observations:
        by_date.setdefault(str(row["date"]), []).append(row)

    daily_ics: list[float] = []
    spreads: list[float] = []
    top_returns: list[float] = []
    bottom_returns: list[float] = []
    factor_ics: dict[str, list[float]] = {key: [] for key in FACTOR_KEYS}
    for rows in by_date.values():
        ic = spearman_ic(rows, "score")
        if ic is not None:
            daily_ics.append(ic)
        grouped = grouped_return_spread(rows)
        if grouped["spread"] is not None:
            spreads.append(float(grouped["spread"]))
            top_returns.append(float(grouped["top_bucket_return"]))
            bottom_returns.append(float(grouped["bottom_bucket_return"]))
        for factor in FACTOR_KEYS:
            factor_ic = spearman_ic(rows, factor)
            if factor_ic is not None:
                factor_ics[factor].append(factor_ic)

    return {
        "observation_count": len(observations),
        "date_count": len(by_date),
        "rank_ic": None if not daily_ics else round(sum(daily_ics) / len(daily_ics), 6),
        "top_bucket_return": None if not top_returns else round(sum(top_returns) / len(top_returns), 6),
        "bottom_bucket_return": None if not bottom_returns else round(sum(bottom_returns) / len(bottom_returns), 6),
        "spread": None if not spreads else round(sum(spreads) / len(spreads), 6),
        "factor_ic": {
            factor: None if not values else round(sum(values) / len(values), 6)
            for factor, values in factor_ics.items()
        },
    }
