from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import pandas as pd

from core.features import build_feature_frame
from engine.regime_transition_matrix import REGIMES


DEFAULT_HORIZONS = (5, 10, 20)


def _prepare_index_features(index_df: pd.DataFrame) -> pd.DataFrame:
    if index_df.empty:
        raise ValueError("index_df is empty")
    required = {"trade_date", "close"}
    missing = required.difference(index_df.columns)
    if missing:
        raise KeyError(f"index_df missing required columns: {sorted(missing)}")

    features = build_feature_frame(index_df.copy())
    features["trade_date"] = features["trade_date"].astype(str).str.replace(r"\.0$", "", regex=True)
    features["close"] = pd.to_numeric(features["close"], errors="coerce")
    features = features.dropna(subset=["trade_date", "close"])
    return features.sort_values("trade_date").drop_duplicates("trade_date", keep="last").reset_index(drop=True)


def build_forward_return_frame(
    regime_items: Iterable[Mapping[str, object]],
    index_df: pd.DataFrame,
    *,
    horizons: Sequence[int] = DEFAULT_HORIZONS,
) -> pd.DataFrame:
    index_features = _prepare_index_features(index_df)
    forward = index_features[["trade_date", "close", "ma120"]].copy()
    for horizon in horizons:
        if horizon <= 0:
            raise ValueError("horizons must be positive")
        forward[f"future_trade_date_{horizon}d"] = forward["trade_date"].shift(-horizon)
        forward[f"future_close_{horizon}d"] = forward["close"].shift(-horizon)
        forward[f"return_{horizon}d"] = forward[f"future_close_{horizon}d"] / forward["close"] - 1.0

    regime_df = pd.DataFrame(list(regime_items))
    if regime_df.empty:
        return pd.DataFrame(columns=["trade_date", "regime", "close", "ma120"])
    if "trade_date" not in regime_df.columns or "regime" not in regime_df.columns:
        raise KeyError("regime_items must contain trade_date and regime")

    regime_df = regime_df.copy()
    regime_df["trade_date"] = regime_df["trade_date"].astype(str).str.replace(r"\.0$", "", regex=True)
    regime_df["regime"] = regime_df["regime"].astype(str)
    result = regime_df.merge(forward, on="trade_date", how="inner")
    result["ma120_signal"] = result["close"] > result["ma120"]
    return result.sort_values("trade_date").reset_index(drop=True)


def summarize_forward_returns(
    forward_frame: pd.DataFrame,
    *,
    horizons: Sequence[int] = DEFAULT_HORIZONS,
    regimes: Sequence[str] = REGIMES,
) -> dict[str, dict[str, float | int | None]]:
    summary: dict[str, dict[str, float | int | None]] = {}
    for regime in regimes:
        regime_rows = forward_frame[forward_frame["regime"] == regime]
        regime_summary: dict[str, float | int | None] = {"observations": int(len(regime_rows))}
        for horizon in horizons:
            column = f"return_{horizon}d"
            values = pd.to_numeric(regime_rows[column], errors="coerce").dropna()
            prefix = f"{horizon}d"
            regime_summary[f"{prefix}_count"] = int(len(values))
            if values.empty:
                regime_summary[f"{prefix}_mean"] = None
                regime_summary[f"{prefix}_median"] = None
                regime_summary[f"{prefix}_win_rate"] = None
                regime_summary[f"{prefix}_std"] = None
                continue
            regime_summary[f"{prefix}_mean"] = round(float(values.mean()), 6)
            regime_summary[f"{prefix}_median"] = round(float(values.median()), 6)
            regime_summary[f"{prefix}_win_rate"] = round(float((values > 0).mean()), 6)
            regime_summary[f"{prefix}_std"] = round(float(values.std(ddof=0)), 6)
        summary[regime] = regime_summary
    return summary


def save_forward_return_summary(summary: Mapping[str, object], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
