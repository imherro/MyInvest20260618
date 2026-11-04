from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import pandas as pd

from core.alpha_validation_engine import compound_return, max_drawdown, performance_metrics
from core.etf_return_utils import coerce_price_frame, daily_return_series
from core.strategy_suite_backtest_engine import Asset, RETURN_SOURCE


@dataclass(frozen=True)
class FixedAllocationSpec:
    strategy_id: str
    name: str
    short_name: str
    description: str
    method: list[str]
    universe: tuple[Asset, ...]
    cash_code: str
    target_weights: Mapping[str, float]
    benchmark_codes: tuple[str, ...]
    commodity_codes: tuple[str, ...] = ()


ALL_WEATHER_SPEC = FixedAllocationSpec(
    strategy_id="all-weather",
    name="All Weather Portfolio（A股 ETF 全天候组合）",
    short_name="全天候组合",
    description=(
        "用 A 股上市 ETF 近似经典全天候组合，固定配置股票、长久期国债、"
        "中期国债、黄金和商品期货篮子，并定期再平衡。"
    ),
    method=[
        "股票 30%：510300 沪深300ETF，承担经济增长收益来源。",
        "长久期国债 40%：511260 10年期国债ETF，用于对冲增长下行和通缩环境。",
        "中期国债 15%：511010 5年期国债ETF，补充债券稳定器。",
        "黄金 7.5%：518880 黄金ETF；商品 7.5%：159980 有色期货ETF、159981 能源化工ETF、159985 豆粕ETF 各 2.5%。",
        "不做趋势择时；每 20 个交易日把权重再平衡回固定比例。结果只用于 ETF 级历史模拟，不代表真实交易建议。",
    ],
    universe=(
        Asset("510300.SH", "沪深300ETF", "股票"),
        Asset("511260.SH", "10年期国债ETF", "长久期国债"),
        Asset("511010.SH", "5年期国债ETF", "中期国债"),
        Asset("518880.SH", "黄金ETF", "黄金"),
        Asset("159980.SZ", "有色金属期货ETF", "商品期货"),
        Asset("159981.SZ", "能源化工期货ETF", "商品期货"),
        Asset("159985.SZ", "豆粕期货ETF", "商品期货"),
    ),
    cash_code="511880.SH",
    target_weights={
        "510300.SH": 0.30,
        "511260.SH": 0.40,
        "511010.SH": 0.15,
        "518880.SH": 0.075,
        "159980.SZ": 0.025,
        "159981.SZ": 0.025,
        "159985.SZ": 0.025,
    },
    benchmark_codes=("510300.SH", "511260.SH", "511010.SH", "518880.SH", "511880.SH"),
    commodity_codes=("159980.SZ", "159981.SZ", "159985.SZ"),
)


def _asset_map(spec: FixedAllocationSpec) -> dict[str, Asset]:
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
        raise ValueError("no ETF price history available for fixed allocation backtest")
    return pd.DataFrame(returns).sort_index()


def _target_turnover(previous: Mapping[str, float], current: Mapping[str, float]) -> float:
    keys = set(previous) | set(current)
    return round(sum(abs(float(current.get(key, 0.0)) - float(previous.get(key, 0.0))) for key in keys) / 2.0, 6)


def _normalize_weights(weights: Mapping[str, float]) -> dict[str, float]:
    clean = {code: max(0.0, float(weight)) for code, weight in weights.items() if float(weight) > 0}
    total = sum(clean.values())
    if total <= 0:
        raise ValueError("fixed allocation target weights must be positive")
    return {code: round(weight / total, 6) for code, weight in clean.items()}


def _top_candidates(spec: FixedAllocationSpec) -> list[dict[str, object]]:
    asset_lookup = _asset_map(spec)
    return [
        {
            "code": code,
            "name": asset_lookup.get(code).name if asset_lookup.get(code) else code,
            "group": asset_lookup.get(code).group if asset_lookup.get(code) else "--",
            "score": round(float(weight), 6),
            "target_weight": round(float(weight), 6),
        }
        for code, weight in sorted(spec.target_weights.items(), key=lambda item: item[1], reverse=True)
    ]


def _strategy_record_columns(spec: FixedAllocationSpec) -> list[str]:
    return [
        "date",
        "strategy_equity",
        "equal_weight_equity",
        *[_benchmark_equity_column(code) for code in spec.benchmark_codes],
        "benchmark_commodity_basket_equity",
    ]


def _return_record_columns(spec: FixedAllocationSpec) -> list[str]:
    return [
        "date",
        "strategy_return",
        "equal_weight_return",
        "turnover",
        *[_benchmark_return_column(code) for code in spec.benchmark_codes],
        "benchmark_commodity_basket_return",
    ]


def _curve_records(frame: pd.DataFrame, spec: FixedAllocationSpec) -> list[dict[str, object]]:
    rows = []
    for _, row in frame[_strategy_record_columns(spec)].iterrows():
        rows.append({key: (str(row[key]) if key == "date" else round(float(row[key]), 6)) for key in _strategy_record_columns(spec) if key in row})
    return rows


def _return_records(frame: pd.DataFrame, spec: FixedAllocationSpec) -> list[dict[str, object]]:
    rows = []
    for _, row in frame[_return_record_columns(spec)].iterrows():
        rows.append({key: (str(row[key]) if key == "date" else round(float(row[key]), 8)) for key in _return_record_columns(spec) if key in row})
    return rows


def _comparison_row(
    *,
    code: str,
    name: str,
    group: str,
    label: str,
    returns: pd.Series,
    equity: pd.Series,
    strategy_total: float,
    strategy_drawdown: float,
) -> dict[str, object]:
    benchmark_total = compound_return(returns)
    benchmark_drawdown = max_drawdown(equity)
    return {
        "code": code,
        "name": name,
        "group": group,
        "label": label,
        "total_return": round(benchmark_total, 6),
        "max_drawdown": benchmark_drawdown,
        "return_advantage": round(strategy_total - benchmark_total, 6),
        "drawdown_reduction": round(strategy_drawdown - benchmark_drawdown, 6),
    }


def run_fixed_allocation_backtest(
    price_history: Mapping[str, pd.DataFrame],
    *,
    start_date: str,
    end_date: str,
    rebalance_every_sessions: int = 20,
    spec: FixedAllocationSpec = ALL_WEATHER_SPEC,
) -> dict[str, object]:
    asset_lookup = _asset_map(spec)
    returns = _returns_matrix(price_history)
    target_weights = _normalize_weights(spec.target_weights)
    allocation_codes = list(target_weights)
    missing_codes = [code for code in allocation_codes if code not in returns.columns]
    if missing_codes:
        raise ValueError(f"missing fixed allocation ETF history: {', '.join(missing_codes)}")

    candidate_dates = sorted(date for date in returns.index.astype(str) if start_date <= date <= end_date)
    dates = [
        date_text for date_text in candidate_dates
        if all(pd.notna(returns.loc[date_text, code]) for code in allocation_codes)
    ]
    if not dates:
        raise ValueError("no overlapping dates with complete fixed allocation ETF returns")

    current_weights: dict[str, float] = {}
    pending_turnover = 0.0
    last_rebalance_index = -max(1, rebalance_every_sessions)
    daily_records: list[dict[str, object]] = []
    signal_records: list[dict[str, object]] = []

    for index, date_text in enumerate(dates):
        day_returns = returns.loc[date_text].fillna(0.0)
        if current_weights:
            strategy_return = sum(float(weight) * float(day_returns.get(code, 0.0)) for code, weight in current_weights.items())
            commodity_returns = [float(day_returns.get(code, 0.0)) for code in spec.commodity_codes if code in day_returns.index]
            record = {
                "date": date_text,
                "strategy_return": strategy_return,
                "equal_weight_return": float(day_returns[allocation_codes].mean()),
                "benchmark_commodity_basket_return": sum(commodity_returns) / len(commodity_returns) if commodity_returns else 0.0,
                "turnover": pending_turnover,
                "applied_weights": dict(current_weights),
            }
            for code in spec.benchmark_codes:
                record[_benchmark_return_column(code)] = float(day_returns.get(code, 0.0))
            daily_records.append(record)
            pending_turnover = 0.0
            if strategy_return > -1.0:
                current_weights = {
                    code: float(weight) * (1.0 + float(day_returns.get(code, 0.0))) / (1.0 + strategy_return)
                    for code, weight in current_weights.items()
                }

        should_rebalance = index - last_rebalance_index >= max(1, rebalance_every_sessions)
        if should_rebalance:
            pending_turnover = _target_turnover(current_weights, target_weights)
            current_weights = dict(target_weights)
            last_rebalance_index = index
            signal_records.append(
                {
                    "date": date_text,
                    "apply_from_next_session": True,
                    "strategy_signal": "all_weather_rebalance",
                    "target_weights": dict(current_weights),
                    "turnover_to_target": pending_turnover,
                    "top_candidates": _top_candidates(spec),
                    "rebalance_reason": {
                        "label": "all_weather_rebalance",
                        "detail": "按全天候固定权重再平衡：股票 30%，长久期国债 40%，中期国债 15%，黄金 7.5%，商品期货篮子 7.5%。",
                        "drivers": [
                            "不使用趋势择时或状态预测，只把偏离的资产重新拉回目标权重。",
                            "商品仓位由有色金属、能源化工和豆粕三个 A 股商品期货 ETF 等权组成。",
                        ],
                    },
                }
            )

    frame = pd.DataFrame(daily_records)
    if frame.empty:
        raise ValueError("no fixed allocation backtest returns generated")

    return_columns = [
        "strategy_return",
        "equal_weight_return",
        *[_benchmark_return_column(code) for code in spec.benchmark_codes],
        "benchmark_commodity_basket_return",
    ]
    for column in return_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
        frame[column.replace("_return", "_equity")] = (1.0 + frame[column]).cumprod()

    primary_benchmark_column = _benchmark_return_column(spec.benchmark_codes[0])
    primary = performance_metrics(frame["strategy_return"], benchmark_returns=frame[primary_benchmark_column], turnover=frame["turnover"])
    strategy_total = compound_return(frame["strategy_return"])
    strategy_drawdown = max_drawdown(frame["strategy_equity"])
    equal_total = compound_return(frame["equal_weight_return"])
    equal_drawdown = max_drawdown(frame["equal_weight_equity"])

    comparison_assets = []
    for code in spec.benchmark_codes:
        asset = asset_lookup.get(code)
        if code == spec.cash_code:
            name = "银华日利ETF"
            group = "现金/货币"
            label = f"{group} {code} {name}"
        else:
            name = asset.name if asset else code
            group = asset.group if asset else "基准"
            label = asset.label if asset else code
        comparison_assets.append(
            _comparison_row(
                code=code,
                name=name,
                group=group,
                label=label,
                returns=frame[_benchmark_return_column(code)],
                equity=frame[_benchmark_equity_column(code)],
                strategy_total=strategy_total,
                strategy_drawdown=strategy_drawdown,
            )
        )
    comparison_assets.append(
        _comparison_row(
            code="commodity_basket",
            name="商品期货篮子",
            group="商品期货",
            label="商品期货篮子 159980/159981/159985",
            returns=frame["benchmark_commodity_basket_return"],
            equity=frame["benchmark_commodity_basket_equity"],
            strategy_total=strategy_total,
            strategy_drawdown=strategy_drawdown,
        )
    )
    comparison_assets.append(
        {
            "code": "equal_weight",
            "name": "等权组合",
            "group": "基准",
            "label": "全天候资产等权组合",
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
        key = str(item["code"]).split(".")[0]
        summary[f"benchmark_{key}_return"] = item["total_return"]
        summary[f"benchmark_{key}_max_drawdown"] = item["max_drawdown"]
        summary[f"alpha_vs_{key}"] = item["return_advantage"]

    return {
        "metadata": {
            "engine": "Fixed Allocation ETF Backtest",
            "strategy_id": spec.strategy_id,
            "description": spec.description,
            "method": spec.method,
            "universe": [
                {"code": asset.code, "name": asset.name, "group": asset.group, "label": asset.label}
                for asset in spec.universe
            ],
            "target_weights": dict(target_weights),
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
            "static_allocation": True,
        },
    }
