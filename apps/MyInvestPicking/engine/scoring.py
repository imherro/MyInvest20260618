from __future__ import annotations

import pandas as pd

GROWTH_TREND_WEIGHTS = {
    "trend": 0.27,
    "growth": 0.25,
    "quality": 0.15,
    "industry_strength": 0.15,
    "risk": 0.10,
    "value": 0.08,
}

GROWTH_INDUSTRY_KEYWORDS = (
    "半导体",
    "芯片",
    "元器件",
    "电子",
    "通信",
    "软件",
    "IT",
    "互联网",
    "人工智能",
    "AI",
    "机器人",
    "自动化",
    "专用机械",
    "通用机械",
    "电气设备",
    "电池",
    "光伏",
    "新能源",
    "汽车",
    "航空",
    "军工",
    "医疗保健",
    "生物制药",
    "创新药",
    "Tech",
    "Pharma",
    "Auto",
)

SECONDARY_GROWTH_INDUSTRY_KEYWORDS = (
    "化学制药",
    "医药",
    "新材料",
    "化纤",
    "矿物制品",
    "有色",
    "Consumer",
)

FINANCIAL_INDUSTRY_KEYWORDS = ("银行", "证券", "保险", "多元金融", "Bank")

LOW_GROWTH_INDUSTRY_KEYWORDS = (
    "房地产",
    "煤炭",
    "石油",
    "钢铁",
    "水泥",
    "建筑",
    "公路",
    "港口",
    "机场",
    "Energy",
)


def _rank_score(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce").replace([float("inf"), -float("inf")], pd.NA)
    valid = numeric.dropna()
    if valid.empty or valid.nunique() <= 1:
        return pd.Series(0.5, index=series.index, dtype="float64")

    lower = valid.quantile(0.01)
    upper = valid.quantile(0.99)
    clipped = numeric.clip(lower=lower, upper=upper)
    ranked = clipped.rank(method="average", pct=True, ascending=higher_is_better)
    return ranked.fillna(0.5).astype("float64")


def _score_column(frame: pd.DataFrame, column: str, higher_is_better: bool = True) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(0.5, index=frame.index, dtype="float64")
    return _rank_score(frame[column], higher_is_better)


def score_stocks(factors: pd.DataFrame, regime_state: str | None = None) -> pd.DataFrame:
    if factors.empty:
        return factors.copy()

    scored = factors.copy()
    scored["momentum"] = _score_column(scored, "momentum_20d", True)
    scored["momentum_60d_score"] = _score_column(scored, "momentum_60d", True)
    scored["momentum_120d_score"] = _score_column(scored, "momentum_120d", True)
    scored["amount_expansion_score"] = _score_column(scored, "amount_expansion_20d", True)
    scored["high_120_proximity_score"] = _score_column(scored, "high_120_distance", True)
    scored["roe_score"] = _score_column(scored, "roe", True)
    scored["roe_improvement_score"] = _score_column(scored, "roe_improvement", True)
    scored["revenue_growth_score"] = _score_column(scored, "revenue_growth_yoy", True)
    scored["net_profit_growth_score"] = _score_column(scored, "net_profit_growth_yoy", True)
    scored["cashflow_quality_score"] = _score_column(scored, "ocf_to_profit", True)
    scored["growth_data_quality"] = _bounded_column(scored, "growth_data_quality")
    scored["quality"] = (
        0.40 * scored["roe_score"]
        + 0.25 * scored["revenue_growth_score"]
        + 0.20 * scored["net_profit_growth_score"]
        + 0.15 * scored["cashflow_quality_score"]
    )
    raw_growth = (
        0.25 * scored["revenue_growth_score"]
        + 0.25 * scored["net_profit_growth_score"]
        + 0.20 * scored["roe_score"]
        + 0.15 * scored["roe_improvement_score"]
        + 0.10 * scored["amount_expansion_score"]
        + 0.05 * scored["high_120_proximity_score"]
    )
    scored["growth"] = (raw_growth * (0.55 + 0.45 * scored["growth_data_quality"])).clip(0, 1)
    scored["trend"] = (
        0.20 * scored["momentum"]
        + 0.40 * scored["momentum_60d_score"]
        + 0.25 * scored["momentum_120d_score"]
        + 0.10 * scored["high_120_proximity_score"]
        + 0.05 * scored["amount_expansion_score"]
    )

    value_parts = []
    if "pe" in scored.columns:
        value_parts.append(_rank_score(scored["pe"], False))
    if "pb" in scored.columns:
        value_parts.append(_rank_score(scored["pb"], False))
    scored["value"] = sum(value_parts) / len(value_parts) if value_parts else 0.5
    scored["risk"] = _score_column(scored, "volatility_20d", False)
    scored["industry_strength"] = _bounded_column(scored, "industry_relative_strength")
    scored["growth_industry_profile"] = _growth_industry_profile(scored)
    scored["growth_theme_profile"] = _bounded_column(scored, "growth_theme_profile")

    scored["score"] = (
        GROWTH_TREND_WEIGHTS["trend"] * scored["trend"]
        + GROWTH_TREND_WEIGHTS["growth"] * scored["growth"]
        + GROWTH_TREND_WEIGHTS["quality"] * scored["quality"]
        + GROWTH_TREND_WEIGHTS["industry_strength"] * scored["industry_strength"]
        + GROWTH_TREND_WEIGHTS["risk"] * scored["risk"]
        + GROWTH_TREND_WEIGHTS["value"] * scored["value"]
    ).clip(0, 1)
    scored["trend_contribution"] = GROWTH_TREND_WEIGHTS["trend"] * scored["trend"]
    scored["growth_contribution"] = GROWTH_TREND_WEIGHTS["growth"] * scored["growth"]
    scored["quality_contribution"] = GROWTH_TREND_WEIGHTS["quality"] * scored["quality"]
    scored["industry_strength_contribution"] = (
        GROWTH_TREND_WEIGHTS["industry_strength"] * scored["industry_strength"]
    )
    scored["value_contribution"] = GROWTH_TREND_WEIGHTS["value"] * scored["value"]
    scored["risk_contribution"] = GROWTH_TREND_WEIGHTS["risk"] * scored["risk"]
    scored["momentum_contribution"] = scored["trend_contribution"]
    scored["value_candidate_score"] = (
        0.45 * scored["value"]
        + 0.20 * scored["quality"]
        + 0.15 * scored["risk"]
        + 0.10 * scored["trend"]
        + 0.10 * scored["industry_strength"]
    ).clip(0, 1)
    raw_growth_candidate = (
        0.30 * scored["growth"]
        + 0.20 * scored["trend"]
        + 0.20 * scored["growth_theme_profile"]
        + 0.10 * scored["growth_industry_profile"]
        + 0.10 * scored["amount_expansion_score"]
        + 0.05 * scored["quality"]
        + 0.03 * scored["industry_strength"]
        + 0.02 * scored["risk"]
    )
    growth_evidence = (
        0.40 * scored["growth_data_quality"]
        + 0.35 * scored["growth_theme_profile"]
        + 0.15 * scored["growth_industry_profile"]
        + 0.10 * scored["amount_expansion_score"]
    ).clip(0, 1)
    scored["growth_candidate_score"] = (
        raw_growth_candidate * (0.55 + 0.45 * growth_evidence)
    )
    financial = _financial_industry_mask(scored)
    low_growth_data = scored["growth_data_quality"] < 0.50
    scored.loc[financial & low_growth_data, "growth_candidate_score"] *= 0.35
    scored.loc[financial & ~low_growth_data, "growth_candidate_score"] *= 0.75
    scored["growth_candidate_score"] = scored["growth_candidate_score"].clip(0, 1)
    scored["trend_candidate_score"] = (
        0.50 * scored["trend"]
        + 0.20 * scored["industry_strength"]
        + 0.15 * scored["growth"]
        + 0.10 * scored["amount_expansion_score"]
        + 0.05 * scored["risk"]
    ).clip(0, 1)
    scored["risk_adjust_factor"] = (0.75 + 0.25 * scored["risk"]).clip(0.75, 1.0)
    scored["regime_multiplier"] = _regime_multiplier(scored, regime_state)
    scored["factor_health_score"] = _health_multiplier(scored)
    scored["exchange_risk_multiplier"] = _exchange_risk_multiplier(scored)
    scored["liquidity_risk_multiplier"] = _liquidity_risk_multiplier(scored)
    scored["final_score"] = (
        scored["score"]
        * scored["risk_adjust_factor"]
        * scored["regime_multiplier"]
        * scored["factor_health_score"]
        * scored["exchange_risk_multiplier"]
        * scored["liquidity_risk_multiplier"]
    ).clip(0, 1)
    return scored.sort_values(
        ["final_score", "score", "trend", "growth", "ts_code"],
        ascending=[False, False, False, False, True],
    ).reset_index(drop=True)


def _regime_multiplier(scored: pd.DataFrame, regime_state: str | None) -> pd.Series:
    state = regime_state or "range"
    if state in {"ignored", "full_shadow"}:
        return pd.Series(1.0, index=scored.index, dtype="float64")
    if state == "trend":
        return (0.95 + 0.07 * scored["trend"] + 0.03 * scored["growth"]).clip(0.95, 1.05)
    if state == "crash":
        return (0.80 + 0.20 * scored["risk"]).clip(0.80, 1.00)
    if state == "high_vol":
        return (0.85 + 0.15 * scored["risk"]).clip(0.85, 1.00)
    return (0.94 + 0.04 * scored["industry_strength"] + 0.02 * scored["trend"]).clip(0.94, 1.00)


def _bounded_column(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(0.5, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce").fillna(0.5).clip(0, 1)


def _growth_industry_profile(scored: pd.DataFrame) -> pd.Series:
    if "industry" not in scored.columns:
        return pd.Series(0.45, index=scored.index, dtype="float64")

    industry = scored["industry"].fillna("").astype(str)
    profile = pd.Series(0.45, index=scored.index, dtype="float64")
    profile.loc[_contains_any(industry, LOW_GROWTH_INDUSTRY_KEYWORDS)] = 0.18
    profile.loc[_contains_any(industry, SECONDARY_GROWTH_INDUSTRY_KEYWORDS)] = 0.68
    profile.loc[_contains_any(industry, GROWTH_INDUSTRY_KEYWORDS)] = 0.92
    profile.loc[_financial_industry_mask(scored)] = 0.05
    return profile.clip(0, 1)


def _financial_industry_mask(scored: pd.DataFrame) -> pd.Series:
    if "industry" not in scored.columns:
        return pd.Series(False, index=scored.index)
    return _contains_any(scored["industry"].fillna("").astype(str), FINANCIAL_INDUSTRY_KEYWORDS)


def _contains_any(series: pd.Series, keywords: tuple[str, ...]) -> pd.Series:
    mask = pd.Series(False, index=series.index)
    for keyword in keywords:
        mask = mask | series.str.contains(keyword, case=False, regex=False, na=False)
    return mask


def _health_multiplier(scored: pd.DataFrame) -> pd.Series:
    if "factor_health_score" not in scored.columns:
        return pd.Series(1.0, index=scored.index, dtype="float64")
    health = pd.to_numeric(scored["factor_health_score"], errors="coerce").fillna(1.0)
    return health.clip(0.4, 1.05)


def _exchange_risk_multiplier(scored: pd.DataFrame) -> pd.Series:
    if "exchange" in scored.columns:
        exchange = scored["exchange"].astype(str)
    else:
        exchange = scored["ts_code"].astype(str).str.rsplit(".", n=1).str[-1]

    multiplier = pd.Series(1.0, index=scored.index, dtype="float64")
    multiplier.loc[exchange == "BJ"] = 0.70
    return multiplier


def _liquidity_risk_multiplier(scored: pd.DataFrame) -> pd.Series:
    multiplier = pd.Series(1.0, index=scored.index, dtype="float64")

    if "latest_amount" in scored.columns:
        latest_amount = pd.to_numeric(scored["latest_amount"], errors="coerce")
        multiplier.loc[latest_amount < 100_000] *= 0.90

    if "turnover_rate" in scored.columns:
        turnover_rate = pd.to_numeric(scored["turnover_rate"], errors="coerce")
        multiplier.loc[turnover_rate < 1.0] *= 0.90

    if "observation_count" in scored.columns:
        observations = pd.to_numeric(scored["observation_count"], errors="coerce")
        multiplier.loc[observations < 40] *= 0.85

    if "list_age_days" in scored.columns:
        list_age_days = pd.to_numeric(scored["list_age_days"], errors="coerce")
        multiplier.loc[list_age_days < 180] *= 0.85

    return multiplier.clip(0.50, 1.0)
