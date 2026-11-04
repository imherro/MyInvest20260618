from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

import pandas as pd

from core.alpha_validation_engine import compound_return, max_drawdown, performance_metrics
from core.etf_return_utils import coerce_price_frame, daily_return_series
from core.free_cash_flow_buy_hold_backtest_engine import (
    CHINEXT_TOTAL_RETURN_CODE,
    SHANGHAI_COMPOSITE_CODE,
    _calmar,
    _curve_records,
    _cycle_blocks,
    _shanghai_background,
)
from core.free_cash_flow_chinext_dynamic_backtest_engine import (
    FIXED_EQUAL_WEIGHT_CODE,
    FREE_CASH_FLOW_CHINEXT_DYNAMIC_UNIVERSE,
    _benchmark_equity_column,
    _metrics_from_returns,
)
from core.free_cash_flow_trend_channel_backtest_engine import FREE_CASH_FLOW_PRIMARY_CODE, _benchmark_key


@dataclass(frozen=True)
class FreeCashFlowChinextReversionSpec:
    strategy_id: str = "free-cash-flow-chinext-reversion"
    name: str = "自由现金流R/创业板R相对回归策略"
    short_name: str = "FCF/创业板回归"
    description: str = "在 480092.CNI 自由现金流R指数与 399606.SZ 创业板R全收益指数之间，根据相对净值偏离做反向再平衡，组合始终保持 100% 满仓。"
    method: tuple[str, ...] = (
        "资产池只包含 480092.CNI 国证自由现金流R指数和 399606.SZ 创业板R全收益指数，收益均使用 Tushare index_daily 全收益口径。",
        "构造相对比值 log(自由现金流R净值 / 创业板R净值)，用 500 日滚动均值和波动计算 Z-score。",
        "Z-score 高说明自由现金流相对创业板偏热，反向增配创业板；Z-score 低说明创业板相对偏热，反向增配自由现金流。",
        "组合始终满仓，两个指数权重合计 100%，不持有现金、不加杠杆、不生成真实订单。",
        "每 20 个交易日评估一次；单一指数权重限制在 20% 到 80%；若新旧目标权重差小于 10pct，则不调仓。",
        "若 120 日相关性明显升高，说明两者可能同时受大盘 beta 主导，回归倾斜会自动收缩一半。",
    )
    index_code: str = FREE_CASH_FLOW_PRIMARY_CODE
    benchmark_codes: tuple[str, ...] = (CHINEXT_TOTAL_RETURN_CODE,)
    background_codes: tuple[str, ...] = (SHANGHAI_COMPOSITE_CODE,)
    warmup_calendar_days: int = 900
    backtest_start_date: str = "20100101"
    rebalance_every_sessions: int = 20
    zscore_window: int = 500
    min_zscore_samples: int = 120
    neutral_threshold: float = 0.35
    zscore_scale: float = 1.35
    max_tilt: float = 0.30
    min_weight: float = 0.20
    max_weight: float = 0.80
    rebalance_threshold: float = 0.10
    correlation_window: int = 120
    min_correlation_samples: int = 60
    correlation_risk_threshold: float = 0.65


FREE_CASH_FLOW_CHINEXT_REVERSION_SPEC = FreeCashFlowChinextReversionSpec()


def _round(value: float | None, digits: int = 6) -> float | None:
    if value is None or not math.isfinite(float(value)):
        return None
    return round(float(value), digits)


def _relative_stats(
    frame: pd.DataFrame,
    index: int,
    spec: FreeCashFlowChinextReversionSpec,
) -> dict[str, float | None]:
    start = max(0, index + 1 - spec.zscore_window)
    sample = frame["log_relative_ratio"].iloc[start : index + 1].dropna()
    zscore: float | None = None
    mean: float | None = None
    std: float | None = None
    if len(sample) >= spec.min_zscore_samples:
        mean = float(sample.mean())
        std = float(sample.std())
        if std > 0:
            zscore = (float(frame["log_relative_ratio"].iloc[index]) - mean) / std

    corr_start = max(1, index + 1 - spec.correlation_window)
    corr_sample = frame.iloc[corr_start : index + 1][["fcf_return", "chinext_return"]].dropna()
    correlation: float | None = None
    if len(corr_sample) >= spec.min_correlation_samples:
        corr_value = corr_sample["fcf_return"].corr(corr_sample["chinext_return"])
        if pd.notna(corr_value):
            correlation = float(corr_value)

    return {
        "relative_zscore": zscore,
        "relative_mean": mean,
        "relative_std": std,
        "rolling_correlation": correlation,
    }


def _target_weights(
    frame: pd.DataFrame,
    index: int,
    spec: FreeCashFlowChinextReversionSpec,
) -> dict[str, float | None]:
    stats = _relative_stats(frame, index, spec)
    zscore = stats["relative_zscore"]
    correlation = stats["rolling_correlation"]

    if zscore is None or abs(zscore) < spec.neutral_threshold:
        tilt = 0.0
    else:
        effective_z = math.copysign(abs(zscore) - spec.neutral_threshold, zscore)
        tilt = spec.max_tilt * math.tanh(effective_z / spec.zscore_scale)

    if correlation is not None and correlation >= spec.correlation_risk_threshold:
        tilt *= 0.5

    # zscore > 0 means FCF is rich versus Chinext, so shift weight to Chinext.
    chinext_weight = 0.5 + tilt
    chinext_weight = min(spec.max_weight, max(spec.min_weight, chinext_weight))
    fcf_weight = 1.0 - chinext_weight
    return {
        FREE_CASH_FLOW_PRIMARY_CODE: round(float(fcf_weight), 6),
        CHINEXT_TOTAL_RETURN_CODE: round(float(chinext_weight), 6),
        "relative_zscore": _round(zscore),
        "rolling_correlation": _round(correlation),
        "tilt_to_chinext": round(float(tilt), 6),
    }


def _signal_reason(
    target: dict[str, float | None],
    previous: dict[str, float] | None,
) -> dict[str, str]:
    zscore = target.get("relative_zscore")
    correlation = target.get("rolling_correlation")
    fcf_weight = float(target[FREE_CASH_FLOW_PRIMARY_CODE] or 0.0)
    chinext_weight = float(target[CHINEXT_TOTAL_RETURN_CODE] or 0.0)
    if zscore is None:
        relation = "样本不足，维持中性"
    elif zscore > 0:
        relation = "自由现金流R相对偏热，按回归逻辑增配创业板R"
    elif zscore < 0:
        relation = "创业板R相对偏热，按回归逻辑增配自由现金流R"
    else:
        relation = "相对比值接近均衡，维持中性"
    if previous:
        change = chinext_weight - previous[CHINEXT_TOTAL_RETURN_CODE]
        change_text = f"创业板权重变化 {change:+.1%}"
    else:
        change_text = "初始建仓"
    corr_text = "--" if correlation is None else f"{correlation:.2f}"
    z_text = "--" if zscore is None else f"{zscore:+.2f}"
    return {
        "label": relation,
        "detail": (
            f"{relation}：相对比值 Z-score {z_text}，120日相关性 {corr_text}；"
            f"目标权重 自由现金流R {fcf_weight:.1%} / 创业板R {chinext_weight:.1%}；{change_text}。"
        ),
    }


def run_free_cash_flow_chinext_reversion_backtest(
    spec: FreeCashFlowChinextReversionSpec,
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
    frame["log_relative_ratio"] = (frame["fcf_equity"] / frame["chinext_equity"]).map(math.log)
    frame["fixed_equal_weight_return"] = (frame["fcf_return"] + frame["chinext_return"]) / 2.0
    frame["fixed_equal_weight_equity"] = (1.0 + frame["fixed_equal_weight_return"]).cumprod()
    frame["shanghai_equity"] = _shanghai_background(index_history, primary_dates).to_numpy()

    current_weights = {FREE_CASH_FLOW_PRIMARY_CODE: 0.5, CHINEXT_TOTAL_RETURN_CODE: 0.5}
    strategy_returns: list[float] = []
    fcf_weights: list[float] = []
    chinext_weights: list[float] = []
    turnovers: list[float] = []
    zscores: list[float | None] = []
    correlations: list[float | None] = []
    signals: list[dict[str, object]] = []

    initial_target = {
        FREE_CASH_FLOW_PRIMARY_CODE: 0.5,
        CHINEXT_TOTAL_RETURN_CODE: 0.5,
        "relative_zscore": None,
        "rolling_correlation": None,
        "tilt_to_chinext": 0.0,
    }
    signals.append(
        {
            "date": str(frame["date"].iloc[0]),
            "apply_from_next_session": False,
            "strategy_signal": "fcf_chinext_reversion_init",
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
        stats = _relative_stats(frame, index, spec)
        zscores.append(stats["relative_zscore"])
        correlations.append(stats["rolling_correlation"])
        fcf_weight = current_weights[FREE_CASH_FLOW_PRIMARY_CODE]
        chinext_weight = current_weights[CHINEXT_TOTAL_RETURN_CODE]
        fcf_weights.append(fcf_weight)
        chinext_weights.append(chinext_weight)
        strategy_returns.append(fcf_weight * float(row["fcf_return"]) + chinext_weight * float(row["chinext_return"]))
        turnover = 0.0

        if index > 0 and index % spec.rebalance_every_sessions == 0:
            target = _target_weights(frame, index, spec)
            target_weights = {
                FREE_CASH_FLOW_PRIMARY_CODE: float(target[FREE_CASH_FLOW_PRIMARY_CODE] or 0.0),
                CHINEXT_TOTAL_RETURN_CODE: float(target[CHINEXT_TOTAL_RETURN_CODE] or 0.0),
            }
            turnover = sum(abs(target_weights[code] - current_weights[code]) for code in target_weights)
            if turnover >= spec.rebalance_threshold:
                zscore = target.get("relative_zscore")
                signals.append(
                    {
                        "date": str(row["date"]),
                        "apply_from_next_session": True,
                        "strategy_signal": "fcf_chinext_reversion_rebalance",
                        "target_weights": target_weights,
                        "turnover_to_target": round(float(turnover), 6),
                        "top_candidates": [
                            {
                                "code": FREE_CASH_FLOW_PRIMARY_CODE,
                                "name": "国证自由现金流R指数",
                                "group": "自由现金流R",
                                "score": None if zscore is None else round(float(-zscore), 6),
                                "target_weight": target_weights[FREE_CASH_FLOW_PRIMARY_CODE],
                            },
                            {
                                "code": CHINEXT_TOTAL_RETURN_CODE,
                                "name": "创业板R",
                                "group": "创业板全收益",
                                "score": None if zscore is None else round(float(zscore), 6),
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
    frame["relative_zscore"] = zscores
    frame["rolling_correlation"] = correlations
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
        group="相对回归策略",
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

    latest_stats = _relative_stats(frame, len(frame) - 1, spec)
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
        "latest_relative_zscore": _round(latest_stats["relative_zscore"]),
        "latest_rolling_correlation": _round(latest_stats["rolling_correlation"]),
        "comparison_assets": comparison_assets,
        "metric_comparison_assets": [strategy_metrics, *comparison_assets],
        "latest_signal": signals[-1]["strategy_signal"] if signals else "fcf_chinext_reversion_hold",
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
        "relative_zscore",
        "rolling_correlation",
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
            "indicator": "free_cash_flow_chinext_reversion",
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
            "relative_mean_reversion_signal": True,
            "dynamic_full_investment": True,
            "sum_weights_one": True,
            "alpha_positive_vs_equal_weight": summary["alpha_vs_equal_weight"] > 0,
            "no_lookahead_bias": True,
            "uses_total_return_indices": True,
        },
    }
