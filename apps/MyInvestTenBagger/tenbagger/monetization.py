"""Alpha monetization diagnostics for TASK 6."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from math import log
from typing import Any

import pandas as pd

from tenbagger.alpha_validation import AlphaValidator
from tenbagger.optimization import FactorNeutralizer, FactorWeightOptimizer
from tenbagger.portfolio import BacktestConfig, PortfolioBuilder, RiskMetrics


@dataclass(frozen=True)
class MonetizationResult:
    best_config: dict[str, Any]
    train_metrics: dict[str, Any]
    test_metrics: dict[str, Any]
    turnover_sharpe_curve: list[dict[str, Any]]
    cost_sensitivity: list[dict[str, Any]]
    alpha_decay: dict[str, Any]
    payoff_report: dict[str, Any]
    ic_pnl_divergence: dict[str, Any]


class AlphaDecayModel:
    def fit(self, factors: pd.DataFrame, prices: pd.DataFrame) -> dict[str, Any]:
        validator = AlphaValidator(horizons=(21, 63, 126))
        enriched = validator.attach_forward_returns(factors, prices)
        curve = validator.ic_decay_curve(enriched, factor="tenbagger_score")
        positive = [item for item in curve if item["rank_ic_mean"] > 0]
        if len(positive) >= 2:
            first = positive[0]
            last = positive[-1]
            decay = -(log(last["rank_ic_mean"]) - log(first["rank_ic_mean"])) / (
                last["horizon_days"] - first["horizon_days"]
            )
        else:
            decay = 0.0
        return {
            "curve": curve,
            "decay_rate": float(decay),
        }


class NonlinearPayoffDetector:
    def analyze(self, factors: pd.DataFrame, prices: pd.DataFrame) -> dict[str, Any]:
        enriched = AlphaValidator(horizons=(21,)).attach_forward_returns(factors, prices)
        target = "future_21d_return"
        usable = enriched.dropna(subset=[target]).copy()
        if usable.empty:
            return {}

        usable["momentum_bucket"] = pd.qcut(
            usable["momentum_score"].rank(method="first"),
            q=5,
            labels=False,
            duplicates="drop",
        )
        momentum = usable.groupby("momentum_bucket")[target].mean().to_dict()

        breakout = usable[
            (usable["growth_score"] >= usable["growth_score"].quantile(0.8))
            & (usable["momentum_score"] >= usable["momentum_score"].quantile(0.8))
        ]
        tail_threshold = usable[target].quantile(0.95)
        tail = usable[usable[target] >= tail_threshold]
        return {
            "momentum_convexity": {str(key): float(value) for key, value in momentum.items()},
            "growth_momentum_breakout_return": float(breakout[target].mean()) if not breakout.empty else 0.0,
            "tail_event_threshold": float(tail_threshold),
            "tail_event_mean_return": float(tail[target].mean()) if not tail.empty else 0.0,
            "tail_event_count": int(len(tail)),
        }


class MonetizationOptimizer:
    """Search execution settings on train data and evaluate on test data."""

    def __init__(self, top_k: int = 10) -> None:
        self.top_k = top_k

    def run(self, factors: pd.DataFrame, prices: pd.DataFrame, weights: dict[str, float]) -> MonetizationResult:
        neutralized = FactorNeutralizer().neutralize(factors, prices)
        scored = FactorWeightOptimizer._apply_weights(neutralized, weights, neutralized_scores=True)
        dates = sorted(scored["date"].dropna().unique())
        split_date = dates[int(len(dates) * 0.7)]
        train = scored[scored["date"] <= split_date].copy()
        test = scored[scored["date"] > split_date].copy()

        configs = self._configs()
        evaluated = []
        for config in configs:
            try:
                metrics = self._metrics(train, prices, config)
            except ValueError:
                continue
            objective = metrics["sharpe"] + metrics["annual_return"] + metrics["max_drawdown"] - metrics["turnover_rate"]
            evaluated.append((objective, config, metrics))
        if not evaluated:
            raise RuntimeError("No monetization config produced a valid train backtest.")

        _, best_config, train_metrics = max(evaluated, key=lambda item: item[0])
        test_metrics = self._metrics(test, prices, best_config)
        turnover_curve = [
            {
                **config,
                "sharpe": metrics["sharpe"],
                "annual_return": metrics["annual_return"],
                "turnover_rate": metrics["turnover_rate"],
            }
            for _, config, metrics in evaluated
        ]
        cost_sensitivity = self._cost_sensitivity(scored, prices, best_config)
        alpha_decay = AlphaDecayModel().fit(scored, prices)
        payoff = NonlinearPayoffDetector().analyze(scored, prices)
        divergence = {
            "rank_ic_21d": alpha_decay["curve"][0]["rank_ic_mean"] if alpha_decay["curve"] else 0.0,
            "test_sharpe": test_metrics["sharpe"],
            "test_annual_return": test_metrics["annual_return"],
            "interpretation": "ranking_signal_not_monetized"
            if test_metrics["sharpe"] <= 0
            else "ranking_signal_monetized",
        }
        return MonetizationResult(
            best_config=best_config,
            train_metrics=train_metrics,
            test_metrics=test_metrics,
            turnover_sharpe_curve=turnover_curve,
            cost_sensitivity=cost_sensitivity,
            alpha_decay=alpha_decay,
            payoff_report=payoff,
            ic_pnl_divergence=divergence,
        )

    def _configs(self) -> list[dict[str, Any]]:
        frequencies = ["weekly", "biweekly", "monthly"]
        weight_modes = ["equal", "score", "volatility_adjusted", "score_convex", "top_heavy"]
        cost_rates = [0.0005, 0.002, 0.005]
        return [
            {
                "rebalance": frequency,
                "weight_mode": weight_mode,
                "transaction_cost_rate": cost_rate,
                "slippage_rate": 0.0005,
            }
            for frequency, weight_mode, cost_rate in product(frequencies, weight_modes, cost_rates)
        ]

    def _metrics(self, factors: pd.DataFrame, prices: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any]:
        backtest = PortfolioBuilder(
            BacktestConfig(
                top_k=self.top_k,
                rebalance=config["rebalance"],
                weight_mode=config["weight_mode"],
                transaction_cost_rate=config["transaction_cost_rate"],
                slippage_rate=config["slippage_rate"],
            )
        ).run_backtest(factors, prices)
        return RiskMetrics().summarize(backtest["nav"], {})

    def _cost_sensitivity(self, factors: pd.DataFrame, prices: pd.DataFrame, base_config: dict[str, Any]) -> list[dict[str, Any]]:
        rows = []
        for cost_rate in [0.0005, 0.001, 0.002, 0.005, 0.01]:
            config = {**base_config, "transaction_cost_rate": cost_rate}
            metrics = self._metrics(factors, prices, config)
            rows.append(
                {
                    "transaction_cost_rate": cost_rate,
                    "sharpe": metrics["sharpe"],
                    "annual_return": metrics["annual_return"],
                    "turnover_rate": metrics["turnover_rate"],
                }
            )
        return rows
