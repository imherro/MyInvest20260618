"""Portfolio construction and backtesting for TASK 4."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Literal

import pandas as pd

from tenbagger.config import DEFAULT_DATA_DIR, compact_date, get_setting
from tenbagger.factor_engine import FactorEngine
from tenbagger.universe import filter_frame_to_universe


WeightMode = Literal["equal", "score", "volatility_adjusted", "score_convex", "top_heavy"]


@dataclass(frozen=True)
class BacktestConfig:
    top_k: int = 20
    rebalance: str = "monthly"
    weight_mode: WeightMode = "score"
    transaction_cost_rate: float = 0.002
    slippage_rate: float = 0.0005
    annualization_days: int = 252
    apply_hard_filter: bool = False


class PortfolioBuilder:
    """Build top-K portfolios and run walk-forward daily NAV simulation."""

    def __init__(self, config: BacktestConfig | None = None) -> None:
        self.config = config or BacktestConfig()

    def run_backtest(self, factors: pd.DataFrame, prices: pd.DataFrame) -> dict:
        prepared = self._prepare_inputs(factors, prices)
        rebalance_dates = self._rebalance_dates(prepared)
        if len(rebalance_dates) < 2:
            raise ValueError("Need at least two rebalance dates for portfolio backtest.")

        nav_rows = []
        holding_rows = []
        contribution_rows = []
        previous_weights: pd.Series = pd.Series(dtype=float)
        nav = 1.0

        for idx, signal_date in enumerate(rebalance_dates[:-1]):
            next_signal_date = rebalance_dates[idx + 1]
            selected = self.build_top_k_portfolio(prepared, signal_date)
            if selected.empty:
                continue

            weights = self._allocate_weights(selected)
            turnover = self._turnover(previous_weights, weights)
            cost = turnover * (self.config.transaction_cost_rate + self.config.slippage_rate)
            previous_weights = weights

            period = prepared[
                (prepared["date"] > signal_date)
                & (prepared["date"] <= next_signal_date)
                & (prepared["ts_code"].isin(weights.index))
            ].copy()
            if period.empty:
                continue

            first_day = True
            for date_value, date_df in period.groupby("date", sort=True):
                daily_return = float((date_df.set_index("ts_code")["daily_return"].fillna(0.0) * weights).sum())
                net_return = daily_return - cost if first_day else daily_return
                nav *= 1 + net_return
                nav_rows.append(
                    {
                        "date": date_value,
                        "portfolio_return": net_return,
                        "gross_return": daily_return,
                        "transaction_cost": cost if first_day else 0.0,
                        "turnover": turnover if first_day else 0.0,
                        "nav": nav,
                        "holding_count": int(len(weights)),
                    }
                )
                first_day = False

            for ts_code, weight in weights.items():
                holding_rows.append(
                    {
                        "rebalance_date": signal_date,
                        "ts_code": ts_code,
                        "weight": float(weight),
                    }
                )
            contribution_rows.append(self._factor_contribution(selected, weights, signal_date))

        nav_df = pd.DataFrame(nav_rows)
        holdings_df = pd.DataFrame(holding_rows)
        contribution_df = pd.DataFrame(contribution_rows)
        if nav_df.empty:
            raise ValueError("Portfolio backtest produced no NAV rows.")

        return {
            "nav": nav_df,
            "holdings": holdings_df,
            "factor_contribution": contribution_df,
        }

    def build_top_k_portfolio(self, data: pd.DataFrame, signal_date) -> pd.DataFrame:
        snapshot = data[data["date"] == signal_date].copy()
        if self.config.apply_hard_filter and "is_candidate" in snapshot.columns:
            snapshot = snapshot[snapshot["is_candidate"]]
        snapshot = snapshot.dropna(subset=["tenbagger_score", "ts_code"])
        return snapshot.sort_values("tenbagger_score", ascending=False).head(self.config.top_k)

    def _prepare_inputs(self, factors: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
        factor_frame = factors.copy()
        factor_frame["date"] = pd.to_datetime(factor_frame["date"], errors="coerce")

        price_frame = prices[["ts_code", "date", "close"]].copy()
        price_frame["date"] = pd.to_datetime(price_frame["date"], errors="coerce")
        price_frame["close"] = pd.to_numeric(price_frame["close"], errors="coerce")
        price_frame = price_frame.sort_values(["ts_code", "date"])
        price_frame["daily_return"] = price_frame.groupby("ts_code")["close"].pct_change()

        merged = factor_frame.merge(
            price_frame[["ts_code", "date", "daily_return"]],
            on=["ts_code", "date"],
            how="left",
        )
        return merged.dropna(subset=["date", "ts_code"]).sort_values(["date", "ts_code"])

    def _rebalance_dates(self, data: pd.DataFrame) -> list[pd.Timestamp]:
        dates = data[["date"]].drop_duplicates().sort_values("date")
        if self.config.rebalance == "monthly":
            dates["period"] = dates["date"].dt.to_period("M")
            return dates.groupby("period")["date"].max().tolist()
        if self.config.rebalance == "weekly":
            dates["period"] = dates["date"].dt.to_period("W")
            return dates.groupby("period")["date"].max().tolist()
        if self.config.rebalance == "biweekly":
            dates["period"] = dates["date"].dt.to_period("W")
            weekly_dates = dates.groupby("period")["date"].max().tolist()
            return weekly_dates[::2]
        raise ValueError(f"Unsupported rebalance frequency: {self.config.rebalance}")

    def _allocate_weights(self, selected: pd.DataFrame) -> pd.Series:
        if self.config.weight_mode == "equal":
            raw = pd.Series(1.0, index=selected["ts_code"])
        elif self.config.weight_mode == "score":
            raw = pd.Series(
                pd.to_numeric(selected["tenbagger_score"], errors="coerce").clip(lower=0.0).values,
                index=selected["ts_code"],
            )
        elif self.config.weight_mode == "volatility_adjusted":
            volatility = pd.to_numeric(selected.get("volatility_60d", 0.0), errors="coerce").replace({0: pd.NA})
            raw = pd.Series(1.0 / volatility.fillna(volatility.median()).values, index=selected["ts_code"])
            raw = raw * pd.to_numeric(selected["tenbagger_score"], errors="coerce").clip(lower=0.0).values
        elif self.config.weight_mode == "score_convex":
            raw = pd.Series(
                pd.to_numeric(selected["tenbagger_score"], errors="coerce").clip(lower=0.0).values ** 2,
                index=selected["ts_code"],
            )
        elif self.config.weight_mode == "top_heavy":
            raw = pd.Series(range(len(selected), 0, -1), index=selected["ts_code"], dtype=float)
        else:
            raise ValueError(f"Unsupported weight mode: {self.config.weight_mode}")

        raw = raw.fillna(0.0)
        if raw.sum() <= 0:
            raw = pd.Series(1.0, index=selected["ts_code"])
        return raw / raw.sum()

    @staticmethod
    def _turnover(previous: pd.Series, current: pd.Series) -> float:
        aligned = pd.concat([previous.rename("previous"), current.rename("current")], axis=1).fillna(0.0)
        return float((aligned["current"] - aligned["previous"]).abs().sum() / 2)

    @staticmethod
    def _factor_contribution(selected: pd.DataFrame, weights: pd.Series, signal_date) -> dict:
        components = {
            "growth": ("growth_score", 0.35),
            "quality": ("quality_score", 0.25),
            "value": ("value_score", 0.15),
            "industry": ("industry_score", 0.10),
            "momentum": ("momentum_score", 0.10),
            "risk": ("risk_score", 0.05),
        }
        selected = selected.set_index("ts_code")
        total = 0.0
        row = {"date": signal_date}
        for name, (column, coefficient) in components.items():
            contribution = float((selected[column].fillna(0.0) * weights).sum() * coefficient)
            row[f"{name}_contribution"] = contribution
            total += contribution
        row["dominant_factor"] = max(
            components,
            key=lambda key: row[f"{key}_contribution"],
        )
        row["weighted_score"] = total
        return row


class BenchmarkLoader:
    """Load benchmark index data, falling back to equal-weight universe returns."""

    def load(
        self,
        start_date,
        end_date,
        fallback_returns: pd.DataFrame,
    ) -> dict[str, pd.DataFrame]:
        token = get_setting("TUSHARE_TOKEN")
        if token:
            try:
                return self._load_tushare_indices(token, start_date, end_date)
            except Exception:
                pass
        return {"EQUAL_WEIGHT_UNIVERSE": self._equal_weight_benchmark(fallback_returns)}

    def _load_tushare_indices(self, token: str, start_date, end_date) -> dict[str, pd.DataFrame]:
        import tushare as ts

        ts.set_token(token)
        pro = ts.pro_api()
        result = {}
        for code, name in {"000300.SH": "CSI300", "000905.SH": "CSI500"}.items():
            df = pro.index_daily(
                ts_code=code,
                start_date=compact_date(start_date),
                end_date=compact_date(end_date),
                fields="ts_code,trade_date,close",
            )
            if df.empty:
                continue
            df = df.rename(columns={"trade_date": "date"})
            df["date"] = pd.to_datetime(df["date"], format="%Y%m%d", errors="coerce")
            df = df.sort_values("date")
            df["benchmark_return"] = pd.to_numeric(df["close"], errors="coerce").pct_change()
            result[name] = df[["date", "benchmark_return"]].dropna()
        if not result:
            raise RuntimeError("No benchmark index rows returned.")
        return result

    @staticmethod
    def _equal_weight_benchmark(returns: pd.DataFrame) -> pd.DataFrame:
        benchmark = returns.groupby("date", as_index=False)["daily_return"].mean()
        return benchmark.rename(columns={"daily_return": "benchmark_return"})


class RiskMetrics:
    def __init__(self, annualization_days: int = 252) -> None:
        self.annualization_days = annualization_days

    def summarize(self, nav: pd.DataFrame, benchmarks: dict[str, pd.DataFrame]) -> dict:
        returns = nav["portfolio_return"].fillna(0.0)
        turnover_sample = nav.loc[nav["turnover"] > 0, "turnover"]
        turnover_rate = float(turnover_sample.mean()) if not turnover_sample.empty else 0.0
        result = {
            "annual_return": self._annual_return(nav["nav"]),
            "sharpe": self._sharpe(returns),
            "max_drawdown": self._max_drawdown(nav["nav"]),
            "volatility": float(returns.std(ddof=0) * (self.annualization_days**0.5)),
            "win_rate": float((returns > 0).mean()),
            "turnover_rate": turnover_rate,
            "total_transaction_cost": float(nav["transaction_cost"].sum()),
        }

        benchmark_stats = {}
        for name, benchmark in benchmarks.items():
            aligned = nav[["date", "portfolio_return"]].merge(benchmark, on="date", how="inner")
            if aligned.empty:
                continue
            benchmark_nav = (1 + aligned["benchmark_return"].fillna(0.0)).cumprod()
            benchmark_stats[name] = {
                "annual_return": self._annual_return(benchmark_nav),
                "max_drawdown": self._max_drawdown(benchmark_nav),
                "excess_return": result["annual_return"] - self._annual_return(benchmark_nav),
                "beta": self._beta(aligned["portfolio_return"], aligned["benchmark_return"]),
            }
        result["benchmarks"] = benchmark_stats
        return result

    def _annual_return(self, nav: pd.Series) -> float:
        if len(nav) < 2:
            return 0.0
        total_return = float(nav.iloc[-1] / nav.iloc[0] - 1)
        years = len(nav) / self.annualization_days
        return float((1 + total_return) ** (1 / years) - 1) if years > 0 else 0.0

    def _sharpe(self, returns: pd.Series) -> float:
        std = float(returns.std(ddof=0))
        if std == 0:
            return 0.0
        return float(returns.mean() / std * (self.annualization_days**0.5))

    @staticmethod
    def _max_drawdown(nav: pd.Series) -> float:
        drawdown = nav / nav.cummax() - 1
        return float(drawdown.min())

    @staticmethod
    def _beta(portfolio: pd.Series, benchmark: pd.Series) -> float:
        variance = float(benchmark.var(ddof=0))
        if variance == 0:
            return 0.0
        return float(portfolio.cov(benchmark, ddof=0) / variance)


def load_local_task_data(
    data_dir: Path | str = DEFAULT_DATA_DIR,
    universe: Iterable[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    engine = FactorEngine()
    prices = engine.read_task1_parquet(data_dir, universe=universe)
    factors_dir = Path(data_dir) / "factors" / "by_stock"
    if factors_dir.exists() and list(factors_dir.glob("*.parquet")):
        factors = pd.concat([pd.read_parquet(path) for path in sorted(factors_dir.glob("*.parquet"))], ignore_index=True)
        factors = filter_frame_to_universe(factors, universe)
        if factors.empty:
            raise ValueError("No factor rows match the selected universe.")
    else:
        factors = engine.compute(prices)
    return factors, prices
