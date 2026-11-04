from __future__ import annotations

import math
from typing import Mapping

import pandas as pd


LOOKBACK_RETURNS = (20, 60)
MA_WINDOWS = (60, 120, 250)


def _finite(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _clip(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _scale(value: float | None, low: float, high: float) -> float:
    if value is None or high <= low:
        return 0.0
    return _clip((value - low) / (high - low) * 100.0)


def _as_price_frame(frame: pd.DataFrame, as_of: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["trade_date", "close"])
    result = frame.copy()
    result["trade_date"] = result["trade_date"].astype(str).str.replace(r"\.0$", "", regex=True)
    result["close"] = pd.to_numeric(result["close"], errors="coerce")
    result = result.dropna(subset=["trade_date", "close"])
    result = result[result["trade_date"] <= as_of]
    return result[["trade_date", "close"]].sort_values("trade_date").reset_index(drop=True)


def _return_over_sessions(frame: pd.DataFrame, sessions: int) -> float | None:
    if len(frame) <= sessions:
        return None
    latest = _finite(frame["close"].iloc[-1])
    base = _finite(frame["close"].iloc[-sessions - 1])
    if latest is None or base is None or base <= 0:
        return None
    return latest / base - 1.0


def _moving_average(frame: pd.DataFrame, sessions: int) -> float | None:
    if len(frame) < sessions:
        return None
    value = frame["close"].tail(sessions).mean()
    return _finite(value)


def _daily_return_std(frame: pd.DataFrame, sessions: int = 60) -> float | None:
    if len(frame) <= sessions:
        return None
    returns = frame["close"].pct_change().tail(sessions).dropna()
    if returns.empty:
        return None
    return _finite(returns.std())


def _price_percentile(frame: pd.DataFrame, sessions: int = 252) -> float | None:
    if frame.empty:
        return None
    window = frame["close"].tail(min(sessions, len(frame))).dropna()
    if window.empty:
        return None
    latest = window.iloc[-1]
    return float((window <= latest).sum() / len(window))


def _trend_quality(frame: pd.DataFrame) -> dict[str, object]:
    close = _finite(frame["close"].iloc[-1]) if not frame.empty else None
    ma60 = _moving_average(frame, 60)
    ma120 = _moving_average(frame, 120)
    ma250 = _moving_average(frame, 250)
    score = 0.0
    if close is not None and ma60 is not None and close >= ma60:
        score += 30.0
    if close is not None and ma120 is not None and close >= ma120:
        score += 30.0
    if close is not None and ma250 is not None and close >= ma250:
        score += 25.0
    if ma60 is not None and ma120 is not None and ma60 >= ma120:
        score += 10.0
    if ma120 is not None and ma250 is not None and ma120 >= ma250:
        score += 5.0
    return {
        "score": round(score, 4),
        "close": close,
        "ma60": ma60,
        "ma120": ma120,
        "ma250": ma250,
        "above_ma60": close is not None and ma60 is not None and close >= ma60,
        "above_ma120": close is not None and ma120 is not None and close >= ma120,
        "above_ma250": close is not None and ma250 is not None and close >= ma250,
    }


def percentile_scores(values: Mapping[str, float | None]) -> dict[str, float]:
    clean = {code: _finite(value) for code, value in values.items()}
    valid = {code: value for code, value in clean.items() if value is not None}
    if not valid:
        return {code: 50.0 for code in values}
    if len(valid) == 1:
        only = next(iter(valid))
        return {code: 50.0 if code == only else 0.0 for code in values}
    series = pd.Series(valid, dtype=float)
    ranks = (series.rank(method="average") - 1.0) / (len(series) - 1.0) * 100.0
    return {code: round(float(ranks.get(code, 0.0)), 4) for code in values}


def persistence_scores(
    histories: Mapping[str, pd.DataFrame],
    *,
    as_of: str,
    lookback_sessions: int = 60,
    ranking_return_sessions: int = 60,
) -> dict[str, float]:
    price_columns: dict[str, pd.Series] = {}
    for code, frame in histories.items():
        price_frame = _as_price_frame(frame, as_of)
        if price_frame.empty:
            continue
        price_columns[code] = price_frame.set_index("trade_date")["close"]
    if len(price_columns) < 2:
        return {code: 50.0 for code in histories}
    prices = pd.concat(price_columns, axis=1).sort_index().ffill()
    returns = prices / prices.shift(ranking_return_sessions) - 1.0
    ranks = returns.rank(axis=1, method="average", pct=True) * 100.0
    latest = ranks.tail(lookback_sessions).mean(axis=0)
    return {code: round(float(latest.get(code, 50.0)) if not pd.isna(latest.get(code, pd.NA)) else 50.0, 4) for code in histories}


def compute_asset_metrics(
    code: str,
    history: pd.DataFrame,
    benchmark_history: pd.DataFrame,
    *,
    as_of: str,
) -> dict[str, object]:
    frame = _as_price_frame(history, as_of)
    benchmark = _as_price_frame(benchmark_history, as_of)
    ret20 = _return_over_sessions(frame, 20)
    ret60 = _return_over_sessions(frame, 60)
    benchmark_ret60 = _return_over_sessions(benchmark, 60)
    vol60 = _daily_return_std(frame, 60)
    risk_adjusted = ret60 / vol60 if ret60 is not None and vol60 not in (None, 0.0) else None
    trend = _trend_quality(frame)
    return {
        "code": code,
        "as_of": str(frame["trade_date"].iloc[-1]) if not frame.empty else None,
        "rows": int(len(frame)),
        "return_20d": ret20,
        "return_60d": ret60,
        "benchmark_return_60d": benchmark_ret60,
        "relative_60d": ret60 - benchmark_ret60 if ret60 is not None and benchmark_ret60 is not None else None,
        "volatility_60d": vol60,
        "risk_adjusted_raw": risk_adjusted,
        "price_percentile_252": _price_percentile(frame, 252),
        "deviation_ma120": (
            (trend["close"] / trend["ma120"] - 1.0)
            if trend.get("close") is not None and trend.get("ma120") not in (None, 0.0)
            else None
        ),
        "trend": trend,
    }


def extension_penalty(metrics: Mapping[str, object]) -> float:
    price_position = _finite(metrics.get("price_percentile_252"))
    return_60d = _finite(metrics.get("return_60d"))
    deviation_ma120 = _finite(metrics.get("deviation_ma120"))
    penalty = 0.18 * _scale(price_position, 0.85, 0.98)
    penalty += 0.10 * _scale(return_60d, 0.20, 0.50)
    penalty += 0.08 * _scale(deviation_ma120, 0.15, 0.40)
    return round(min(30.0, penalty), 4)
