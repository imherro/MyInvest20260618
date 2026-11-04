from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from core.data_loader import normalize_trade_date


DEFAULT_FEATURES = (
    "trend",
    "breadth",
    "liquidity",
    "volatility",
    "pressure",
    "momentum_decay",
    "liquidity_acceleration",
    "volatility_shock",
    "regime_persistence",
    "regime_score",
    "confidence",
)


@dataclass(frozen=True)
class HazardSplit:
    train_rows: list[dict[str, object]]
    test_rows: list[dict[str, object]]


def load_hazard_dataset(
    path: str | Path,
    *,
    start: str | None = None,
    end: str | None = None,
) -> list[dict[str, object]]:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("Hazard dataset must be a JSON array.")

    start_date = normalize_trade_date(start) if start else None
    end_date = normalize_trade_date(end) if end else None
    filtered: list[dict[str, object]] = []
    for row in rows:
        date_text = normalize_trade_date(row["date"])
        if start_date and date_text < start_date:
            continue
        if end_date and date_text > end_date:
            continue
        normalized = dict(row)
        normalized["date"] = date_text
        filtered.append(normalized)

    return sorted(filtered, key=lambda row: str(row["date"]))


def time_series_split(rows: Sequence[Mapping[str, object]], *, train_end: str) -> HazardSplit:
    cutoff = normalize_trade_date(train_end)
    train_rows = [dict(row) for row in rows if str(row["date"]) <= cutoff]
    test_rows = [dict(row) for row in rows if str(row["date"]) > cutoff]
    if not train_rows:
        raise ValueError("Training split is empty.")
    if not test_rows:
        raise ValueError("Test split is empty.")
    return HazardSplit(train_rows=train_rows, test_rows=test_rows)


def rows_to_matrix(
    rows: Sequence[Mapping[str, object]],
    *,
    feature_names: Sequence[str] = DEFAULT_FEATURES,
) -> tuple[np.ndarray, np.ndarray, list[dict[str, float | int]]]:
    matrix: list[list[float]] = []
    labels: list[int] = []
    feature_rows: list[dict[str, float | int]] = []
    for row in rows:
        features = row.get("features")
        if not isinstance(features, Mapping):
            raise ValueError(f"Missing features for {row.get('date')}")

        feature_row = {name: float(features.get(name, 0.0)) for name in feature_names}
        matrix.append([float(feature_row[name]) for name in feature_names])
        labels.append(int(row["label"]))
        feature_rows.append(feature_row)

    return np.asarray(matrix, dtype=float), np.asarray(labels, dtype=int), feature_rows


def standardize_train_test(train_x: np.ndarray, test_x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    means = train_x.mean(axis=0)
    scales = train_x.std(axis=0)
    scales[scales == 0.0] = 1.0
    return (train_x - means) / scales, (test_x - means) / scales, means, scales


def _sigmoid(values: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(values, -50.0, 50.0)))


def fit_logistic_regression(
    x: np.ndarray,
    y: np.ndarray,
    *,
    learning_rate: float = 0.05,
    epochs: int = 6000,
    l2: float = 0.01,
    class_weight: str = "balanced",
) -> dict[str, object]:
    if len(x) != len(y):
        raise ValueError("x and y length mismatch")
    if len(x) == 0:
        raise ValueError("Cannot train on an empty matrix.")

    y_float = y.astype(float)
    weights = np.ones(len(y_float), dtype=float)
    positives = float(y_float.sum())
    negatives = float(len(y_float) - positives)
    if class_weight == "balanced":
        if positives == 0.0 or negatives == 0.0:
            raise ValueError("Balanced class weights require both classes.")
        weights = np.where(
            y_float == 1.0,
            len(y_float) / (2.0 * positives),
            len(y_float) / (2.0 * negatives),
        )

    coefficients = np.zeros(x.shape[1], dtype=float)
    intercept = 0.0
    for _ in range(epochs):
        scores = x @ coefficients + intercept
        probabilities = _sigmoid(scores)
        error = (probabilities - y_float) * weights
        gradient = (x.T @ error) / len(y_float) + l2 * coefficients
        intercept_gradient = float(error.mean())
        coefficients -= learning_rate * gradient
        intercept -= learning_rate * intercept_gradient

    final_probabilities = _sigmoid(x @ coefficients + intercept)
    epsilon = 1e-12
    loss = -np.mean(
        weights
        * (
            y_float * np.log(final_probabilities + epsilon)
            + (1.0 - y_float) * np.log(1.0 - final_probabilities + epsilon)
        )
    )
    loss += 0.5 * l2 * float(np.dot(coefficients, coefficients))

    return {
        "coefficients": coefficients.tolist(),
        "intercept": float(intercept),
        "training_loss": float(loss),
        "learning_rate": float(learning_rate),
        "epochs": int(epochs),
        "l2": float(l2),
        "class_weight": class_weight,
    }


def predict_logistic_proba(model: Mapping[str, object], x: np.ndarray) -> np.ndarray:
    coefficients = np.asarray(model["coefficients"], dtype=float)
    intercept = float(model["intercept"])
    return _sigmoid(x @ coefficients + intercept)


def train_logistic_model(
    rows: Sequence[Mapping[str, object]],
    *,
    train_end: str,
    feature_names: Sequence[str] = DEFAULT_FEATURES,
    learning_rate: float = 0.05,
    epochs: int = 6000,
    l2: float = 0.01,
) -> dict[str, object]:
    split = time_series_split(rows, train_end=train_end)
    train_x, train_y, _ = rows_to_matrix(split.train_rows, feature_names=feature_names)
    test_x, test_y, test_feature_rows = rows_to_matrix(split.test_rows, feature_names=feature_names)
    train_scaled, test_scaled, means, scales = standardize_train_test(train_x, test_x)
    fitted = fit_logistic_regression(train_scaled, train_y, learning_rate=learning_rate, epochs=epochs, l2=l2)
    train_scores = predict_logistic_proba(fitted, train_scaled)
    test_scores = predict_logistic_proba(fitted, test_scaled)
    train_positive_rate = float(train_y.mean())

    return {
        "model": {
            "type": "logistic",
            "feature_names": list(feature_names),
            "feature_means": means.tolist(),
            "feature_scales": scales.tolist(),
            **fitted,
        },
        "split": {
            "train_end": normalize_trade_date(train_end),
            "train_observations": int(len(train_y)),
            "test_observations": int(len(test_y)),
            "train_positive_rate": round(train_positive_rate, 6),
            "test_positive_rate": round(float(test_y.mean()), 6),
            "train_positive_count": int(train_y.sum()),
            "test_positive_count": int(test_y.sum()),
        },
        "train_scores": train_scores.tolist(),
        "test_scores": test_scores.tolist(),
        "test_labels": test_y.astype(int).tolist(),
        "test_feature_rows": test_feature_rows,
    }


def save_model(model: Mapping[str, object], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(model, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
