from __future__ import annotations

from typing import Any


def evaluate_concentration_risk(
    positions: list[dict[str, Any]],
    clusters: list[dict[str, Any]],
    cluster_warning_threshold: float = 0.45,
) -> dict[str, Any]:
    weight_by_code = {
        str(position["code"]): float(position.get("weight") or 0)
        for position in positions
    }
    cluster_exposure = {}
    warnings = []
    for cluster in clusters:
        exposure = round(sum(weight_by_code.get(code, 0.0) for code in cluster["codes"]), 6)
        cluster_exposure[cluster["id"]] = exposure
        if exposure > cluster_warning_threshold:
            warnings.append(
                {
                    "cluster": cluster["id"],
                    "exposure": exposure,
                    "threshold": cluster_warning_threshold,
                }
            )

    max_cluster_exposure = max(cluster_exposure.values(), default=0.0)
    return {
        "cluster_exposure": cluster_exposure,
        "max_cluster_exposure": round(max_cluster_exposure, 6),
        "warning_threshold": cluster_warning_threshold,
        "warnings": warnings,
        "concentration_score": round(min(1.0, max_cluster_exposure / cluster_warning_threshold), 4)
        if cluster_warning_threshold > 0
        else 0.0,
    }
