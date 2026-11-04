from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np


def _round(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 6)


def roc_auc_score(y_true: Sequence[int], y_score: Sequence[float]) -> float | None:
    y = np.asarray(y_true, dtype=int)
    scores = np.asarray(y_score, dtype=float)
    pos = scores[y == 1]
    neg = scores[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return None

    comparisons = pos[:, None] - neg[None, :]
    wins = float((comparisons > 0).sum())
    ties = float((comparisons == 0).sum())
    return (wins + 0.5 * ties) / (len(pos) * len(neg))


def precision_recall_at_rate(
    y_true: Sequence[int],
    y_score: Sequence[float],
    *,
    positive_rate: float,
) -> dict[str, float | int]:
    if positive_rate <= 0.0:
        raise ValueError("positive_rate must be positive")

    y = np.asarray(y_true, dtype=int)
    scores = np.asarray(y_score, dtype=float)
    if len(y) == 0:
        raise ValueError("Cannot evaluate an empty test set.")

    predicted_count = max(1, int(round(len(y) * positive_rate)))
    predicted_count = min(predicted_count, len(y))
    order = np.argsort(scores)[::-1]
    selected = order[:predicted_count]
    true_positives = int(y[selected].sum())
    actual_positives = int(y.sum())
    precision = true_positives / predicted_count if predicted_count else 0.0
    recall = true_positives / actual_positives if actual_positives else 0.0
    return {
        "predicted_positive_count": int(predicted_count),
        "true_positive_count": true_positives,
        "actual_positive_count": actual_positives,
        "precision": precision,
        "recall": recall,
    }


def roc_curve_points(
    y_true: Sequence[int],
    y_score: Sequence[float],
    *,
    max_points: int = 101,
) -> list[dict[str, float]]:
    y = np.asarray(y_true, dtype=int)
    scores = np.asarray(y_score, dtype=float)
    if len(y) == 0:
        return []

    unique_scores = np.unique(scores)
    if len(unique_scores) > max_points:
        quantiles = np.linspace(0.0, 1.0, max_points)
        thresholds = np.quantile(unique_scores, quantiles)[::-1]
    else:
        thresholds = unique_scores[::-1]

    positives = max(1, int(y.sum()))
    negatives = max(1, int(len(y) - y.sum()))
    curve: list[dict[str, float]] = []
    for threshold in thresholds:
        predicted = scores >= threshold
        true_positive = int(((y == 1) & predicted).sum())
        false_positive = int(((y == 0) & predicted).sum())
        curve.append(
            {
                "threshold": round(float(threshold), 6),
                "tpr": round(true_positive / positives, 6),
                "fpr": round(false_positive / negatives, 6),
            }
        )
    return curve


def evaluate_scores(
    y_true: Sequence[int],
    y_score: Sequence[float],
    *,
    positive_rate: float,
    random_precision: float | None = None,
) -> dict[str, float | int | None]:
    pr = precision_recall_at_rate(y_true, y_score, positive_rate=positive_rate)
    precision = float(pr["precision"])
    lift = None
    if random_precision and random_precision > 0.0:
        lift = precision / random_precision

    return {
        "roc_auc": _round(roc_auc_score(y_true, y_score)),
        "roc_curve": roc_curve_points(y_true, y_score),
        "precision": _round(precision),
        "recall": _round(float(pr["recall"])),
        "lift_vs_random": _round(lift),
        "predicted_positive_count": int(pr["predicted_positive_count"]),
        "true_positive_count": int(pr["true_positive_count"]),
        "actual_positive_count": int(pr["actual_positive_count"]),
    }


def evaluate_hazard_model(
    y_true: Sequence[int],
    model_scores: Sequence[float],
    *,
    positive_rate: float,
    feature_rows: Sequence[Mapping[str, float | int]],
) -> dict[str, object]:
    y = np.asarray(y_true, dtype=int)
    test_positive_rate = float(y.mean()) if len(y) else 0.0
    random_baseline = {
        "roc_auc": 0.5,
        "precision": _round(test_positive_rate),
        "recall": _round(positive_rate),
        "lift_vs_random": 1.0,
    }
    always_zero_baseline = {
        "roc_auc": 0.5,
        "precision": 0.0,
        "recall": 0.0,
        "lift_vs_random": 0.0,
    }
    volatility_scores = [
        float(row.get("volatility_shock", row.get("volatility", 0.0)))
        for row in feature_rows
    ]
    volatility_baseline = evaluate_scores(
        y,
        volatility_scores,
        positive_rate=positive_rate,
        random_precision=test_positive_rate,
    )
    model_metrics = evaluate_scores(
        y,
        model_scores,
        positive_rate=positive_rate,
        random_precision=test_positive_rate,
    )

    return {
        "model": model_metrics,
        "baselines": {
            "random": random_baseline,
            "always_zero": always_zero_baseline,
            "volatility_only": volatility_baseline,
        },
        "test_positive_rate": _round(test_positive_rate),
        "threshold_positive_rate": _round(positive_rate),
        "baseline_gap": {
            "auc_vs_random": _round((model_metrics["roc_auc"] or 0.0) - 0.5),
            "auc_vs_volatility_only": _round(
                (model_metrics["roc_auc"] or 0.0) - (volatility_baseline["roc_auc"] or 0.0)
            ),
            "precision_lift_vs_random": model_metrics["lift_vs_random"],
        },
    }


def save_evaluation_report(report: Mapping[str, object], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
