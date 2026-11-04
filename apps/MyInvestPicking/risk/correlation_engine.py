from __future__ import annotations

from collections import defaultdict
from typing import Any

import pandas as pd


def compute_correlation_risk(
    daily: pd.DataFrame,
    candidate_codes: list[str],
    lookback: int = 60,
    threshold: float = 0.75,
) -> dict[str, Any]:
    if daily.empty or not candidate_codes:
        return _empty_correlation_risk()

    frame = daily[daily["ts_code"].isin(candidate_codes)].copy()
    frame["close"] = pd.to_numeric(frame.get("close"), errors="coerce")
    frame = frame.dropna(subset=["ts_code", "trade_date", "close"])
    if frame.empty:
        return _empty_correlation_risk()

    close_wide = frame.pivot_table(index="trade_date", columns="ts_code", values="close")
    returns = close_wide.pct_change().tail(lookback)
    correlation = returns.corr().fillna(0)
    pairs = _high_correlation_pairs(correlation, threshold)
    clusters = _clusters_from_pairs(candidate_codes, pairs, correlation)
    score = _risk_score(clusters, len(candidate_codes))

    return {
        "lookback": lookback,
        "threshold": threshold,
        "cluster_count": len(clusters),
        "clusters": clusters,
        "high_correlation_pairs": pairs[:20],
        "concentration_risk_score": score,
    }


def _high_correlation_pairs(
    correlation: pd.DataFrame,
    threshold: float,
) -> list[dict[str, Any]]:
    pairs = []
    codes = list(correlation.columns)
    for left_index, left in enumerate(codes):
        for right in codes[left_index + 1 :]:
            value = float(correlation.loc[left, right])
            if value >= threshold:
                pairs.append(
                    {
                        "left": left,
                        "right": right,
                        "correlation": round(value, 4),
                    }
                )
    return sorted(pairs, key=lambda item: (-item["correlation"], item["left"], item["right"]))


def _clusters_from_pairs(
    candidate_codes: list[str],
    pairs: list[dict[str, Any]],
    correlation: pd.DataFrame,
) -> list[dict[str, Any]]:
    graph: dict[str, set[str]] = defaultdict(set)
    for pair in pairs:
        graph[pair["left"]].add(pair["right"])
        graph[pair["right"]].add(pair["left"])

    visited = set()
    clusters = []
    for code in sorted(candidate_codes):
        if code in visited or code not in graph:
            continue
        stack = [code]
        members = set()
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            members.add(current)
            stack.extend(sorted(graph[current] - visited))
        if len(members) > 1:
            clusters.append(_cluster_payload(len(clusters) + 1, sorted(members), correlation))
    return clusters


def _cluster_payload(cluster_id: int, codes: list[str], correlation: pd.DataFrame) -> dict[str, Any]:
    values = []
    for left_index, left in enumerate(codes):
        for right in codes[left_index + 1 :]:
            values.append(float(correlation.loc[left, right]))
    average = sum(values) / len(values) if values else 0.0
    return {
        "id": f"cluster_{cluster_id}",
        "codes": codes,
        "size": len(codes),
        "avg_correlation": round(average, 4),
    }


def _risk_score(clusters: list[dict[str, Any]], candidate_count: int) -> float:
    if not clusters or candidate_count <= 0:
        return 0.0
    largest_cluster = max(cluster["size"] for cluster in clusters)
    return round(min(1.0, largest_cluster / candidate_count), 4)


def _empty_correlation_risk() -> dict[str, Any]:
    return {
        "lookback": 60,
        "threshold": 0.75,
        "cluster_count": 0,
        "clusters": [],
        "high_correlation_pairs": [],
        "concentration_risk_score": 0.0,
    }
