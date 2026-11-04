from __future__ import annotations

import math

import numpy as np
import pandas as pd


def _close_series(df: pd.DataFrame, price_col: str = "close") -> pd.Series:
    if price_col not in df.columns:
        raise KeyError(f"Missing required column: {price_col}")
    return pd.to_numeric(df[price_col], errors="coerce")


def calc_ma(df: pd.DataFrame, window: int, price_col: str = "close") -> pd.Series:
    close = _close_series(df, price_col)
    return close.rolling(window=window, min_periods=window).mean()


def calc_ma_slope(
    df: pd.DataFrame,
    window: int,
    price_col: str = "close",
    slope_periods: int = 5,
) -> pd.Series:
    ma = calc_ma(df, window, price_col)
    return ma.pct_change(periods=slope_periods)


def price_above_ma(
    df: pd.DataFrame,
    window: int = 120,
    price_col: str = "close",
) -> pd.Series:
    close = _close_series(df, price_col)
    ma = calc_ma(df, window, price_col)
    return (close > ma).astype(float)


def calc_volatility(
    df: pd.DataFrame,
    window: int = 20,
    price_col: str = "close",
    annualize: bool = True,
) -> pd.Series:
    close = _close_series(df, price_col)
    returns = close.pct_change()
    volatility = returns.rolling(window=window, min_periods=max(5, window // 2)).std()
    if annualize:
        volatility = volatility * math.sqrt(252)
    return volatility


def _window_max_drawdown(values: np.ndarray) -> float:
    series = pd.Series(values)
    running_peak = series.cummax()
    drawdown = series / running_peak - 1.0
    return float(drawdown.min())


def calc_max_drawdown(
    df: pd.DataFrame,
    window: int = 60,
    price_col: str = "close",
) -> pd.Series:
    close = _close_series(df, price_col)
    return close.rolling(window=window, min_periods=max(10, window // 3)).apply(
        _window_max_drawdown,
        raw=True,
    )


def calc_breadth_proxy(
    df: pd.DataFrame,
    window: int = 20,
    price_col: str = "close",
) -> pd.Series:
    """Placeholder breadth score based on positive index-return frequency."""
    close = _close_series(df, price_col)
    returns = close.pct_change()
    positive_ratio = returns.gt(0).rolling(window=window, min_periods=max(5, window // 2)).mean()
    return positive_ratio.fillna(0.5).clip(lower=0.0, upper=1.0)


def normalize_all_scores(
    df: pd.DataFrame,
    specs: dict[str, tuple[float, float, bool]],
) -> pd.DataFrame:
    """Normalize columns to 0-1 using {column: (low, high, invert)} specs."""
    result = df.copy()
    for column, (low, high, invert) in specs.items():
        if column not in result.columns:
            raise KeyError(f"Missing column for normalization: {column}")
        if high <= low:
            raise ValueError(f"Invalid range for {column}: high must be greater than low")
        normalized = (pd.to_numeric(result[column], errors="coerce") - low) / (high - low)
        normalized = normalized.clip(lower=0.0, upper=1.0)
        result[f"{column}_score"] = 1.0 - normalized if invert else normalized
    return result


def build_feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    result["ma20"] = calc_ma(result, 20)
    result["ma60"] = calc_ma(result, 60)
    result["ma120"] = calc_ma(result, 120)
    result["ma20_slope"] = calc_ma_slope(result, 20)
    result["above_ma120"] = price_above_ma(result, 120)
    result["return_60"] = _close_series(result).pct_change(periods=60)
    result["volatility_20"] = calc_volatility(result, 20)
    result["max_drawdown_60"] = calc_max_drawdown(result, 60)
    result["breadth_proxy"] = calc_breadth_proxy(result, 20)
    return result
