from __future__ import annotations

import math
from typing import Mapping

import pandas as pd


INDEX_LABELS = {
    "000001.SH": "SSE Composite",
    "000300.SH": "CSI 300",
    "000905.SH": "CSI 500",
}


def clip(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def scale(value: float, low: float, high: float) -> float:
    if high <= low:
        raise ValueError("high must be greater than low")
    return clip((value - low) / (high - low) * 100.0)


def _close(df: pd.DataFrame) -> pd.Series:
    return pd.to_numeric(df["close"], errors="coerce")


def score_index_trend(index_df: pd.DataFrame) -> dict[str, object]:
    if index_df.empty:
        raise ValueError("index_df is empty")
    df = index_df.sort_values("trade_date").copy()
    close = _close(df)
    df["ma60"] = close.rolling(60, min_periods=60).mean()
    df["ma120"] = close.rolling(120, min_periods=120).mean()
    df["ma250"] = close.rolling(250, min_periods=250).mean()
    df["ma250_slope"] = df["ma250"].pct_change(20)
    df["return_60"] = close.pct_change(60)
    df["drawdown_60"] = close / close.rolling(60, min_periods=20).max() - 1.0
    df["volatility_20"] = close.pct_change().rolling(20, min_periods=10).std() * math.sqrt(252)
    valid = df.dropna(subset=["ma60", "ma120", "ma250", "ma250_slope", "return_60", "drawdown_60", "volatility_20"])
    if valid.empty:
        raise ValueError("At least 250 trading rows are required for structure scoring.")

    latest = valid.iloc[-1]
    close_value = float(latest["close"])
    ma60 = float(latest["ma60"])
    ma120 = float(latest["ma120"])
    ma250 = float(latest["ma250"])
    above_ma250 = 100.0 if close_value > ma250 else 0.0
    ma_stack = 100.0 if ma60 > ma120 > ma250 else (65.0 if ma60 > ma120 else 25.0)
    slope_score = scale(float(latest["ma250_slope"]), -0.06, 0.08)
    momentum_score = scale(float(latest["return_60"]), -0.18, 0.30)
    drawdown = float(latest["drawdown_60"])
    drawdown_health = scale(drawdown, -0.18, 0.0)
    volatility_stability = clip(100.0 - scale(float(latest["volatility_20"]), 0.12, 0.55))
    trend_score = clip(
        0.28 * above_ma250
        + 0.24 * ma_stack
        + 0.20 * slope_score
        + 0.18 * momentum_score
        + 0.10 * volatility_stability
    )

    return {
        "trade_date": str(latest["trade_date"]),
        "close": round(close_value, 4),
        "ma60": round(ma60, 4),
        "ma120": round(ma120, 4),
        "ma250": round(ma250, 4),
        "above_ma250": close_value > ma250,
        "ma_stack_score": round(ma_stack, 4),
        "ma250_slope": round(float(latest["ma250_slope"]), 6),
        "return_60": round(float(latest["return_60"]), 6),
        "drawdown_60": round(drawdown, 6),
        "volatility_20": round(float(latest["volatility_20"]), 6),
        "drawdown_health": round(drawdown_health, 4),
        "volatility_stability": round(volatility_stability, 4),
        "trend_score": round(trend_score, 4),
    }


def aggregate_index_trends(index_metrics: Mapping[str, Mapping[str, object]]) -> dict[str, object]:
    scores = [float(metrics["trend_score"]) for metrics in index_metrics.values()]
    if not scores:
        raise ValueError("index_metrics is empty")
    broad_score = sum(scores) / len(scores)
    dispersion = max(scores) - min(scores)
    above_ma250_ratio = sum(1 for item in index_metrics.values() if bool(item.get("above_ma250"))) / len(scores)
    pullback_health = sum(float(item.get("drawdown_health", 0.0)) for item in index_metrics.values()) / len(scores)
    return {
        "index_trend": round(broad_score, 4),
        "index_dispersion": round(dispersion, 4),
        "above_ma250_ratio": round(above_ma250_ratio, 4),
        "pullback_health": round(pullback_health, 4),
    }


def normalize_breadth_metrics(breadth_metrics: Mapping[str, object] | None) -> dict[str, object]:
    if not breadth_metrics:
        return {
            "breadth": None,
            "up_down_ratio": None,
            "high_52w_ratio": None,
            "limit_up_ratio": None,
        }
    strength = float(breadth_metrics.get("strength_score", 0.0)) * 100.0
    return {
        "breadth": round(strength, 4),
        "up_down_ratio": breadth_metrics.get("up_down_ratio"),
        "high_52w_ratio": breadth_metrics.get("high_52w_ratio"),
        "limit_up_ratio": breadth_metrics.get("limit_up_ratio"),
    }


def normalize_liquidity_metrics(liquidity_metrics: Mapping[str, object] | None) -> dict[str, object]:
    if not liquidity_metrics:
        return {
            "liquidity": None,
            "turnover_ma_ratio": None,
            "northbound_5d_avg": None,
        }
    return {
        "liquidity": round(float(liquidity_metrics.get("liquidity_score", 0.0)) * 100.0, 4),
        "turnover_ma_ratio": liquidity_metrics.get("turnover_ma_ratio"),
        "northbound_5d_avg": liquidity_metrics.get("northbound_5d_avg"),
    }


def build_structure_metrics(
    index_metrics: Mapping[str, Mapping[str, object]],
    *,
    breadth_metrics: Mapping[str, object] | None,
    liquidity_metrics: Mapping[str, object] | None,
    industry_metrics: Mapping[str, object] | None = None,
) -> dict[str, object]:
    index_summary = aggregate_index_trends(index_metrics)
    breadth = normalize_breadth_metrics(breadth_metrics)
    liquidity = normalize_liquidity_metrics(liquidity_metrics)
    industry_strength = None if not industry_metrics else industry_metrics.get("industry_strength")
    theme_persistence = None if not industry_metrics else industry_metrics.get("theme_persistence")

    weighted_sum = 0.45 * float(index_summary["index_trend"])
    available_weight = 0.45
    if breadth["breadth"] is not None:
        weighted_sum += 0.25 * float(breadth["breadth"])
        available_weight += 0.25
    if liquidity["liquidity"] is not None:
        weighted_sum += 0.20 * float(liquidity["liquidity"])
        available_weight += 0.20
    if industry_strength is not None:
        weighted_sum += 0.10 * float(industry_strength)
        available_weight += 0.10

    structure_score = weighted_sum / available_weight if available_weight else 0.0
    return {
        **index_summary,
        **breadth,
        **liquidity,
        "industry_strength": industry_strength,
        "theme_persistence": theme_persistence,
        "structure_score": round(structure_score, 4),
        "available_weight": round(available_weight, 4),
        "missing_inputs": [
            name
            for name, value in {
                "breadth": breadth["breadth"],
                "liquidity": liquidity["liquidity"],
                "industry_strength": industry_strength,
                "theme_persistence": theme_persistence,
            }.items()
            if value is None
        ],
    }
