from __future__ import annotations

import pandas as pd

from engine.data_loader import MarketData
from engine.theme_engine import add_growth_theme_profiles


def compute_factors(market_data: MarketData) -> pd.DataFrame:
    daily = market_data.daily.copy()
    if daily.empty:
        return pd.DataFrame()

    daily["close"] = pd.to_numeric(daily["close"], errors="coerce")
    daily["pct_chg"] = pd.to_numeric(daily.get("pct_chg"), errors="coerce")
    daily["amount"] = pd.to_numeric(daily.get("amount"), errors="coerce")
    daily["vol"] = pd.to_numeric(daily.get("vol"), errors="coerce")
    daily = daily.dropna(subset=["ts_code", "trade_date", "close"])
    daily = daily.sort_values(["trade_date", "ts_code"])

    close_wide = daily.pivot_table(index="trade_date", columns="ts_code", values="close")
    amount_wide = daily.pivot_table(index="trade_date", columns="ts_code", values="amount")
    returns = close_wide.pct_change()
    latest_close = close_wide.iloc[-1]
    observation_count = close_wide.notna().sum()
    if len(close_wide) > 5:
        base_close_5d = close_wide.shift(5).iloc[-1]
    else:
        base_close_5d = close_wide.iloc[0]
    if len(close_wide) > 20:
        base_close = close_wide.shift(20).iloc[-1]
    else:
        base_close = close_wide.iloc[0]
    if len(close_wide) > 60:
        base_close_60d = close_wide.shift(60).iloc[-1]
    else:
        base_close_60d = close_wide.iloc[0]
    if len(close_wide) > 120:
        base_close_120d = close_wide.shift(120).iloc[-1]
    else:
        base_close_120d = close_wide.iloc[0]

    momentum_5d = latest_close / base_close_5d - 1
    momentum_20d = latest_close / base_close - 1
    momentum_60d = latest_close / base_close_60d - 1
    momentum_120d = latest_close / base_close_120d - 1
    volatility_20d = returns.tail(20).std()
    rolling_high_120 = close_wide.tail(min(len(close_wide), 120)).max()
    high_120_distance = latest_close / rolling_high_120 - 1
    amount_baseline_20d = amount_wide.tail(min(len(amount_wide), 20)).mean()
    latest_amount = amount_wide.iloc[-1].reindex(latest_close.index)
    amount_expansion_20d = latest_amount / amount_baseline_20d.reindex(latest_close.index)
    latest_daily = daily.groupby("ts_code", as_index=False).tail(1)

    factors = pd.DataFrame(
        {
            "ts_code": latest_close.index.astype(str),
            "momentum_5d": momentum_5d.values,
            "momentum_20d": momentum_20d.values,
            "momentum_60d": momentum_60d.values,
            "momentum_120d": momentum_120d.values,
            "volatility_20d": volatility_20d.reindex(latest_close.index).values,
            "amount_expansion_20d": amount_expansion_20d.reindex(latest_close.index).values,
            "high_120_distance": high_120_distance.reindex(latest_close.index).values,
            "observation_count": observation_count.reindex(latest_close.index).values,
            "close": latest_close.values,
        }
    )

    latest_columns = [
        column
        for column in ["ts_code", "trade_date", "amount", "vol", "pct_chg"]
        if column in latest_daily.columns
    ]
    factors = factors.merge(latest_daily[latest_columns], on="ts_code", how="left")
    factors = factors.rename(
        columns={
            "amount": "latest_amount",
            "vol": "latest_vol",
            "pct_chg": "latest_pct_chg",
        }
    )

    daily_basic = market_data.daily_basic.copy()
    if not daily_basic.empty:
        daily_basic = daily_basic.groupby("ts_code", as_index=False).tail(1)
        keep_columns = [
            column
            for column in ["ts_code", "pe", "pb", "roe", "turnover_rate", "volume_ratio"]
            if column in daily_basic.columns
        ]
        factors = factors.merge(daily_basic[keep_columns], on="ts_code", how="left")

    financial = market_data.financial_indicator.copy()
    if not financial.empty:
        financial = financial.rename(
            columns={
                "or_yoy": "revenue_growth_yoy",
                "netprofit_yoy": "net_profit_growth_yoy",
            }
        )
        financial["roe"] = pd.to_numeric(financial.get("roe"), errors="coerce")
        financial = financial.sort_values(["ts_code", "end_date"])
        financial["roe_improvement"] = financial.groupby("ts_code")["roe"].diff()
        financial = financial.groupby("ts_code", as_index=False).tail(1)
        keep_columns = [
            column
            for column in [
                "ts_code",
                "roe",
                "revenue_growth_yoy",
                "net_profit_growth_yoy",
                "roe_improvement",
                "ocf_to_profit",
            ]
            if column in financial.columns
        ]
        factors = factors.merge(
            financial[keep_columns],
            on="ts_code",
            how="left",
            suffixes=("", "_financial"),
        )
        if "roe_financial" in factors.columns:
            if "roe" in factors.columns:
                factors["roe"] = factors["roe_financial"].combine_first(factors["roe"])
            else:
                factors["roe"] = factors["roe_financial"]
            factors = factors.drop(columns=["roe_financial"])

    stock_basic = market_data.stock_basic.copy()
    if not stock_basic.empty:
        keep_columns = [
            column
            for column in ["ts_code", "name", "industry", "list_date"]
            if column in stock_basic.columns
        ]
        factors = factors.merge(stock_basic[keep_columns], on="ts_code", how="left")
    factors["exchange"] = factors["ts_code"].astype(str).str.rsplit(".", n=1).str[-1]
    if "list_date" in factors.columns:
        trade_date = pd.to_datetime(str(market_data.trade_date), format="%Y%m%d", errors="coerce")
        list_dates = pd.to_datetime(factors["list_date"].astype(str), format="%Y%m%d", errors="coerce")
        factors["list_age_days"] = (trade_date - list_dates).dt.days

    for column in [
        "momentum_20d",
        "momentum_60d",
        "momentum_120d",
        "momentum_5d",
        "volatility_20d",
        "amount_expansion_20d",
        "high_120_distance",
        "observation_count",
        "latest_amount",
        "latest_vol",
        "latest_pct_chg",
        "pe",
        "pb",
        "roe",
        "roe_improvement",
        "revenue_growth_yoy",
        "net_profit_growth_yoy",
        "ocf_to_profit",
        "turnover_rate",
        "volume_ratio",
        "list_age_days",
    ]:
        if column in factors.columns:
            factors[column] = pd.to_numeric(factors[column], errors="coerce")

    growth_fields = [
        column
        for column in ["revenue_growth_yoy", "net_profit_growth_yoy", "roe", "roe_improvement"]
        if column in factors.columns
    ]
    factors["growth_data_quality"] = (
        factors[growth_fields].notna().mean(axis=1) if growth_fields else 0.0
    )
    factors = add_growth_theme_profiles(factors, market_data.theme_membership)

    return _add_industry_strength(factors)


def _add_industry_strength(factors: pd.DataFrame) -> pd.DataFrame:
    if factors.empty or "industry" not in factors.columns:
        factors = factors.copy()
        factors["industry_relative_strength"] = 0.5
        return factors

    enriched = factors.copy()
    industry = enriched["industry"].fillna("Unknown").astype(str)
    momentum_20d = pd.to_numeric(enriched.get("momentum_20d"), errors="coerce")
    momentum_60d = pd.to_numeric(enriched.get("momentum_60d"), errors="coerce")
    industry_momentum_20d = momentum_20d.groupby(industry).transform("median")
    industry_momentum_60d = momentum_60d.groupby(industry).transform("median")
    industry_score_20d = _rank(industry_momentum_20d)
    industry_score_60d = _rank(industry_momentum_60d)
    enriched["industry_relative_strength"] = (
        0.60 * industry_score_20d + 0.40 * industry_score_60d
    ).clip(0, 1)
    return enriched


def _rank(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    valid = numeric.dropna()
    if valid.empty or valid.nunique() <= 1:
        return pd.Series(0.5, index=series.index, dtype="float64")
    return numeric.rank(method="average", pct=True).fillna(0.5).astype("float64")
