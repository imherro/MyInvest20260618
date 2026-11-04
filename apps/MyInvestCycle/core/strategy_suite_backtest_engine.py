from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

import pandas as pd

from core.alpha_validation_engine import compound_return, hit_rate, max_drawdown, performance_metrics
from core.etf_return_utils import coerce_price_frame, daily_return_series


RETURN_SOURCE = (
    "Tushare fund_daily ETF quote returns; prefer pct_chg, then close/pre_close, "
    "with close pct_change only as fallback."
)


@dataclass(frozen=True)
class Asset:
    code: str
    name: str
    group: str

    @property
    def label(self) -> str:
        return f"{self.group} {self.code} {self.name}"


@dataclass(frozen=True)
class StrategySpec:
    strategy_id: str
    name: str
    short_name: str
    description: str
    method: list[str]
    universe: tuple[Asset, ...]
    cash_code: str
    benchmark_codes: tuple[str, ...]
    allocator: Callable[[Mapping[str, dict[str, float]]], tuple[dict[str, float], str, list[str]]]


def _asset_map(spec: StrategySpec) -> dict[str, Asset]:
    return {asset.code: asset for asset in spec.universe}


def _benchmark_key(code: str) -> str:
    return code.split(".")[0]


def _benchmark_return_column(code: str) -> str:
    return f"benchmark_{_benchmark_key(code)}_return"


def _benchmark_equity_column(code: str) -> str:
    return f"benchmark_{_benchmark_key(code)}_equity"


def _returns_matrix(price_history: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    returns: dict[str, pd.Series] = {}
    for code, frame in price_history.items():
        prices = coerce_price_frame(frame)
        if prices.empty:
            continue
        returns[code] = daily_return_series(prices)
    if not returns:
        raise ValueError("no ETF price history available for strategy backtest")
    return pd.DataFrame(returns).sort_index()


def _compound_window(series: pd.Series, window: int) -> float | None:
    clean = series.dropna().tail(window)
    if len(clean) < window:
        return None
    return float((1.0 + clean).prod() - 1.0)


def _window_drawdown(series: pd.Series, window: int) -> float | None:
    clean = series.dropna().tail(window)
    if len(clean) < max(8, min(window, 20)):
        return None
    equity = (1.0 + clean).cumprod()
    return float((equity / equity.cummax() - 1.0).min())


def _volatility(series: pd.Series, window: int) -> float | None:
    clean = series.dropna().tail(window)
    if len(clean) < max(8, min(window, 20)):
        return None
    return float(clean.std() * (252 ** 0.5))


def _rank(values: dict[str, float], *, higher_is_better: bool = True) -> dict[str, float]:
    if not values:
        return {}
    ordered = sorted(values.items(), key=lambda item: item[1], reverse=higher_is_better)
    if len(ordered) == 1:
        return {ordered[0][0]: 1.0}
    return {
        code: 1.0 - index / (len(ordered) - 1)
        for index, (code, _) in enumerate(ordered)
    }


def _feature_snapshot(
    returns: pd.DataFrame,
    date_text: str,
    codes: list[str],
    *,
    min_history: int = 120,
) -> dict[str, dict[str, float]]:
    raw: dict[str, dict[str, float]] = {}
    for code in codes:
        if code not in returns:
            continue
        series = returns.loc[:date_text, code].dropna()
        if len(series) < min_history:
            continue
        ret20 = _compound_window(series, 20)
        ret60 = _compound_window(series, 60)
        ret120 = _compound_window(series, 120)
        vol60 = _volatility(series, 60)
        drawdown60 = _window_drawdown(series, 60)
        if None in {ret20, ret60, ret120, vol60, drawdown60}:
            continue
        raw[code] = {
            "return_20": float(ret20),
            "return_60": float(ret60),
            "return_120": float(ret120),
            "volatility_60": float(vol60),
            "max_drawdown_60": float(drawdown60),
        }

    ranks = {
        "return_20": _rank({code: item["return_20"] for code, item in raw.items()}),
        "return_60": _rank({code: item["return_60"] for code, item in raw.items()}),
        "return_120": _rank({code: item["return_120"] for code, item in raw.items()}),
        "volatility_60": _rank({code: item["volatility_60"] for code, item in raw.items()}, higher_is_better=False),
        "max_drawdown_60": _rank({code: item["max_drawdown_60"] for code, item in raw.items()}),
    }
    for code, item in raw.items():
        item["score"] = round(
            0.20 * ranks["return_20"].get(code, 0.0)
            + 0.32 * ranks["return_60"].get(code, 0.0)
            + 0.26 * ranks["return_120"].get(code, 0.0)
            + 0.12 * ranks["volatility_60"].get(code, 0.0)
            + 0.10 * ranks["max_drawdown_60"].get(code, 0.0),
            6,
        )
    return raw


def _normalize_weights(weights: Mapping[str, float]) -> dict[str, float]:
    clean = {str(code): max(0.0, float(weight)) for code, weight in weights.items() if float(weight) > 0}
    total = sum(clean.values())
    if total <= 0:
        return {}
    return {code: round(weight / total, 6) for code, weight in clean.items()}


def _target_turnover(previous: Mapping[str, float], current: Mapping[str, float]) -> float:
    keys = set(previous) | set(current)
    return round(sum(abs(float(current.get(key, 0.0)) - float(previous.get(key, 0.0))) for key in keys) / 2.0, 6)


def _weighted_top(features: Mapping[str, dict[str, float]], eligible: list[str], total_weight: float, cap: float) -> dict[str, float]:
    if not eligible:
        return {}
    positive_scores = {code: max(0.01, float(features[code].get("score", 0.0))) for code in eligible}
    score_sum = sum(positive_scores.values())
    raw = {code: total_weight * score / score_sum for code, score in positive_scores.items()}
    capped: dict[str, float] = {}
    overflow = 0.0
    open_codes: list[str] = []
    for code, weight in raw.items():
        if weight > cap:
            capped[code] = cap
            overflow += weight - cap
        else:
            capped[code] = weight
            open_codes.append(code)
    if overflow > 0 and open_codes:
        open_sum = sum(capped[code] for code in open_codes)
        for code in open_codes:
            capped[code] += overflow * capped[code] / open_sum if open_sum else overflow / len(open_codes)
    return capped


def defensive_dividend_allocator(features: Mapping[str, dict[str, float]]) -> tuple[dict[str, float], str, list[str]]:
    risky = ["510880.SH", "512890.SH"]
    cash = "511880.SH"
    eligible = [
        code for code in risky
        if code in features
        and features[code]["return_60"] > 0
        and features[code]["return_120"] > 0
        and features[code]["max_drawdown_60"] > -0.08
    ]
    ranked = sorted(eligible, key=lambda code: features[code]["score"], reverse=True)
    if not ranked:
        return {cash: 1.0}, "defensive_cash", ["红利/低波资产 60 日动量未通过，全部转入现金代理。"]
    if len(ranked) == 1:
        return {ranked[0]: 0.55, cash: 0.45}, "single_defensive_asset", [
            f"{ranked[0]} 通过动量和回撤门槛，保留 45% 现金缓冲。"
        ]
    weights = _weighted_top(features, ranked[:2], 0.65, 0.40)
    weights[cash] = 1.0 - sum(weights.values())
    return _normalize_weights(weights), "dividend_low_vol_mix", ["两只防守权益 ETF 均通过动量与回撤门槛，现金保留约 35%。"]


def industry_momentum_allocator(features: Mapping[str, dict[str, float]]) -> tuple[dict[str, float], str, list[str]]:
    cash = "511880.SH"
    candidates = [code for code in features if code != cash]
    eligible = [
        code for code in candidates
        if features[code]["return_60"] > 0 and features[code]["return_120"] > 0 and features[code]["return_20"] > -0.04
    ]
    ranked = sorted(eligible, key=lambda code: features[code]["score"], reverse=True)
    if len(ranked) < 2:
        return {cash: 1.0}, "cash_empty_position", ["少于两个行业 ETF 通过 60/120 日动量门槛，触发 511880 空仓机制。"]
    selected = ranked[:3]
    weights = _weighted_top(features, selected, 0.90, 0.45)
    weights[cash] = 1.0 - sum(weights.values())
    return _normalize_weights(weights), "industry_top3_momentum", [
        "选择 60/120 日动量为正且短期未明显转弱的 Top 3 行业 ETF，保留约 10% 现金代理。"
    ]


def four_asset_allocator(features: Mapping[str, dict[str, float]]) -> tuple[dict[str, float], str, list[str]]:
    cash = "511880.SH"
    risk_assets = [code for code in features if code != cash]
    eligible = [
        code for code in risk_assets
        if features[code]["return_60"] > 0 or features[code]["return_120"] > 0
    ]
    ranked = sorted(eligible, key=lambda code: features[code]["score"], reverse=True)
    if not ranked:
        return {cash: 1.0}, "all_assets_cash", ["股、债、金三类资产动量均未通过，全部使用现金代理。"]
    if len(ranked) == 1:
        return {ranked[0]: 0.70, cash: 0.30}, "single_asset_plus_cash", [
            f"{ranked[0]} 是唯一通过趋势门槛的资产，保留 30% 现金。"
        ]
    weights = _weighted_top(features, ranked[:2], 0.90, 0.60)
    weights[cash] = 1.0 - sum(weights.values())
    return _normalize_weights(weights), "top2_four_asset", ["在股、债、金中选择动量风险调整排名前二，保留约 10% 现金。"]


STRATEGY_SPECS: dict[str, StrategySpec] = {
    "defensive-dividend": StrategySpec(
        strategy_id="defensive-dividend",
        name="红利低波 + 现金代理防守策略",
        short_name="红利低波防守",
        description="只在红利、红利低波和现金代理之间切换，目标是降低回撤和保留防守收益。",
        method=[
            "候选资产为 510880 红利ETF、512890 红利低波ETF、511880 银华日利ETF。",
            "每 20 个交易日评估一次 20/60/120 日动量、60 日波动和 60 日回撤。",
            "红利资产未通过 60 日动量和 120 日趋势门槛时，切到 511880 现金代理。",
        ],
        universe=(
            Asset("510880.SH", "红利ETF", "红利"),
            Asset("512890.SH", "红利低波ETF", "低波"),
            Asset("511880.SH", "银华日利ETF", "现金/债券代理"),
        ),
        cash_code="511880.SH",
        benchmark_codes=("510880.SH", "512890.SH", "511880.SH", "510500.SH"),
        allocator=defensive_dividend_allocator,
    ),
    "industry-momentum": StrategySpec(
        strategy_id="industry-momentum",
        name="行业 ETF 动量轮动 + 511880 空仓机制",
        short_name="行业动量轮动",
        description="在主要行业 ETF 中选择中期趋势最强的方向；行业趋势不足时切到 511880。",
        method=[
            "候选覆盖券商、银行、酒、半导体、医疗、军工、光伏、新能源、科技和科创。",
            "每 20 个交易日用 20/60/120 日动量、60 日波动和 60 日回撤打分。",
            "少于两个行业 ETF 通过趋势门槛时触发 511880 空仓机制。",
        ],
        universe=(
            Asset("512000.SH", "券商ETF", "证券"),
            Asset("512800.SH", "银行ETF", "银行"),
            Asset("512690.SH", "酒ETF", "消费"),
            Asset("512480.SH", "半导体ETF", "半导体"),
            Asset("512170.SH", "医疗ETF", "医疗"),
            Asset("512660.SH", "军工ETF", "军工"),
            Asset("515790.SH", "光伏ETF", "光伏"),
            Asset("516160.SH", "新能源ETF", "新能源"),
            Asset("515000.SH", "科技ETF", "科技"),
            Asset("588000.SH", "科创50ETF", "科创"),
            Asset("511880.SH", "银华日利ETF", "现金/债券代理"),
        ),
        cash_code="511880.SH",
        benchmark_codes=("510500.SH", "515000.SH", "588000.SH", "511880.SH"),
        allocator=industry_momentum_allocator,
    ),
    "four-asset": StrategySpec(
        strategy_id="four-asset",
        name="股 / 债 / 金 / 现金四资产轮动",
        short_name="四资产轮动",
        description="在权益、债券、黄金和现金之间做跨资产轮动，用低相关资产改善组合回撤。",
        method=[
            "权益使用 510300 沪深300ETF，债券使用 511010 国债ETF，黄金使用 518880 黄金ETF，现金使用 511880。",
            "每 20 个交易日评估 20/60/120 日动量、60 日波动和 60 日回撤。",
            "股、债、金均无趋势时切到现金；有趋势时选择风险调整排名前二。",
        ],
        universe=(
            Asset("510300.SH", "沪深300ETF", "股票"),
            Asset("511010.SH", "国债ETF", "债券"),
            Asset("518880.SH", "黄金ETF", "黄金"),
            Asset("511880.SH", "银华日利ETF", "现金"),
        ),
        cash_code="511880.SH",
        benchmark_codes=("510300.SH", "511010.SH", "518880.SH", "511880.SH"),
        allocator=four_asset_allocator,
    ),
}


def _top_candidates(features: Mapping[str, dict[str, float]], asset_lookup: Mapping[str, Asset]) -> list[dict[str, object]]:
    rows = []
    for code, item in sorted(features.items(), key=lambda pair: pair[1].get("score", 0.0), reverse=True):
        asset = asset_lookup.get(code)
        rows.append(
            {
                "code": code,
                "name": asset.name if asset else code,
                "group": asset.group if asset else "--",
                "score": round(float(item.get("score", 0.0)), 6),
                "return_20": round(float(item["return_20"]), 6),
                "return_60": round(float(item["return_60"]), 6),
                "return_120": round(float(item["return_120"]), 6),
                "volatility_60": round(float(item["volatility_60"]), 6),
                "max_drawdown_60": round(float(item["max_drawdown_60"]), 6),
            }
        )
    return rows


def _curve_records(frame: pd.DataFrame, spec: StrategySpec) -> list[dict[str, object]]:
    columns = ["date", "strategy_equity", "equal_weight_equity", *[_benchmark_equity_column(code) for code in spec.benchmark_codes]]
    rows = []
    for _, row in frame[columns].iterrows():
        rows.append({key: (str(row[key]) if key == "date" else round(float(row[key]), 6)) for key in columns if key in row})
    return rows


def _return_records(frame: pd.DataFrame, spec: StrategySpec) -> list[dict[str, object]]:
    columns = ["date", "strategy_return", "equal_weight_return", "turnover", *[_benchmark_return_column(code) for code in spec.benchmark_codes]]
    rows = []
    for _, row in frame[columns].iterrows():
        rows.append({key: (str(row[key]) if key == "date" else round(float(row[key]), 8)) for key in columns if key in row})
    return rows


def run_strategy_backtest(
    spec: StrategySpec,
    price_history: Mapping[str, pd.DataFrame],
    *,
    start_date: str,
    end_date: str,
    rebalance_every_sessions: int = 20,
    min_history_sessions: int = 120,
) -> dict[str, object]:
    asset_lookup = _asset_map(spec)
    returns = _returns_matrix(price_history)
    required_codes = [asset.code for asset in spec.universe]
    dates = sorted(date for date in returns.index.astype(str) if start_date <= date <= end_date)
    if not dates:
        raise ValueError("no overlapping dates between ETF returns and backtest window")

    current_weights: dict[str, float] = {}
    pending_turnover = 0.0
    last_rebalance_index = -max(1, rebalance_every_sessions)
    daily_records: list[dict[str, object]] = []
    signal_records: list[dict[str, object]] = []

    for index, date_text in enumerate(dates):
        day_returns = returns.loc[date_text].fillna(0.0)
        available_codes = [code for code in required_codes if code in day_returns.index]
        if current_weights:
            strategy_return = sum(float(weight) * float(day_returns.get(code, 0.0)) for code, weight in current_weights.items())
            record = {
                "date": date_text,
                "strategy_return": strategy_return,
                "equal_weight_return": float(day_returns[available_codes].mean()) if available_codes else 0.0,
                "turnover": pending_turnover,
                "applied_weights": dict(current_weights),
            }
            for code in spec.benchmark_codes:
                record[_benchmark_return_column(code)] = float(day_returns.get(code, 0.0))
            daily_records.append(record)
            pending_turnover = 0.0

        should_rebalance = index - last_rebalance_index >= max(1, rebalance_every_sessions)
        if should_rebalance:
            features = _feature_snapshot(returns, date_text, available_codes, min_history=min_history_sessions)
            if spec.cash_code not in features and spec.cash_code in available_codes:
                cash_series = returns.loc[:date_text, spec.cash_code].dropna()
                if len(cash_series) >= min_history_sessions:
                    features[spec.cash_code] = {
                        "return_20": _compound_window(cash_series, 20) or 0.0,
                        "return_60": _compound_window(cash_series, 60) or 0.0,
                        "return_120": _compound_window(cash_series, 120) or 0.0,
                        "volatility_60": _volatility(cash_series, 60) or 0.0,
                        "max_drawdown_60": _window_drawdown(cash_series, 60) or 0.0,
                        "score": 0.0,
                    }
            if not features:
                continue
            new_weights, signal, drivers = spec.allocator(features)
            if not new_weights:
                continue
            pending_turnover = _target_turnover(current_weights, new_weights)
            current_weights = new_weights
            last_rebalance_index = index
            signal_records.append(
                {
                    "date": date_text,
                    "apply_from_next_session": True,
                    "strategy_signal": signal,
                    "target_weights": dict(current_weights),
                    "turnover_to_target": pending_turnover,
                    "top_candidates": _top_candidates(features, asset_lookup),
                    "rebalance_reason": {
                        "label": signal,
                        "detail": drivers[0] if drivers else signal,
                        "drivers": drivers,
                    },
                }
            )

    frame = pd.DataFrame(daily_records)
    if frame.empty:
        raise ValueError("no backtest returns generated")

    return_columns = ["strategy_return", "equal_weight_return", *[_benchmark_return_column(code) for code in spec.benchmark_codes]]
    for column in return_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
        frame[column.replace("_return", "_equity")] = (1.0 + frame[column]).cumprod()

    primary_benchmark_column = _benchmark_return_column(spec.benchmark_codes[0])
    primary = performance_metrics(frame["strategy_return"], benchmark_returns=frame[primary_benchmark_column], turnover=frame["turnover"])
    strategy_total = compound_return(frame["strategy_return"])
    strategy_drawdown = max_drawdown(frame["strategy_equity"])
    comparison_assets = []
    for code in spec.benchmark_codes:
        return_column = _benchmark_return_column(code)
        equity_column = _benchmark_equity_column(code)
        asset = asset_lookup.get(code)
        benchmark_total = compound_return(frame[return_column])
        benchmark_drawdown = max_drawdown(frame[equity_column])
        comparison_assets.append(
            {
                "code": code,
                "name": asset.name if asset else code,
                "group": asset.group if asset else "基准",
                "label": asset.label if asset else code,
                "total_return": round(benchmark_total, 6),
                "max_drawdown": benchmark_drawdown,
                "return_advantage": round(strategy_total - benchmark_total, 6),
                "drawdown_reduction": round(strategy_drawdown - benchmark_drawdown, 6),
            }
        )
    equal_total = compound_return(frame["equal_weight_return"])
    equal_drawdown = max_drawdown(frame["equal_weight_equity"])
    comparison_assets.append(
        {
            "code": "equal_weight",
            "name": "等权组合",
            "group": "基准",
            "label": "等权组合",
            "total_return": round(equal_total, 6),
            "max_drawdown": equal_drawdown,
            "return_advantage": round(strategy_total - equal_total, 6),
            "drawdown_reduction": round(strategy_drawdown - equal_drawdown, 6),
        }
    )
    latest_signal = signal_records[-1] if signal_records else {}
    summary = {
        "strategy_id": spec.strategy_id,
        "strategy_name": spec.name,
        "short_name": spec.short_name,
        "start_date": str(frame["date"].iloc[0]),
        "end_date": str(frame["date"].iloc[-1]),
        "sessions": int(len(frame)),
        "rebalance_count": len(signal_records),
        "rebalance_every_sessions": max(1, rebalance_every_sessions),
        "strategy_total_return": round(strategy_total, 6),
        "equal_weight_return": round(equal_total, 6),
        "alpha_vs_equal_weight": round(strategy_total - equal_total, 6),
        "sharpe": primary["sharpe"],
        "max_drawdown": strategy_drawdown,
        "equal_weight_max_drawdown": equal_drawdown,
        "hit_rate_vs_primary_benchmark": primary.get("hit_rate"),
        "average_turnover": primary.get("average_turnover"),
        "cumulative_turnover": primary.get("cumulative_turnover"),
        "latest_signal": latest_signal.get("strategy_signal"),
        "latest_signal_date": latest_signal.get("date"),
        "latest_weights": latest_signal.get("target_weights", {}),
        "comparison_assets": comparison_assets,
    }
    for item in comparison_assets:
        if item["code"] == "equal_weight":
            continue
        key = _benchmark_key(str(item["code"]))
        summary[f"benchmark_{key}_return"] = item["total_return"]
        summary[f"benchmark_{key}_max_drawdown"] = item["max_drawdown"]
        summary[f"alpha_vs_{key}"] = item["return_advantage"]

    return {
        "metadata": {
            "engine": f"{spec.name} Backtest",
            "strategy_id": spec.strategy_id,
            "description": spec.description,
            "method": spec.method,
            "universe": [
                {"code": asset.code, "name": asset.name, "group": asset.group, "label": asset.label}
                for asset in spec.universe
            ],
            "cash_code": spec.cash_code,
            "return_source": RETURN_SOURCE,
            "signal_timing": "Signal is generated after close on date t and applied starting t+1.",
            "no_lookahead_bias": True,
            "evaluation_only": True,
            "no_stock_selection": True,
            "no_trade_execution": True,
            "no_order_generation": True,
        },
        "summary": summary,
        "performance_metrics": primary,
        "equity_curve": _curve_records(frame, spec),
        "daily_returns": _return_records(frame, spec),
        "signals": signal_records,
        "validation": {
            "alpha_positive_vs_equal_weight": summary["alpha_vs_equal_weight"] > 0,
            "alpha_positive_vs_primary_benchmark": (primary.get("excess_return") or 0) > 0,
            "stable_signal_count": len(signal_records),
            "effective_start_after_first_signal": summary["start_date"],
        },
    }
