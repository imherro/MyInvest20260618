from __future__ import annotations

from typing import Mapping

import pandas as pd


def _scale(value: float, low: float, high: float) -> float:
    if high <= low:
        raise ValueError("high must be greater than low")
    return max(0.0, min(100.0, (value - low) / (high - low) * 100.0))


def _clean(frame: pd.DataFrame, as_of: str) -> pd.DataFrame:
    df = frame.copy()
    df["trade_date"] = df["trade_date"].astype(str).str.replace(r"\.0$", "", regex=True)
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["trade_date", "close"])
    df = df[df["trade_date"] <= as_of].sort_values("trade_date").reset_index(drop=True)
    return df


def _trailing_return(close: pd.Series, window: int) -> float | None:
    if len(close) <= window:
        return None
    previous = float(close.iloc[-1 - window])
    if previous <= 0:
        return None
    return float(close.iloc[-1]) / previous - 1.0


def _price_percentile(close: pd.Series, window: int = 252) -> float | None:
    if close.empty:
        return None
    recent = close.tail(min(window, len(close)))
    if recent.empty:
        return None
    return float((recent <= float(close.iloc[-1])).mean())


def evaluate_valuation_pressure(
    top_themes: list[Mapping[str, object]],
    frames: Mapping[str, pd.DataFrame],
    as_of: str,
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for theme in top_themes:
        code = str(theme.get("code"))
        frame = frames.get(code)
        if frame is None or frame.empty:
            continue
        df = _clean(frame, as_of)
        if len(df) < 80:
            continue
        close = df["close"].astype(float)
        latest = float(close.iloc[-1])
        ret20 = _trailing_return(close, 20)
        ret60 = _trailing_return(close, 60)
        ma60 = float(close.rolling(60, min_periods=60).mean().iloc[-1])
        ma120 = float(close.rolling(120, min_periods=80).mean().iloc[-1])
        ma250_series = close.rolling(250, min_periods=120).mean()
        ma250 = None if pd.isna(ma250_series.iloc[-1]) else float(ma250_series.iloc[-1])
        deviation_ma60 = latest / ma60 - 1.0 if ma60 else 0.0
        deviation_ma120 = latest / ma120 - 1.0 if ma120 else 0.0
        deviation_ma250 = None if ma250 is None or ma250 == 0 else latest / ma250 - 1.0
        percentile = _price_percentile(close)

        extension_score = max(
            _scale(ret20 or 0.0, 0.02, 0.22),
            _scale(ret60 or 0.0, 0.08, 0.55),
            _scale(deviation_ma60, 0.02, 0.25),
        )
        relative_position_score = 0.0 if percentile is None else percentile * 100.0
        pressure_score = 0.58 * extension_score + 0.42 * relative_position_score
        warnings: list[str] = []
        if ret60 is not None and ret60 >= 0.35:
            warnings.append("high_60d_momentum_extension")
        if deviation_ma60 >= 0.18:
            warnings.append("high_ma60_deviation")
        if percentile is not None and percentile >= 0.9:
            warnings.append("near_252d_high_position")
        results.append(
            {
                "code": code,
                "name": str(theme.get("name")),
                "close": round(latest, 4),
                "return_20d": None if ret20 is None else round(ret20, 6),
                "return_60d": None if ret60 is None else round(ret60, 6),
                "deviation_ma60": round(deviation_ma60, 6),
                "deviation_ma120": round(deviation_ma120, 6),
                "deviation_ma250": None if deviation_ma250 is None else round(deviation_ma250, 6),
                "price_percentile_252": None if percentile is None else round(percentile, 4),
                "momentum_extension_score": round(extension_score, 4),
                "relative_position_score": round(relative_position_score, 4),
                "valuation_pressure_score": round(pressure_score, 4),
                "warnings": warnings,
            }
        )
    return sorted(results, key=lambda item: float(item["valuation_pressure_score"]), reverse=True)
