"""Alpha validation utilities for TASK 3."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd


FACTOR_SCORE_COLUMNS = [
    "value_score",
    "growth_score",
    "quality_score",
    "industry_score",
    "momentum_score",
    "risk_score",
    "tenbagger_score",
    "tenbagger_score_v2",
]


@dataclass(frozen=True)
class BacktestPreview:
    top_decile_return: float
    benchmark_return: float
    excess_return: float
    max_drawdown: float
    observations: int


class AlphaValidator:
    """Compute IC, RankIC, stability, and a minimal preview return series."""

    def __init__(self, horizons: Iterable[int] = (21, 63, 126)) -> None:
        self.horizons = tuple(horizons)

    def attach_forward_returns(self, factors: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
        price_frame = prices[["ts_code", "date", "close"]].copy()
        price_frame["date"] = pd.to_datetime(price_frame["date"], errors="coerce")
        price_frame["close"] = pd.to_numeric(price_frame["close"], errors="coerce")
        price_frame = price_frame.dropna(subset=["ts_code", "date", "close"]).sort_values(["ts_code", "date"])

        for horizon in self.horizons:
            price_frame[f"future_{horizon}d_return"] = (
                price_frame.groupby("ts_code")["close"].shift(-horizon) / price_frame["close"] - 1
            )

        enriched = factors.copy()
        enriched["date"] = pd.to_datetime(enriched["date"], errors="coerce")
        return enriched.merge(
            price_frame.drop(columns=["close"]),
            on=["ts_code", "date"],
            how="left",
        )

    def ic_summary(self, enriched: pd.DataFrame) -> dict[str, dict[str, float | int]]:
        result: dict[str, dict[str, float | int]] = {}
        for factor in [column for column in FACTOR_SCORE_COLUMNS if column in enriched.columns]:
            for horizon in self.horizons:
                target = f"future_{horizon}d_return"
                values = self._daily_correlations(enriched, factor, target)
                key = f"{factor}_{horizon}d"
                result[key] = {
                    "ic_mean": float(values["ic"].mean()) if not values.empty else 0.0,
                    "ic_std": float(values["ic"].std(ddof=0)) if not values.empty else 0.0,
                    "rank_ic_mean": float(values["rank_ic"].mean()) if not values.empty else 0.0,
                    "rank_ic_std": float(values["rank_ic"].std(ddof=0)) if not values.empty else 0.0,
                    "observations": int(len(values)),
                }
        return result

    def ic_decay_curve(self, enriched: pd.DataFrame, factor: str = "tenbagger_score") -> list[dict[str, float | int]]:
        curve = []
        for horizon in self.horizons:
            values = self._daily_correlations(enriched, factor, f"future_{horizon}d_return")
            curve.append(
                {
                    "horizon_days": horizon,
                    "ic_mean": float(values["ic"].mean()) if not values.empty else 0.0,
                    "rank_ic_mean": float(values["rank_ic"].mean()) if not values.empty else 0.0,
                    "observations": int(len(values)),
                }
            )
        return curve

    def backtest_preview(self, enriched: pd.DataFrame, horizon: int = 21, factor: str = "tenbagger_score") -> BacktestPreview:
        target = f"future_{horizon}d_return"
        usable = enriched.dropna(subset=["date", factor, target]).copy()
        if usable.empty:
            return BacktestPreview(0.0, 0.0, 0.0, 0.0, 0)

        rows = []
        rebalance_dates = sorted(usable["date"].dropna().unique())[::horizon]
        for date_value, date_df in usable[usable["date"].isin(rebalance_dates)].groupby("date"):
            if len(date_df) < 3:
                continue
            top_count = max(1, int(len(date_df) * 0.1))
            ranked = date_df.sort_values(factor, ascending=False)
            rows.append(
                {
                    "date": date_value,
                    "top_return": float(ranked.head(top_count)[target].mean()),
                    "benchmark_return": float(date_df[target].mean()),
                }
            )

        preview = pd.DataFrame(rows).sort_values("date")
        if preview.empty:
            return BacktestPreview(0.0, 0.0, 0.0, 0.0, 0)

        equity = (1 + preview["top_return"]).cumprod()
        drawdown = equity / equity.cummax() - 1
        top_return = float(preview["top_return"].mean())
        benchmark_return = float(preview["benchmark_return"].mean())
        return BacktestPreview(
            top_decile_return=top_return,
            benchmark_return=benchmark_return,
            excess_return=top_return - benchmark_return,
            max_drawdown=float(drawdown.min()),
            observations=int(len(preview)),
        )

    @staticmethod
    def _daily_correlations(enriched: pd.DataFrame, factor: str, target: str) -> pd.DataFrame:
        rows = []
        for date_value, date_df in enriched.dropna(subset=[factor, target]).groupby("date"):
            if len(date_df) < 3:
                continue
            if date_df[factor].nunique() < 2 or date_df[target].nunique() < 2:
                continue
            rows.append(
                {
                    "date": date_value,
                    "ic": float(date_df[factor].corr(date_df[target], method="pearson")),
                    "rank_ic": float(date_df[factor].rank().corr(date_df[target].rank(), method="pearson")),
                }
            )
        return pd.DataFrame(rows)
