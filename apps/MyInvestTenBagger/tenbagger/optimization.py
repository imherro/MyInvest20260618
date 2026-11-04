"""Factor optimization and neutralization for TASK 5."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from tenbagger.alpha_validation import AlphaValidator
from tenbagger.config import DEFAULT_DATA_DIR
from tenbagger.portfolio import BacktestConfig, PortfolioBuilder, RiskMetrics, load_local_task_data


COMPONENTS = [
    "growth_score",
    "quality_score",
    "value_score",
    "industry_score",
    "momentum_score",
    "risk_score",
]


@dataclass(frozen=True)
class OptimizationResult:
    best_weights: dict[str, float]
    train_metrics: dict[str, Any]
    test_metrics: dict[str, Any]
    baseline_test_metrics: dict[str, Any]
    optimized_full_metrics: dict[str, Any]
    baseline_full_metrics: dict[str, Any]
    ic_comparison: dict[str, Any]
    regime_analysis: dict[str, Any]
    candidates_evaluated: int


class FactorNeutralizer:
    """Neutralize component scores by industry, size bucket, and beta bucket."""

    def neutralize(self, factors: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
        result = factors.copy()
        result["date"] = pd.to_datetime(result["date"], errors="coerce")
        result = self._attach_beta_proxy(result, prices)

        for column in COMPONENTS:
            result[f"{column}_neutral"] = pd.to_numeric(result[column], errors="coerce")
            result[f"{column}_neutral"] = self._neutralize_group(
                result,
                f"{column}_neutral",
                ["date", "industry"],
            )
            result["size_bucket"] = result.groupby("date")["market_cap"].transform(self._bucket)
            result[f"{column}_neutral"] = self._neutralize_group(
                result,
                f"{column}_neutral",
                ["date", "size_bucket"],
            )
            result["beta_bucket"] = result.groupby("date")["beta_proxy"].transform(self._bucket)
            result[f"{column}_neutral"] = self._neutralize_group(
                result,
                f"{column}_neutral",
                ["date", "beta_bucket"],
            )
            result[f"{column}_neutral"] = result[f"{column}_neutral"].fillna(50.0).clip(0, 100)
        return result

    @staticmethod
    def _neutralize_group(df: pd.DataFrame, column: str, group_columns: list[str]) -> pd.Series:
        date_mean = df.groupby("date")[column].transform("mean")
        group_mean = df.groupby(group_columns)[column].transform("mean")
        return (df[column] - group_mean + date_mean).clip(0, 100)

    @staticmethod
    def _bucket(values: pd.Series) -> pd.Series:
        values = pd.to_numeric(values, errors="coerce")
        if values.nunique(dropna=True) < 3:
            return pd.Series("all", index=values.index)
        ranks = values.rank(method="first")
        try:
            return pd.qcut(ranks, q=3, labels=["low", "mid", "high"]).astype(str)
        except ValueError:
            return pd.Series("all", index=values.index)

    @staticmethod
    def _attach_beta_proxy(factors: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
        returns = prices[["ts_code", "date", "close"]].copy()
        returns["date"] = pd.to_datetime(returns["date"], errors="coerce")
        returns["close"] = pd.to_numeric(returns["close"], errors="coerce")
        returns = returns.sort_values(["ts_code", "date"])
        returns["stock_return"] = returns.groupby("ts_code")["close"].pct_change()
        market = returns.groupby("date", as_index=False)["stock_return"].mean().rename(
            columns={"stock_return": "market_return"}
        )
        market["market_var"] = market["market_return"].rolling(60, min_periods=20).var()
        returns = returns.merge(market, on="date", how="left")
        rolling_cov = (
            returns.groupby("ts_code")
            .apply(lambda group: group["stock_return"].rolling(60, min_periods=20).cov(group["market_return"]))
            .reset_index(level=0, drop=True)
        )
        returns["beta_proxy"] = (rolling_cov / returns["market_var"]).replace([float("inf"), -float("inf")], pd.NA)
        return factors.merge(
            returns[["ts_code", "date", "beta_proxy"]],
            on=["ts_code", "date"],
            how="left",
        )


class RegimeDetector:
    """Detect simple market and style regimes from local data."""

    def detect(self, prices: pd.DataFrame, factors: pd.DataFrame) -> pd.DataFrame:
        price_frame = prices[["ts_code", "date", "close"]].copy()
        price_frame["date"] = pd.to_datetime(price_frame["date"], errors="coerce")
        price_frame = price_frame.sort_values(["ts_code", "date"])
        price_frame["ret"] = price_frame.groupby("ts_code")["close"].pct_change()
        market = price_frame.groupby("date", as_index=False)["ret"].mean().sort_values("date")
        market["nav"] = (1 + market["ret"].fillna(0.0)).cumprod()
        market["ret_126d"] = market["nav"].pct_change(126)
        market["market_regime"] = "sideways"
        market.loc[market["ret_126d"] > 0.10, "market_regime"] = "bull"
        market.loc[market["ret_126d"] < -0.10, "market_regime"] = "bear"

        style = factors.copy()
        style["date"] = pd.to_datetime(style["date"], errors="coerce")
        style = style.groupby("date", as_index=False).agg(
            growth=("growth_score", "mean"),
            value=("value_score", "mean"),
        )
        style["style_regime"] = "balanced"
        style.loc[style["growth"] > style["value"] + 5, "style_regime"] = "growth-driven"
        style.loc[style["value"] > style["growth"] + 5, "style_regime"] = "value-driven"
        return market[["date", "market_regime"]].merge(style[["date", "style_regime"]], on="date", how="left")


class DynamicWeightSystem:
    """Create simple regime-aware weights from optimized static weights."""

    def weights_for_regime(self, base_weights: dict[str, float], market_regime: str, style_regime: str) -> dict[str, float]:
        weights = base_weights.copy()
        if market_regime == "bear":
            weights["quality_score"] = weights.get("quality_score", 0) + 0.05
            weights["risk_score"] = weights.get("risk_score", 0) + 0.05
            weights["growth_score"] = max(0.0, weights.get("growth_score", 0) - 0.05)
            weights["momentum_score"] = max(0.0, weights.get("momentum_score", 0) - 0.05)
        elif market_regime == "bull":
            weights["growth_score"] = weights.get("growth_score", 0) + 0.05
            weights["momentum_score"] = weights.get("momentum_score", 0) + 0.05
            weights["risk_score"] = max(0.0, weights.get("risk_score", 0) - 0.05)

        if style_regime == "value-driven":
            weights["value_score"] = weights.get("value_score", 0) + 0.05
            weights["growth_score"] = max(0.0, weights.get("growth_score", 0) - 0.05)

        total = sum(weights.values()) or 1.0
        return {key: value / total for key, value in weights.items()}


class FactorWeightOptimizer:
    """Coarse grid-search optimizer with train/test split."""

    def __init__(self, step: float = 0.25, top_k: int = 10) -> None:
        self.step = step
        self.top_k = top_k

    def optimize(
        self,
        factors: pd.DataFrame,
        prices: pd.DataFrame,
    ) -> OptimizationResult:
        neutralized = FactorNeutralizer().neutralize(factors, prices)
        dates = sorted(neutralized["date"].dropna().unique())
        split_idx = int(len(dates) * 0.7)
        split_date = dates[split_idx]

        train_factors = neutralized[neutralized["date"] <= split_date].copy()
        test_factors = neutralized[neutralized["date"] > split_date].copy()

        candidates = self._weight_grid()
        evaluated = []
        for weights in candidates:
            scored = self._apply_weights(train_factors, weights, neutralized_scores=True)
            try:
                metrics = self._backtest_metrics(scored, prices)
            except ValueError:
                continue
            objective = metrics["sharpe"] + metrics["annual_return"] + metrics["max_drawdown"]
            evaluated.append((objective, weights, metrics))

        if not evaluated:
            raise RuntimeError("No optimization candidate produced a valid backtest.")

        _, best_weights, train_metrics = max(evaluated, key=lambda item: item[0])
        optimized_test = self._apply_weights(test_factors, best_weights, neutralized_scores=True)
        baseline_test = test_factors.copy()
        optimized_full = self._apply_weights(neutralized, best_weights, neutralized_scores=True)
        baseline_full = neutralized.copy()

        test_metrics = self._backtest_metrics(optimized_test, prices)
        baseline_test_metrics = self._backtest_metrics(baseline_test, prices)
        optimized_full_metrics = self._backtest_metrics(optimized_full, prices)
        baseline_full_metrics = self._backtest_metrics(baseline_full, prices)

        ic_comparison = self._ic_comparison(baseline_full, optimized_full, prices)
        regimes = RegimeDetector().detect(prices, optimized_full)
        regime_analysis = self._regime_analysis(optimized_full, prices, regimes)

        return OptimizationResult(
            best_weights=best_weights,
            train_metrics=train_metrics,
            test_metrics=test_metrics,
            baseline_test_metrics=baseline_test_metrics,
            optimized_full_metrics=optimized_full_metrics,
            baseline_full_metrics=baseline_full_metrics,
            ic_comparison=ic_comparison,
            regime_analysis=regime_analysis,
            candidates_evaluated=len(evaluated),
        )

    def _weight_grid(self) -> list[dict[str, float]]:
        units = int(round(1 / self.step))
        candidates = []
        for combo in product(range(units + 1), repeat=len(COMPONENTS)):
            if sum(combo) != units:
                continue
            weights = {component: value * self.step for component, value in zip(COMPONENTS, combo)}
            if max(weights.values()) > 0.5:
                continue
            candidates.append(weights)
        return candidates

    @staticmethod
    def _apply_weights(factors: pd.DataFrame, weights: dict[str, float], neutralized_scores: bool) -> pd.DataFrame:
        result = factors.copy()
        score = pd.Series(0.0, index=result.index)
        for component, weight in weights.items():
            column = f"{component}_neutral" if neutralized_scores and f"{component}_neutral" in result.columns else component
            score = score + pd.to_numeric(result[column], errors="coerce").fillna(50.0) * weight
        result["optimized_score"] = score.clip(0, 100)
        result["tenbagger_score"] = result["optimized_score"]
        return result

    def _backtest_metrics(self, factors: pd.DataFrame, prices: pd.DataFrame) -> dict[str, Any]:
        backtest = PortfolioBuilder(BacktestConfig(top_k=self.top_k, weight_mode="score")).run_backtest(factors, prices)
        return RiskMetrics().summarize(backtest["nav"], {})

    @staticmethod
    def _ic_comparison(baseline: pd.DataFrame, optimized: pd.DataFrame, prices: pd.DataFrame) -> dict[str, Any]:
        validator = AlphaValidator(horizons=(21, 63, 126))
        baseline_ic = validator.ic_summary(validator.attach_forward_returns(baseline, prices))
        optimized_ic = validator.ic_summary(validator.attach_forward_returns(optimized, prices))
        keys = ["tenbagger_score_21d", "tenbagger_score_63d", "tenbagger_score_126d"]
        return {
            key: {
                "baseline_rank_ic": baseline_ic.get(key, {}).get("rank_ic_mean", 0.0),
                "optimized_rank_ic": optimized_ic.get(key, {}).get("rank_ic_mean", 0.0),
                "delta": optimized_ic.get(key, {}).get("rank_ic_mean", 0.0)
                - baseline_ic.get(key, {}).get("rank_ic_mean", 0.0),
            }
            for key in keys
        }

    def _regime_analysis(self, factors: pd.DataFrame, prices: pd.DataFrame, regimes: pd.DataFrame) -> dict[str, Any]:
        backtest = PortfolioBuilder(BacktestConfig(top_k=self.top_k, weight_mode="score")).run_backtest(factors, prices)
        nav = backtest["nav"].merge(regimes, on="date", how="left")
        summary = {}
        for column in ["market_regime", "style_regime"]:
            summary[column] = (
                nav.groupby(column)["portfolio_return"]
                .agg(["mean", "std", "count"])
                .fillna(0.0)
                .reset_index()
                .to_dict(orient="records")
            )
        latest = regimes.dropna(subset=["market_regime", "style_regime"]).tail(1)
        dynamic_weights = {}
        if not latest.empty:
            row = latest.iloc[0]
            dynamic_weights = DynamicWeightSystem().weights_for_regime(
                {component: 1 / len(COMPONENTS) for component in COMPONENTS},
                str(row["market_regime"]),
                str(row["style_regime"]),
            )
        summary["latest_dynamic_weights"] = dynamic_weights
        return summary


def load_optimization_inputs(
    data_dir: Path | str = DEFAULT_DATA_DIR,
    universe: Iterable[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    return load_local_task_data(data_dir, universe=universe)
