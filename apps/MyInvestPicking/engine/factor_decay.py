from __future__ import annotations

import pandas as pd


def add_factor_health(factors: pd.DataFrame) -> pd.DataFrame:
    if factors.empty:
        return factors.copy()

    enriched = factors.copy()
    momentum_5d = _numeric_column(enriched, "momentum_5d")
    momentum_20d = _numeric_column(enriched, "momentum_20d")
    revenue_growth = _numeric_column(enriched, "revenue_growth_yoy")
    profit_growth = _numeric_column(enriched, "net_profit_growth_yoy")
    cashflow = _numeric_column(enriched, "ocf_to_profit")
    pe = _numeric_column(enriched, "pe")
    pb = _numeric_column(enriched, "pb")

    enriched["momentum_health"] = _momentum_health(momentum_5d, momentum_20d)
    enriched["value_health"] = ((pe > 0) & (pb > 0)).astype(float).replace(0, 0.5)
    enriched["quality_health"] = (
        revenue_growth.notna().astype(float) * 0.35
        + profit_growth.notna().astype(float) * 0.35
        + cashflow.notna().astype(float) * 0.30
    ).replace(0, 0.5)
    enriched["factor_health_score"] = (
        0.40 * enriched["momentum_health"]
        + 0.30 * enriched["value_health"]
        + 0.30 * enriched["quality_health"]
    ).clip(0.4, 1.05)
    return enriched


def summarize_factor_health(factors: pd.DataFrame) -> dict[str, float]:
    if factors.empty or "factor_health_score" not in factors.columns:
        return {
            "factor_health_score": 0.0,
            "momentum_health": 0.0,
            "value_health": 0.0,
            "quality_health": 0.0,
        }

    return {
        "factor_health_score": round(float(factors["factor_health_score"].mean()), 4),
        "momentum_health": round(float(factors["momentum_health"].mean()), 4),
        "value_health": round(float(factors["value_health"].mean()), 4),
        "quality_health": round(float(factors["quality_health"].mean()), 4),
    }


def _momentum_health(momentum_5d: pd.Series, momentum_20d: pd.Series) -> pd.Series:
    denominator = (momentum_20d.abs() / 4).replace(0, pd.NA)
    ratio = (momentum_5d / denominator).clip(lower=-1, upper=1)
    health = (0.65 + 0.35 * ratio).fillna(0.65)
    return health.clip(0.3, 1.0)


def _numeric_column(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(float("nan"), index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")
