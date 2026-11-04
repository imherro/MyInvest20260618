from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

import pandas as pd

from core.alpha_validation_engine import annualized_return, compound_return, max_drawdown, performance_metrics
from core.etf_return_utils import coerce_price_frame, daily_return_series
from core.free_cash_flow_buy_hold_backtest_engine import (
    CHINEXT_TOTAL_RETURN_CODE,
    SHANGHAI_COMPOSITE_CODE,
    _asset_metrics,
    _calmar,
    _curve_records,
    _cycle_blocks,
    _shanghai_background,
)
from core.free_cash_flow_trend_channel_backtest_engine import FREE_CASH_FLOW_PRIMARY_CODE, _benchmark_key
from core.strategy_suite_backtest_engine import Asset


FIXED_EQUAL_WEIGHT_CODE = "fcf_chinext_fixed_equal"


@dataclass(frozen=True)
class FreeCashFlowChinextDynamicSpec:
    strategy_id: str = "free-cash-flow-chinext-dynamic"
    name: str = "自由现金流R/创业板R动态满仓策略"
    short_name: str = "FCF/创业板动态"
    description: str = "在 480092.CNI 自由现金流R指数与 399606.SZ 创业板R全收益指数之间动态分配，组合始终保持 100% 满仓。"
    method: tuple[str, ...] = (
        "资产池只包含 480092.CNI 国证自由现金流R指数和 399606.SZ 创业板R全收益指数，收益均使用 Tushare index_daily 全收益口径。",
        "组合始终满仓，两个指数权重合计 100%，不持有现金、不加杠杆、不生成真实订单。",
        "每 20 个交易日评估一次目标权重；基础权重采用 60 日波动率倒数风险平价，样本不足时使用 50/50。",
        "在风险平价基础上叠加趋势强弱倾斜：综合 60/120/250 日动量、MA250 位置和 120 日回撤修复程度。",
        "单一指数权重限制在 20% 到 80%；若新旧目标权重差小于 10pct，则不调仓，以降低来回切换。",
    )
    index_code: str = FREE_CASH_FLOW_PRIMARY_CODE
    benchmark_codes: tuple[str, ...] = (CHINEXT_TOTAL_RETURN_CODE,)
    background_codes: tuple[str, ...] = (SHANGHAI_COMPOSITE_CODE,)
    warmup_calendar_days: int = 900
    backtest_start_date: str = "20100101"
    rebalance_every_sessions: int = 20
    volatility_window: int = 60
    min_volatility_samples: int = 20
    min_weight: float = 0.2
    max_weight: float = 0.8
    max_tilt: float = 0.25
    rebalance_threshold: float = 0.10


FREE_CASH_FLOW_CHINEXT_DYNAMIC_SPEC = FreeCashFlowChinextDynamicSpec()
FREE_CASH_FLOW_CHINEXT_DYNAMIC_UNIVERSE = (
    Asset(FREE_CASH_FLOW_PRIMARY_CODE, "国证自由现金流R指数", "自由现金流R"),
    Asset(CHINEXT_TOTAL_RETURN_CODE, "创业板R", "创业板全收益"),
)


def _round(value: float | None, digits: int = 6) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _benchmark_equity_column(code: str) -> str:
    return f"benchmark_{_benchmark_key(code)}_equity"


def _metrics_from_returns(
    *,
    code: str,
    label: str,
    group: str,
    returns: pd.Series,
    dates: pd.Series | None = None,
    is_strategy: bool = False,
    equity_key: str | None = None,
) -> dict[str, object]:
    if dates is not None:
        returns = pd.Series(returns.to_numpy(), index=dates.astype(str).to_numpy())
    metrics = _asset_metrics(code, returns)
    metrics.update(
        {
            "label": label,
            "group": group,
            "name": label,
        }
    )
    if is_strategy:
        metrics["isStrategy"] = True
    if equity_key:
        metrics["equity_key"] = equity_key
    return metrics


def _safe_momentum(equity: pd.Series, index: int, window: int) -> float:
    if index < window:
        return 0.0
    current = float(equity.iloc[index])
    previous = float(equity.iloc[index - window])
    if previous <= 0:
        return 0.0
    return current / previous - 1.0


def _ma_gap(equity: pd.Series, index: int, window: int = 250) -> float:
    if index + 1 < window:
        return 0.0
    current = float(equity.iloc[index])
    average = float(equity.iloc[index + 1 - window : index + 1].mean())
    if average <= 0:
        return 0.0
    return current / average - 1.0


def _drawdown_repair(equity: pd.Series, index: int, window: int = 120) -> float:
    start = max(0, index + 1 - window)
    current = float(equity.iloc[index])
    peak = float(equity.iloc[start : index + 1].max())
    if peak <= 0:
        return 0.0
    return current / peak - 1.0


def _trend_score(equity: pd.Series, index: int) -> float:
    return (
        0.25 * _safe_momentum(equity, index, 60)
        + 0.35 * _safe_momentum(equity, index, 120)
        + 0.25 * _safe_momentum(equity, index, 250)
        + 0.10 * _ma_gap(equity, index, 250)
        + 0.05 * _drawdown_repair(equity, index, 120)
    )


def _inverse_volatility_weights(
    returns: pd.DataFrame,
    index: int,
    *,
    window: int,
    min_samples: int,
) -> tuple[float, float]:
    if index < min_samples:
        return 0.5, 0.5
    start = max(1, index + 1 - window)
    sample = returns.iloc[start : index + 1][["fcf_return", "chinext_return"]].dropna()
    if len(sample) < min_samples:
        return 0.5, 0.5
    vols = sample.std()
    fcf_vol = float(vols.get("fcf_return") or 0.0)
    chinext_vol = float(vols.get("chinext_return") or 0.0)
    if fcf_vol <= 0 or chinext_vol <= 0:
        return 0.5, 0.5
    fcf_inverse = 1.0 / fcf_vol
    chinext_inverse = 1.0 / chinext_vol
    total = fcf_inverse + chinext_inverse
    return fcf_inverse / total, chinext_inverse / total


def _clamp_weight(value: float, spec: FreeCashFlowChinextDynamicSpec) -> float:
    return min(spec.max_weight, max(spec.min_weight, value))


def _target_weights(frame: pd.DataFrame, index: int, spec: FreeCashFlowChinextDynamicSpec) -> dict[str, float]:
    base_fcf, base_chinext = _inverse_volatility_weights(
        frame,
        index,
        window=spec.volatility_window,
        min_samples=spec.min_volatility_samples,
    )
    fcf_score = _trend_score(frame["fcf_equity"], index)
    chinext_score = _trend_score(frame["chinext_equity"], index)
    tilt = spec.max_tilt * math.tanh((chinext_score - fcf_score) * 3.0)
    chinext_weight = _clamp_weight(base_chinext + tilt, spec)
    fcf_weight = 1.0 - chinext_weight
    return {
        FREE_CASH_FLOW_PRIMARY_CODE: round(float(fcf_weight), 6),
        CHINEXT_TOTAL_RETURN_CODE: round(float(chinext_weight), 6),
        "base_fcf_weight": round(float(base_fcf), 6),
        "base_chinext_weight": round(float(base_chinext), 6),
        "fcf_score": round(float(fcf_score), 6),
        "chinext_score": round(float(chinext_score), 6),
        "tilt_to_chinext": round(float(tilt), 6),
    }


def _signal_reason(target: dict[str, float], previous: dict[str, float] | None) -> dict[str, str]:
    direction = "偏向创业板" if target[CHINEXT_TOTAL_RETURN_CODE] > target[FREE_CASH_FLOW_PRIMARY_CODE] else "偏向自由现金流"
    if previous:
        change = target[CHINEXT_TOTAL_RETURN_CODE] - previous[CHINEXT_TOTAL_RETURN_CODE]
        change_text = f"创业板权重变化 {change:+.1%}"
    else:
        change_text = "初始建仓"
    return {
        "label": direction,
        "detail": (
            f"{direction}：自由现金流R {target[FREE_CASH_FLOW_PRIMARY_CODE]:.1%}，"
            f"创业板R {target[CHINEXT_TOTAL_RETURN_CODE]:.1%}；"
            f"趋势分差 {target['chinext_score'] - target['fcf_score']:+.3f}，"
            f"风险平价基础权重 自由现金流R {target['base_fcf_weight']:.1%} / 创业板R {target['base_chinext_weight']:.1%}；{change_text}。"
        ),
    }


def run_free_cash_flow_chinext_dynamic_backtest(
    spec: FreeCashFlowChinextDynamicSpec,
    index_history: Mapping[str, pd.DataFrame],
    *,
    start_date: str,
    end_date: str,
    resolved_index_code: str | None = None,
    resolved_index_type: str = "total_return",
) -> dict[str, object]:
    source_code = resolved_index_code or spec.index_code
    for code in (source_code, CHINEXT_TOTAL_RETURN_CODE):
        if code not in index_history:
            raise ValueError(f"missing index history: {code}")

    primary_prices = coerce_price_frame(index_history[source_code])
    primary_prices = primary_prices[(primary_prices["trade_date"] >= start_date) & (primary_prices["trade_date"] <= end_date)]
    primary_prices = primary_prices.drop_duplicates("trade_date", keep="last").sort_values("trade_date")
    if primary_prices.empty:
        raise ValueError("no 480092.CNI rows available in backtest window")

    primary_dates = pd.Index(primary_prices["trade_date"].astype(str), name="date")
    fcf_returns = daily_return_series(primary_prices).reindex(primary_dates).fillna(0.0)
    if not fcf_returns.empty:
        fcf_returns.iloc[0] = 0.0

    chinext_prices = coerce_price_frame(index_history[CHINEXT_TOTAL_RETURN_CODE])
    chinext_prices = chinext_prices[(chinext_prices["trade_date"] >= start_date) & (chinext_prices["trade_date"] <= end_date)]
    chinext_prices = chinext_prices.drop_duplicates("trade_date", keep="last").sort_values("trade_date")
    chinext_returns = daily_return_series(chinext_prices).reindex(primary_dates).fillna(0.0)
    if not chinext_returns.empty:
        chinext_returns.iloc[0] = 0.0

    frame = pd.DataFrame(
        {
            "date": primary_dates.astype(str),
            "fcf_return": fcf_returns.to_numpy(),
            "chinext_return": chinext_returns.to_numpy(),
        }
    )
    frame["fcf_equity"] = (1.0 + frame["fcf_return"]).cumprod()
    frame["chinext_equity"] = (1.0 + frame["chinext_return"]).cumprod()
    frame["fixed_equal_weight_return"] = (frame["fcf_return"] + frame["chinext_return"]) / 2.0
    frame["fixed_equal_weight_equity"] = (1.0 + frame["fixed_equal_weight_return"]).cumprod()
    frame["shanghai_equity"] = _shanghai_background(index_history, primary_dates).to_numpy()

    current_weights = {FREE_CASH_FLOW_PRIMARY_CODE: 0.5, CHINEXT_TOTAL_RETURN_CODE: 0.5}
    strategy_returns: list[float] = []
    fcf_weights: list[float] = []
    chinext_weights: list[float] = []
    turnovers: list[float] = []
    signals: list[dict[str, object]] = []

    initial_target = {
        FREE_CASH_FLOW_PRIMARY_CODE: 0.5,
        CHINEXT_TOTAL_RETURN_CODE: 0.5,
        "base_fcf_weight": 0.5,
        "base_chinext_weight": 0.5,
        "fcf_score": 0.0,
        "chinext_score": 0.0,
        "tilt_to_chinext": 0.0,
    }
    signals.append(
        {
            "date": str(frame["date"].iloc[0]),
            "apply_from_next_session": False,
            "strategy_signal": "fcf_chinext_dynamic_init",
            "target_weights": {
                FREE_CASH_FLOW_PRIMARY_CODE: 0.5,
                CHINEXT_TOTAL_RETURN_CODE: 0.5,
            },
            "turnover_to_target": 1.0,
            "top_candidates": [],
            "rebalance_reason": _signal_reason(initial_target, None),
        }
    )

    for index, row in frame.iterrows():
        fcf_weight = current_weights[FREE_CASH_FLOW_PRIMARY_CODE]
        chinext_weight = current_weights[CHINEXT_TOTAL_RETURN_CODE]
        fcf_weights.append(fcf_weight)
        chinext_weights.append(chinext_weight)
        strategy_returns.append(fcf_weight * float(row["fcf_return"]) + chinext_weight * float(row["chinext_return"]))
        turnover = 0.0

        if index > 0 and index % spec.rebalance_every_sessions == 0:
            target = _target_weights(frame, index, spec)
            target_weights = {
                FREE_CASH_FLOW_PRIMARY_CODE: target[FREE_CASH_FLOW_PRIMARY_CODE],
                CHINEXT_TOTAL_RETURN_CODE: target[CHINEXT_TOTAL_RETURN_CODE],
            }
            turnover = sum(abs(target_weights[code] - current_weights[code]) for code in target_weights)
            if turnover >= spec.rebalance_threshold:
                signals.append(
                    {
                        "date": str(row["date"]),
                        "apply_from_next_session": True,
                        "strategy_signal": "fcf_chinext_dynamic_rebalance",
                        "target_weights": target_weights,
                        "turnover_to_target": round(float(turnover), 6),
                        "top_candidates": [
                            {
                                "code": FREE_CASH_FLOW_PRIMARY_CODE,
                                "name": "国证自由现金流R指数",
                                "group": "自由现金流R",
                                "score": target["fcf_score"],
                                "target_weight": target_weights[FREE_CASH_FLOW_PRIMARY_CODE],
                            },
                            {
                                "code": CHINEXT_TOTAL_RETURN_CODE,
                                "name": "创业板R",
                                "group": "创业板全收益",
                                "score": target["chinext_score"],
                                "target_weight": target_weights[CHINEXT_TOTAL_RETURN_CODE],
                            },
                        ],
                        "rebalance_reason": _signal_reason(target, current_weights),
                    }
                )
                current_weights = target_weights
        turnovers.append(turnover)

    frame["strategy_return"] = strategy_returns
    frame["strategy_equity"] = (1.0 + frame["strategy_return"]).cumprod()
    frame["target_fcf_weight"] = fcf_weights
    frame["target_chinext_weight"] = chinext_weights
    frame["turnover"] = turnovers
    frame[_benchmark_equity_column(FREE_CASH_FLOW_PRIMARY_CODE)] = frame["fcf_equity"]
    frame[_benchmark_equity_column(CHINEXT_TOTAL_RETURN_CODE)] = frame["chinext_equity"]

    primary = performance_metrics(frame["strategy_return"], turnover=frame["turnover"])
    strategy_total = compound_return(frame["strategy_return"])
    strategy_drawdown = max_drawdown(frame["strategy_equity"])
    fixed_total = compound_return(frame["fixed_equal_weight_return"])
    fixed_drawdown = max_drawdown(frame["fixed_equal_weight_equity"])

    strategy_metrics = _metrics_from_returns(
        code=spec.strategy_id,
        label=spec.short_name,
        group="动态满仓策略",
        returns=frame["strategy_return"],
        dates=frame["date"],
        is_strategy=True,
    )
    fixed_metrics = _metrics_from_returns(
        code=FIXED_EQUAL_WEIGHT_CODE,
        label="50/50 固定等权",
        group="固定等权基准",
        returns=frame["fixed_equal_weight_return"],
        dates=frame["date"],
        equity_key="fixed_equal_weight_equity",
    )
    fcf_metrics = _metrics_from_returns(
        code=FREE_CASH_FLOW_PRIMARY_CODE,
        label="自由现金流R 480092.CNI",
        group="自由现金流R",
        returns=frame["fcf_return"],
        dates=frame["date"],
        equity_key=_benchmark_equity_column(FREE_CASH_FLOW_PRIMARY_CODE),
    )
    chinext_metrics = _metrics_from_returns(
        code=CHINEXT_TOTAL_RETURN_CODE,
        label="创业板全收益 399606.SZ",
        group="创业板全收益",
        returns=frame["chinext_return"],
        dates=frame["date"],
        equity_key=_benchmark_equity_column(CHINEXT_TOTAL_RETURN_CODE),
    )

    comparison_assets = []
    for item in (fixed_metrics, fcf_metrics, chinext_metrics):
        item = dict(item)
        item["return_advantage"] = (
            None
            if item["total_return"] is None
            else round(float(strategy_metrics["total_return"]) - float(item["total_return"]), 6)
        )
        item["drawdown_reduction"] = (
            None
            if item["max_drawdown"] is None
            else round(float(strategy_metrics["max_drawdown"]) - float(item["max_drawdown"]), 6)
        )
        comparison_assets.append(item)

    latest_weights = signals[-1]["target_weights"] if signals else current_weights
    summary = {
        "strategy_id": spec.strategy_id,
        "strategy_name": spec.name,
        "short_name": spec.short_name,
        "start_date": str(frame["date"].iloc[0]),
        "end_date": str(frame["date"].iloc[-1]),
        "sessions": int(len(frame)),
        "rebalance_count": int(len(signals)),
        "strategy_total_return": round(strategy_total, 6),
        "annualized_return": primary.get("annualized_return"),
        "equal_weight_label": "50/50 固定等权",
        "equal_weight_return": round(fixed_total, 6),
        "alpha_vs_equal_weight": round(strategy_total - fixed_total, 6),
        "sharpe": primary.get("sharpe"),
        "calmar": _calmar(primary.get("annualized_return"), strategy_drawdown),
        "max_drawdown": strategy_drawdown,
        "equal_weight_max_drawdown": fixed_drawdown,
        "hit_rate_vs_primary_benchmark": None,
        "average_turnover": primary.get("average_turnover"),
        "cumulative_turnover": primary.get("cumulative_turnover"),
        "average_fcf_weight": _round(float(frame["target_fcf_weight"].mean())),
        "average_chinext_weight": _round(float(frame["target_chinext_weight"].mean())),
        "comparison_assets": comparison_assets,
        "metric_comparison_assets": [strategy_metrics, *comparison_assets],
        "latest_signal": signals[-1]["strategy_signal"] if signals else "fcf_chinext_dynamic_hold",
        "latest_signal_date": signals[-1]["date"] if signals else str(frame["date"].iloc[-1]),
        "latest_weights": latest_weights,
    }
    for item in comparison_assets:
        key = _benchmark_key(str(item["code"]))
        summary[f"benchmark_{key}_return"] = item["total_return"]
        summary[f"benchmark_{key}_max_drawdown"] = item["max_drawdown"]
        summary[f"alpha_vs_{key}"] = item.get("return_advantage")

    curve_columns = [
        "strategy_equity",
        "shanghai_equity",
        _benchmark_equity_column(FREE_CASH_FLOW_PRIMARY_CODE),
        _benchmark_equity_column(CHINEXT_TOTAL_RETURN_CODE),
        "fixed_equal_weight_equity",
        "target_fcf_weight",
        "target_chinext_weight",
    ]
    return {
        "metadata": {
            "engine": f"{spec.name} Backtest",
            "strategy_id": spec.strategy_id,
            "description": spec.description,
            "method": list(spec.method),
            "universe": [
                {"code": asset.code, "name": asset.name, "group": asset.group, "label": asset.label}
                for asset in FREE_CASH_FLOW_CHINEXT_DYNAMIC_UNIVERSE
            ],
            "index_code": spec.index_code,
            "resolved_index_code": source_code,
            "resolved_index_type": resolved_index_type,
            "benchmark_codes": list(spec.benchmark_codes),
            "background_codes": list(spec.background_codes),
            "indicator": "free_cash_flow_chinext_dynamic",
            "return_source": "Tushare index_daily total-return index series where available.",
            "signal_timing": "Signals are computed after close and applied from the next session.",
            "no_lookahead_bias": True,
            "evaluation_only": True,
            "no_stock_selection": True,
            "no_trade_execution": True,
            "no_order_generation": True,
        },
        "summary": summary,
        "performance_metrics": primary,
        "equity_curve": _curve_records(frame, curve_columns),
        "signals": signals,
        "cycle_blocks": _cycle_blocks(index_history),
        "validation": {
            "dynamic_full_investment": True,
            "sum_weights_one": True,
            "alpha_positive_vs_equal_weight": summary["alpha_vs_equal_weight"] > 0,
            "no_lookahead_bias": True,
            "uses_total_return_indices": True,
        },
    }
