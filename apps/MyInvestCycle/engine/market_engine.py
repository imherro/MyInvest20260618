from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from core.breadth import calculate_breadth_metrics
from core.features import build_feature_frame
from core.liquidity import calculate_liquidity_metrics


def _clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _scale(value: float, low: float, high: float) -> float:
    if high <= low:
        raise ValueError("high must be greater than low")
    return _clip((value - low) / (high - low))


@dataclass(frozen=True)
class MarketRegimeResult:
    regime: str
    confidence: float
    trend_score: float
    breadth_score: float
    liquidity_score: float
    volatility_score: float
    regime_score: float
    as_of: str | None

    def to_dict(self) -> dict[str, float | str | None | dict[str, float]]:
        return {
            "regime": self.regime,
            "confidence": self.confidence,
            "trend_score": self.trend_score,
            "breadth_score": self.breadth_score,
            "liquidity_score": self.liquidity_score,
            "volatility_score": self.volatility_score,
            "regime_score": self.regime_score,
            "sub_scores": {
                "trend": self.trend_score,
                "breadth": self.breadth_score,
                "liquidity": self.liquidity_score,
                "volatility": self.volatility_score,
            },
            "as_of": self.as_of,
        }


class MarketEngine:
    """Rule-based regime classifier using trend, breadth, liquidity, and volatility."""

    def analyze(
        self,
        index_df: pd.DataFrame,
        *,
        market_daily_df: pd.DataFrame,
        market_history_df: pd.DataFrame | None = None,
        hsgt_df: pd.DataFrame | None = None,
    ) -> MarketRegimeResult:
        if index_df.empty:
            raise ValueError("index_df is empty")
        if market_daily_df.empty:
            raise ValueError("market_daily_df is required for breadth scoring")

        features = build_feature_frame(index_df)
        required = ["close", "ma20", "ma60", "ma120", "ma20_slope", "return_60", "volatility_20"]
        valid = features.dropna(subset=required)
        if valid.empty:
            raise ValueError("Not enough index history. At least 120 trading rows are required.")

        latest = valid.iloc[-1]

        above_ma120 = 1.0 if latest["close"] > latest["ma120"] else 0.0
        ma_stack = 1.0 if latest["ma20"] > latest["ma60"] else 0.0
        slope_score = _scale(float(latest["ma20_slope"]), -0.02, 0.03)
        momentum_score = _scale(float(latest["return_60"]), -0.10, 0.25)

        trend_score = _clip(
            0.30 * above_ma120
            + 0.25 * ma_stack
            + 0.20 * slope_score
            + 0.25 * momentum_score
        )
        volatility_risk = _clip(float(latest["volatility_20"]) / 0.45)
        volatility_score = _clip(1.0 - volatility_risk)
        breadth_metrics = calculate_breadth_metrics(market_daily_df, market_history_df=market_history_df)
        liquidity_metrics = calculate_liquidity_metrics(index_df, hsgt_df=hsgt_df)
        breadth_score = _clip(float(breadth_metrics["strength_score"]))
        liquidity_score = _clip(float(liquidity_metrics["liquidity_score"]))
        regime_score = _clip(
            0.35 * trend_score
            + 0.30 * breadth_score
            + 0.20 * liquidity_score
            + 0.15 * volatility_score
        )

        regime = classify_regime(trend_score, breadth_score, liquidity_score, volatility_score, regime_score)
        confidence = estimate_confidence(regime, trend_score, breadth_score, liquidity_score, volatility_score, regime_score)
        as_of = str(latest["trade_date"]) if "trade_date" in latest else None

        return MarketRegimeResult(
            regime=regime,
            confidence=round(confidence, 2),
            trend_score=round(trend_score, 2),
            volatility_score=round(volatility_score, 2),
            breadth_score=round(breadth_score, 2),
            liquidity_score=round(liquidity_score, 2),
            regime_score=round(regime_score, 2),
            as_of=as_of,
        )


def classify_regime(
    trend_score: float,
    breadth_score: float,
    liquidity_score: float,
    volatility_score: float,
    regime_score: float,
) -> str:
    trend_breadth_gap = abs(trend_score - breadth_score)
    if regime_score >= 0.66 and trend_score >= 0.60 and breadth_score >= 0.55 and liquidity_score >= 0.45:
        return "bull"
    if regime_score <= 0.38 and (trend_score <= 0.40 or breadth_score <= 0.35) and liquidity_score <= 0.55:
        return "bear"
    if (
        trend_breadth_gap >= 0.20
        or (trend_score >= 0.55 and breadth_score < 0.45)
        or (trend_score < 0.45 and breadth_score >= 0.55)
    ):
        return "transition"
    return "range"


def estimate_confidence(
    regime: str,
    trend_score: float,
    breadth_score: float,
    liquidity_score: float,
    volatility_score: float,
    regime_score: float,
) -> float:
    if regime == "bull":
        agreement = min(trend_score, breadth_score, liquidity_score)
        return _clip(0.50 + (regime_score - 0.66) + 0.25 * agreement)
    if regime == "bear":
        weakness = 1.0 - max(trend_score, breadth_score, liquidity_score)
        return _clip(0.50 + (0.38 - regime_score) + 0.30 * weakness)
    if regime == "transition":
        divergence = abs(trend_score - breadth_score)
        return _clip(0.50 + 0.80 * divergence)
    balance = 1.0 - abs(regime_score - 0.50)
    stability = (breadth_score + liquidity_score + volatility_score) / 3.0
    return _clip(0.35 + 0.35 * balance + 0.15 * stability)


def analyze_index_regime(
    index_df: pd.DataFrame,
    *,
    market_daily_df: pd.DataFrame,
    market_history_df: pd.DataFrame | None = None,
    hsgt_df: pd.DataFrame | None = None,
) -> dict[str, float | str | None | dict[str, float]]:
    return MarketEngine().analyze(
        index_df,
        market_daily_df=market_daily_df,
        market_history_df=market_history_df,
        hsgt_df=hsgt_df,
    ).to_dict()
