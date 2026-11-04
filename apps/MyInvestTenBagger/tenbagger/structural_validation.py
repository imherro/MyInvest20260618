"""Structural alpha validation for TASK 7."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

import pandas as pd

from tenbagger.alpha_validation import AlphaValidator
from tenbagger.monetization import AlphaDecayModel
from tenbagger.optimization import FactorNeutralizer, FactorWeightOptimizer, RegimeDetector
from tenbagger.portfolio import BacktestConfig, PortfolioBuilder, RiskMetrics


DEFAULT_STRUCTURAL_WEIGHTS = {
    "growth_score": 0.0,
    "quality_score": 0.0,
    "value_score": 0.0,
    "industry_score": 0.0,
    "momentum_score": 0.5,
    "risk_score": 0.5,
}


@dataclass(frozen=True)
class StructuralValidationResult:
    split_date: str
    classification: str
    criteria: dict[str, Any]
    regime_alpha: dict[str, Any]
    subsample_robustness: dict[str, Any]
    stability_report: dict[str, Any]
    randomization_test: dict[str, Any]
    failure_mode_diagnosis: dict[str, Any]
    oos_metrics: dict[str, Any]
    alpha_decay: dict[str, Any]


class StructuralAlphaValidator:
    """Validate whether the signal is real, pseudo, or absent structural alpha."""

    def __init__(
        self,
        weights: dict[str, float] | None = None,
        top_k: int = 10,
        random_iterations: int = 100,
        random_seed: int = 42,
    ) -> None:
        self.weights = weights or DEFAULT_STRUCTURAL_WEIGHTS
        self.top_k = top_k
        self.random_iterations = random_iterations
        self.random_seed = random_seed

    def run(self, factors: pd.DataFrame, prices: pd.DataFrame) -> StructuralValidationResult:
        scored = self._score_inputs(factors, prices)
        split_date = self._split_date(scored)
        oos_factors = scored[scored["date"] > split_date].copy()
        if oos_factors.empty:
            raise ValueError("No out-of-sample factor rows are available for structural validation.")

        enriched = AlphaValidator(horizons=(21, 63, 126)).attach_forward_returns(oos_factors, prices)
        regimes = RegimeDetector().detect(prices, scored)
        nav = PortfolioBuilder(self._backtest_config()).run_backtest(scored, prices)["nav"]
        nav["date"] = pd.to_datetime(nav["date"], errors="coerce")
        oos_nav = nav[nav["date"] > split_date].copy()
        if oos_nav.empty:
            raise ValueError("No out-of-sample NAV rows are available for structural validation.")

        oos_metrics = RiskMetrics().summarize(oos_nav, {})
        regime_alpha = MultiRegimeAlphaTest().run(enriched, oos_nav, regimes)
        subsample_robustness = SubsampleRobustnessTest().run(enriched, oos_nav, prices)
        randomization = RandomizationTest(self.random_iterations, self.random_seed).run(enriched)
        alpha_decay = AlphaDecayModel().fit(oos_factors, prices)
        stability = AlphaStabilityScorer().score(regime_alpha, subsample_robustness, alpha_decay)
        criteria = RealAlphaCriteriaEngine().criteria(oos_metrics, stability, randomization, alpha_decay)
        classification = RealAlphaCriteriaEngine().classify(criteria, randomization)
        failure_modes = FailureModeDiagnoser().diagnose(oos_metrics, stability, randomization, alpha_decay)

        return StructuralValidationResult(
            split_date=str(pd.Timestamp(split_date).date()),
            classification=classification,
            criteria=criteria,
            regime_alpha=regime_alpha,
            subsample_robustness=subsample_robustness,
            stability_report=stability,
            randomization_test=randomization,
            failure_mode_diagnosis=failure_modes,
            oos_metrics=oos_metrics,
            alpha_decay=alpha_decay,
        )

    def _score_inputs(self, factors: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
        neutralized = FactorNeutralizer().neutralize(factors, prices)
        scored = FactorWeightOptimizer._apply_weights(neutralized, self.weights, neutralized_scores=True)
        scored["date"] = pd.to_datetime(scored["date"], errors="coerce")
        return scored.dropna(subset=["date", "ts_code"]).sort_values(["date", "ts_code"])

    @staticmethod
    def _split_date(scored: pd.DataFrame) -> pd.Timestamp:
        dates = sorted(scored["date"].dropna().unique())
        if len(dates) < 10:
            raise ValueError("Need at least ten trading dates for structural validation.")
        return pd.Timestamp(dates[int(len(dates) * 0.7)])

    def _backtest_config(self) -> BacktestConfig:
        return BacktestConfig(
            top_k=self.top_k,
            rebalance="biweekly",
            weight_mode="volatility_adjusted",
            transaction_cost_rate=0.0005,
            slippage_rate=0.0005,
        )


class MultiRegimeAlphaTest:
    """Measure IC and PnL behavior across market regimes."""

    def run(self, enriched: pd.DataFrame, nav: pd.DataFrame, regimes: pd.DataFrame) -> dict[str, Any]:
        frame = self._attach_regimes(enriched, regimes)
        nav_frame = self._attach_regimes(nav, regimes)
        market = self._group_report(frame, nav_frame, "market_regime")
        style = self._group_report(frame, nav_frame, "style_regime")
        return {
            "market_regime": market,
            "style_regime": style,
            "assessed_regimes": int(sum(1 for item in market if item["return_observations"] >= 20)),
        }

    @staticmethod
    def _attach_regimes(frame: pd.DataFrame, regimes: pd.DataFrame) -> pd.DataFrame:
        result = frame.copy()
        result["date"] = pd.to_datetime(result["date"], errors="coerce")
        regime_frame = regimes.copy()
        regime_frame["date"] = pd.to_datetime(regime_frame["date"], errors="coerce")
        return result.merge(regime_frame, on="date", how="left")

    def _group_report(self, enriched: pd.DataFrame, nav: pd.DataFrame, column: str) -> list[dict[str, Any]]:
        rows = []
        labels = sorted(enriched[column].dropna().unique())
        for label in labels:
            ic_report = _rank_ic_report(enriched[enriched[column] == label])
            returns = nav.loc[nav[column] == label, "portfolio_return"]
            return_report = _return_report(returns)
            rows.append(
                {
                    column: str(label),
                    **ic_report,
                    **return_report,
                }
            )
        return rows


class SubsampleRobustnessTest:
    """Validate robustness across years, volatility regimes, and industries."""

    def run(self, enriched: pd.DataFrame, nav: pd.DataFrame, prices: pd.DataFrame) -> dict[str, Any]:
        frame = enriched.copy()
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        nav_frame = nav.copy()
        nav_frame["date"] = pd.to_datetime(nav_frame["date"], errors="coerce")
        return {
            "by_year": self._by_year(frame, nav_frame),
            "by_volatility_regime": self._by_volatility_regime(frame, nav_frame, prices),
            "by_industry": self._by_industry(frame),
        }

    def _by_year(self, enriched: pd.DataFrame, nav: pd.DataFrame) -> list[dict[str, Any]]:
        rows = []
        enriched = enriched.assign(year=enriched["date"].dt.year)
        nav = nav.assign(year=nav["date"].dt.year)
        for year in sorted(enriched["year"].dropna().unique()):
            year_int = int(year)
            rows.append(
                {
                    "year": year_int,
                    **_rank_ic_report(enriched[enriched["year"] == year]),
                    **_return_report(nav.loc[nav["year"] == year, "portfolio_return"]),
                }
            )
        return rows

    def _by_volatility_regime(
        self,
        enriched: pd.DataFrame,
        nav: pd.DataFrame,
        prices: pd.DataFrame,
    ) -> list[dict[str, Any]]:
        volatility = _volatility_regime_frame(prices)
        frame = enriched.merge(volatility, on="date", how="left")
        nav_frame = nav.merge(volatility, on="date", how="left")
        rows = []
        for label in ["low", "mid", "high"]:
            rows.append(
                {
                    "volatility_regime": label,
                    **_rank_ic_report(frame[frame["volatility_regime"] == label]),
                    **_return_report(nav_frame.loc[nav_frame["volatility_regime"] == label, "portfolio_return"]),
                }
            )
        return rows

    def _by_industry(self, enriched: pd.DataFrame) -> list[dict[str, Any]]:
        rows = []
        if "industry" not in enriched.columns:
            return rows
        for industry in sorted(enriched["industry"].dropna().unique()):
            subset = enriched[enriched["industry"] == industry]
            top_return = _top_bucket_forward_return(subset)
            rows.append(
                {
                    "industry": str(industry),
                    **_rank_ic_report(subset),
                    "top_bucket_21d_return": top_return,
                }
            )
        return rows


class RandomizationTest:
    """Compare the real signal to shuffled labels and permuted features."""

    def __init__(self, iterations: int = 100, random_seed: int = 42) -> None:
        self.iterations = iterations
        self.random_seed = random_seed

    def run(self, enriched: pd.DataFrame) -> dict[str, Any]:
        frame = enriched.dropna(subset=["date", "tenbagger_score", "future_21d_return"]).copy()
        actual_values = _rank_ic_values(frame)
        actual = float(actual_values["rank_ic"].mean()) if not actual_values.empty else 0.0
        if frame.empty:
            return {
                "actual_rank_ic_21d": 0.0,
                "label_shuffle": _random_summary([], actual),
                "feature_permutation": _random_summary([], actual),
                "iterations": self.iterations,
            }

        rng = random.Random(self.random_seed)
        label_means = []
        feature_means = []
        grouped = [group.copy() for _, group in frame.groupby("date", sort=True)]
        for _ in range(self.iterations):
            label_means.append(_shuffled_label_rank_ic(grouped, rng))
            feature_means.append(_permuted_feature_rank_ic(grouped, rng))

        return {
            "actual_rank_ic_21d": actual,
            "label_shuffle": _random_summary(label_means, actual),
            "feature_permutation": _random_summary(feature_means, actual),
            "iterations": self.iterations,
        }


class AlphaStabilityScorer:
    """Summarize IC, Sharpe, and decay stability."""

    def score(
        self,
        regime_alpha: dict[str, Any],
        subsample_robustness: dict[str, Any],
        alpha_decay: dict[str, Any],
    ) -> dict[str, Any]:
        ic_points = _collect_values(
            regime_alpha.get("market_regime", []),
            subsample_robustness.get("by_year", []),
            subsample_robustness.get("by_volatility_regime", []),
            key="rank_ic_mean",
            min_observations=10,
        )
        sharpe_points = _collect_values(
            regime_alpha.get("market_regime", []),
            subsample_robustness.get("by_year", []),
            key="sharpe",
            min_observations=20,
            observation_key="return_observations",
        )
        ic_variance = _variance(ic_points)
        sharpe_variance = _variance(sharpe_points)
        positive_sharpe_ratio = _positive_ratio(sharpe_points)
        decay_report = self._decay_report(alpha_decay)
        score = (
            max(0.0, 1.0 - min(ic_variance / 0.015, 1.0)) * 35.0
            + positive_sharpe_ratio * 35.0
            + (30.0 if decay_report["decay_slow"] else 0.0)
        )
        return {
            "score": float(score),
            "ic_variance": ic_variance,
            "ic_points": ic_points,
            "ic_stable": bool(ic_points and ic_variance <= 0.015),
            "sharpe_variance": sharpe_variance,
            "sharpe_points": sharpe_points,
            "positive_sharpe_ratio": positive_sharpe_ratio,
            "pnl_stable": bool(sharpe_points and positive_sharpe_ratio >= 0.67),
            **decay_report,
        }

    @staticmethod
    def _decay_report(alpha_decay: dict[str, Any]) -> dict[str, Any]:
        curve = alpha_decay.get("curve", [])
        rank_ics = [float(item.get("rank_ic_mean", 0.0)) for item in curve]
        if len(rank_ics) >= 2 and rank_ics[0] > 0:
            retention = rank_ics[-1] / rank_ics[0]
        else:
            retention = 0.0
        decay_rate = float(alpha_decay.get("decay_rate", 0.0))
        return {
            "decay_rate": decay_rate,
            "decay_retention": float(retention),
            "decay_slow": bool(rank_ics and min(rank_ics) > 0 and retention >= 0.5 and abs(decay_rate) <= 0.02),
        }


class RealAlphaCriteriaEngine:
    """Apply the explicit real-alpha criteria."""

    def criteria(
        self,
        oos_metrics: dict[str, Any],
        stability: dict[str, Any],
        randomization: dict[str, Any],
        alpha_decay: dict[str, Any],
    ) -> dict[str, Any]:
        label = randomization.get("label_shuffle", {})
        feature = randomization.get("feature_permutation", {})
        actual_rank_ic = float(randomization.get("actual_rank_ic_21d", 0.0))
        return {
            "rank_ic_gt_0_05": actual_rank_ic > 0.05,
            "rank_ic_stable": bool(stability.get("ic_stable")),
            "sharpe_positive_oos": float(oos_metrics.get("sharpe", 0.0)) > 0,
            "sharpe_positive_over_regimes": bool(stability.get("pnl_stable")),
            "label_shuffle_rejected": bool(label.get("significant")),
            "feature_permutation_rejected": bool(feature.get("significant")),
            "decay_slow": bool(stability.get("decay_slow")),
            "actual_rank_ic_21d": actual_rank_ic,
            "oos_sharpe": float(oos_metrics.get("sharpe", 0.0)),
            "decay_rate": float(alpha_decay.get("decay_rate", 0.0)),
        }

    def classify(self, criteria: dict[str, Any], randomization: dict[str, Any]) -> str:
        real_requirements = [
            criteria["rank_ic_gt_0_05"],
            criteria["rank_ic_stable"],
            criteria["sharpe_positive_oos"],
            criteria["sharpe_positive_over_regimes"],
            criteria["label_shuffle_rejected"],
            criteria["feature_permutation_rejected"],
            criteria["decay_slow"],
        ]
        if all(real_requirements):
            return "REAL"

        actual_rank_ic = float(randomization.get("actual_rank_ic_21d", 0.0))
        if actual_rank_ic > 0.03 or criteria["label_shuffle_rejected"] or criteria["feature_permutation_rejected"]:
            return "PSEUDO"
        return "NO ALPHA"


class FailureModeDiagnoser:
    """Name the main reason alpha fails the real-alpha gate."""

    def diagnose(
        self,
        oos_metrics: dict[str, Any],
        stability: dict[str, Any],
        randomization: dict[str, Any],
        alpha_decay: dict[str, Any],
    ) -> dict[str, Any]:
        sharpe = float(oos_metrics.get("sharpe", 0.0))
        turnover = float(oos_metrics.get("turnover_rate", 0.0))
        actual_rank_ic = float(randomization.get("actual_rank_ic_21d", 0.0))
        label = randomization.get("label_shuffle", {})
        feature = randomization.get("feature_permutation", {})
        modes = {
            "cost_failure": bool(sharpe <= 0 and turnover >= 0.25),
            "turnover_failure": bool(turnover >= 0.5),
            "factor_decay_failure": not bool(stability.get("decay_slow")),
            "permutation_failure": not (bool(label.get("significant")) and bool(feature.get("significant"))),
            "pnl_failure": bool(sharpe <= 0 or not stability.get("pnl_stable")),
            "ic_instability_failure": not bool(stability.get("ic_stable")),
        }
        if actual_rank_ic <= 0.03:
            primary = "no_structural_alpha"
        elif modes["pnl_failure"]:
            primary = "ranking_signal_not_monetized"
        elif modes["permutation_failure"]:
            primary = "randomization_not_rejected"
        elif modes["factor_decay_failure"]:
            primary = "factor_decay_or_horizon_instability"
        else:
            primary = "no_primary_failure"
        return {
            "primary_failure": primary,
            "modes": modes,
            "oos_sharpe": sharpe,
            "actual_rank_ic_21d": actual_rank_ic,
            "turnover_rate": turnover,
            "decay_rate": float(alpha_decay.get("decay_rate", 0.0)),
        }


def _rank_ic_values(
    frame: pd.DataFrame,
    factor: str = "tenbagger_score",
    target: str = "future_21d_return",
) -> pd.DataFrame:
    rows = []
    usable = frame.dropna(subset=["date", factor, target])
    for date_value, date_df in usable.groupby("date", sort=True):
        if len(date_df) < 3:
            continue
        if date_df[factor].nunique() < 2 or date_df[target].nunique() < 2:
            continue
        rows.append(
            {
                "date": date_value,
                "rank_ic": float(date_df[factor].rank().corr(date_df[target].rank(), method="pearson")),
            }
        )
    return pd.DataFrame(rows)


def _rank_ic_report(frame: pd.DataFrame) -> dict[str, Any]:
    values = _rank_ic_values(frame)
    if values.empty:
        return {
            "rank_ic_mean": 0.0,
            "rank_ic_std": 0.0,
            "rank_ic_variance": 0.0,
            "rank_ic_positive_rate": 0.0,
            "ic_observations": 0,
        }
    rank_ic = values["rank_ic"].dropna()
    return {
        "rank_ic_mean": float(rank_ic.mean()),
        "rank_ic_std": float(rank_ic.std(ddof=0)),
        "rank_ic_variance": float(rank_ic.var(ddof=0)),
        "rank_ic_positive_rate": float((rank_ic > 0).mean()),
        "ic_observations": int(len(rank_ic)),
    }


def _return_report(returns: pd.Series) -> dict[str, Any]:
    values = pd.to_numeric(returns, errors="coerce").dropna()
    if values.empty:
        return {
            "annual_return": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
            "return_observations": 0,
        }
    std = float(values.std(ddof=0))
    sharpe = float(values.mean() / std * (252**0.5)) if std > 0 else 0.0
    annual_return = float((1 + values.mean()) ** 252 - 1)
    nav = (1 + values).cumprod()
    drawdown = nav / nav.cummax() - 1
    return {
        "annual_return": annual_return,
        "sharpe": sharpe,
        "max_drawdown": float(drawdown.min()),
        "win_rate": float((values > 0).mean()),
        "return_observations": int(len(values)),
    }


def _volatility_regime_frame(prices: pd.DataFrame) -> pd.DataFrame:
    price_frame = prices[["ts_code", "date", "close"]].copy()
    price_frame["date"] = pd.to_datetime(price_frame["date"], errors="coerce")
    price_frame["close"] = pd.to_numeric(price_frame["close"], errors="coerce")
    price_frame = price_frame.sort_values(["ts_code", "date"])
    price_frame["ret"] = price_frame.groupby("ts_code")["close"].pct_change()
    market = price_frame.groupby("date", as_index=False)["ret"].mean().sort_values("date")
    market["volatility"] = market["ret"].rolling(60, min_periods=20).std()
    valid = market["volatility"].dropna()
    if valid.nunique() < 3:
        market["volatility_regime"] = "mid"
        return market[["date", "volatility_regime"]]
    low = valid.quantile(1 / 3)
    high = valid.quantile(2 / 3)
    market["volatility_regime"] = "mid"
    market.loc[market["volatility"] <= low, "volatility_regime"] = "low"
    market.loc[market["volatility"] >= high, "volatility_regime"] = "high"
    return market[["date", "volatility_regime"]]


def _top_bucket_forward_return(frame: pd.DataFrame) -> float:
    usable = frame.dropna(subset=["tenbagger_score", "future_21d_return"]).copy()
    if usable.empty:
        return 0.0
    returns = []
    for _, date_df in usable.groupby("date", sort=True):
        top_count = max(1, int(len(date_df) * 0.2))
        returns.append(float(date_df.sort_values("tenbagger_score", ascending=False).head(top_count)["future_21d_return"].mean()))
    return float(pd.Series(returns).dropna().mean()) if returns else 0.0


def _shuffled_label_rank_ic(grouped: list[pd.DataFrame], rng: random.Random) -> float:
    values = []
    for group in grouped:
        if len(group) < 3:
            continue
        if group["tenbagger_score"].nunique() < 2 or group["future_21d_return"].nunique() < 2:
            continue
        shuffled = group["future_21d_return"].sample(frac=1.0, random_state=rng.randrange(1_000_000_000)).to_numpy()
        target = pd.Series(shuffled, index=group.index)
        corr = group["tenbagger_score"].rank().corr(target.rank(), method="pearson")
        if pd.notna(corr):
            values.append(float(corr))
    return float(pd.Series(values).mean()) if values else 0.0


def _permuted_feature_rank_ic(grouped: list[pd.DataFrame], rng: random.Random) -> float:
    values = []
    for group in grouped:
        if len(group) < 3:
            continue
        if group["tenbagger_score"].nunique() < 2 or group["future_21d_return"].nunique() < 2:
            continue
        shuffled = group["tenbagger_score"].sample(frac=1.0, random_state=rng.randrange(1_000_000_000)).to_numpy()
        factor = pd.Series(shuffled, index=group.index)
        corr = factor.rank().corr(group["future_21d_return"].rank(), method="pearson")
        if pd.notna(corr):
            values.append(float(corr))
    return float(pd.Series(values).mean()) if values else 0.0


def _random_summary(samples: list[float], actual: float) -> dict[str, Any]:
    if not samples:
        return {
            "mean": 0.0,
            "p95": 0.0,
            "p_value": 1.0,
            "significant": False,
        }
    values = pd.Series(samples)
    p_value = float((1 + (values >= actual).sum()) / (len(values) + 1))
    return {
        "mean": float(values.mean()),
        "p95": float(values.quantile(0.95)),
        "p_value": p_value,
        "significant": bool(actual > 0 and p_value <= 0.05),
    }


def _collect_values(*groups: list[dict[str, Any]], key: str, min_observations: int, observation_key: str = "ic_observations") -> list[float]:
    values = []
    for group in groups:
        for item in group:
            if int(item.get(observation_key, 0)) >= min_observations:
                values.append(float(item.get(key, 0.0)))
    return values


def _variance(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    return float(pd.Series(values).var(ddof=0))


def _positive_ratio(values: list[float]) -> float:
    if not values:
        return 0.0
    return float((pd.Series(values) > 0).mean())
