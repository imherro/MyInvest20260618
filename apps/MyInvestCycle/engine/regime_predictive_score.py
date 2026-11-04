from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd

from engine.regime_forward_returns import DEFAULT_HORIZONS
from engine.regime_transition_matrix import REGIMES


def _directional_accuracy(prediction: pd.Series, returns: pd.Series) -> float | None:
    aligned = pd.DataFrame({"prediction": prediction, "returns": returns}).dropna()
    if aligned.empty:
        return None
    actual_positive = aligned["returns"] > 0
    predicted_positive = aligned["prediction"] > 0
    return float((actual_positive == predicted_positive).mean())


def _regime_prediction(frame: pd.DataFrame, return_column: str) -> pd.Series:
    means = frame.groupby("regime")[return_column].mean()
    return frame["regime"].map(means).astype(float)


def _expanding_regime_prediction(frame: pd.DataFrame, return_column: str, future_date_column: str) -> pd.Series:
    ordered = frame.sort_values("trade_date").copy()
    predictions = pd.Series(index=ordered.index, dtype=float)
    for index, row in ordered.iterrows():
        current_date = str(row["trade_date"])
        regime = str(row["regime"])
        known_history = ordered[
            (ordered["regime"] == regime)
            & (ordered[future_date_column].astype(str) < current_date)
            & ordered[return_column].notna()
        ]
        if not known_history.empty:
            predictions.loc[index] = float(known_history[return_column].mean())
    return predictions.reindex(frame.index)


def _separation_score(frame: pd.DataFrame, return_column: str) -> float | None:
    values = pd.to_numeric(frame[return_column], errors="coerce")
    valid = frame.assign(_return=values).dropna(subset=["_return"])
    if valid.empty:
        return None
    grouped = valid.groupby("regime")["_return"].mean().dropna()
    if len(grouped) < 2:
        return 0.0
    dispersion = float(grouped.max() - grouped.min())
    volatility = float(valid["_return"].std(ddof=0))
    if volatility <= 0:
        return 0.0
    return max(0.0, min(1.0, dispersion / volatility))


def evaluate_predictive_power(
    forward_frame: pd.DataFrame,
    *,
    horizons: Sequence[int] = DEFAULT_HORIZONS,
    regimes: Sequence[str] = REGIMES,
) -> dict[str, object]:
    horizon_scores: dict[str, dict[str, float | int | None]] = {}
    regime_accuracies: list[float] = []
    ma_accuracies: list[float] = []
    always_bull_accuracies: list[float] = []
    separation_scores: list[float] = []
    return_gaps: list[float] = []

    for horizon in horizons:
        column = f"return_{horizon}d"
        future_date_column = f"future_trade_date_{horizon}d"
        if column not in forward_frame.columns:
            raise KeyError(f"Missing forward return column: {column}")
        if future_date_column not in forward_frame.columns:
            raise KeyError(f"Missing future date column: {future_date_column}")

        valid = forward_frame.copy()
        valid[column] = pd.to_numeric(valid[column], errors="coerce")
        valid = valid.dropna(subset=[column, future_date_column])
        if valid.empty:
            horizon_scores[f"{horizon}d"] = {
                "observations": 0,
                "regime_model_samples": 0,
                "regime_model": None,
                "always_bull": None,
                "ma_strategy": None,
                "random": 0.5,
                "regime_advantage": None,
                "regime_separation_score": None,
                "forward_return_gap": None,
            }
            continue

        regime_signal = _expanding_regime_prediction(valid, column, future_date_column)
        regime_accuracy = _directional_accuracy(regime_signal, valid[column])
        regime_model_samples = int(regime_signal.notna().sum())
        always_bull_accuracy = float((valid[column] > 0).mean())
        ma_accuracy = _directional_accuracy(
            valid["ma120_signal"].astype(float).where(valid["ma120_signal"], -1.0),
            valid[column],
        )
        separation = _separation_score(valid, column)
        grouped = valid.groupby("regime")[column].mean().dropna()
        return_gap = None if len(grouped) < 2 else float(grouped.max() - grouped.min())

        baseline_values = [0.5, always_bull_accuracy]
        if ma_accuracy is not None:
            baseline_values.append(ma_accuracy)
        strongest_baseline = max(baseline_values)
        advantage = None if regime_accuracy is None else regime_accuracy - strongest_baseline

        if regime_accuracy is not None:
            regime_accuracies.append(regime_accuracy)
        if ma_accuracy is not None:
            ma_accuracies.append(ma_accuracy)
        always_bull_accuracies.append(always_bull_accuracy)
        if separation is not None:
            separation_scores.append(separation)
        if return_gap is not None:
            return_gaps.append(return_gap)

        horizon_scores[f"{horizon}d"] = {
            "observations": int(len(valid)),
            "regime_model_samples": regime_model_samples,
            "regime_model": round(regime_accuracy, 6) if regime_accuracy is not None else None,
            "always_bull": round(always_bull_accuracy, 6),
            "ma_strategy": round(ma_accuracy, 6) if ma_accuracy is not None else None,
            "random": 0.5,
            "regime_advantage": round(advantage, 6) if advantage is not None else None,
            "regime_separation_score": round(separation, 6) if separation is not None else None,
            "forward_return_gap": round(return_gap, 6) if return_gap is not None else None,
        }

    predictive_power = _mean_or_none(regime_accuracies)
    baseline_ma = _mean_or_none(ma_accuracies)
    baseline_always_bull = _mean_or_none(always_bull_accuracies)
    baseline_random = 0.5
    baseline_candidates = [baseline_random]
    if baseline_ma is not None:
        baseline_candidates.append(baseline_ma)
    if baseline_always_bull is not None:
        baseline_candidates.append(baseline_always_bull)
    regime_advantage = None if predictive_power is None else predictive_power - max(baseline_candidates)

    regime_counts = {regime: int((forward_frame["regime"] == regime).sum()) for regime in regimes}
    return {
        "regime_predictive_power": None if predictive_power is None else round(predictive_power, 6),
        "baseline_ma_strategy": None if baseline_ma is None else round(baseline_ma, 6),
        "baseline_always_bull": None if baseline_always_bull is None else round(baseline_always_bull, 6),
        "baseline_random": baseline_random,
        "regime_advantage": None if regime_advantage is None else round(regime_advantage, 6),
        "regime_separation_score": _rounded_mean(separation_scores),
        "forward_return_gap": _rounded_mean(return_gaps),
        "horizons": horizon_scores,
        "regime_counts": regime_counts,
    }


def _mean_or_none(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return float(sum(values) / len(values))


def _rounded_mean(values: Sequence[float]) -> float | None:
    value = _mean_or_none(values)
    return None if value is None else round(value, 6)


def save_predictive_score(score: Mapping[str, object], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(score, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
