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
    _inverse_volatility_weights,
    _metrics_from_returns,
)
from core.free_cash_flow_trend_channel_backtest_engine import FREE_CASH_FLOW_PRIMARY_CODE, _benchmark_key


@dataclass(frozen=True)
class FreeCashFlowChinextBalancedReversionSpec:
    strategy_id: str = "free-cash-flow-chinext-balanced-reversion"
    name: str = "自由现金流R/创业板R平衡回归策略"
    short_name: str = "FCF/创业板平衡回归"
    description: str = "以 50/50 为底仓，先用风险平价修正；相对偏离极端时先做预备回归倾斜，出现反转确认后加大倾斜，组合始终保持 100% 满仓。"
    method: tuple[str, ...] = (
        "资产池只包含 480092.CNI 国证自由现金流R指数和 399606.SZ 创业板R全收益指数，收益均使用 Tushare index_daily 全收益口径。",
        "底仓为 50/50；用 60 日波动率倒数风险平价做 50% 权重混合，基础权重限制在 35%-65%。",
        "构造相对比值 log(自由现金流R净值 / 创业板R净值)，用 500 日滚动均值和波动计算 Z-score。",
        "当 |Z-score| >= 1.0 时先启动预备回归倾斜；若 20 日相对走势已经反向，则切换为满档回归倾斜。",
        "回归方向为反向配置：自由现金流相对偏热时增配创业板；创业板相对偏热时增配自由现金流。",
        "单一指数最终权重限制在 20% 到 80%；若 120 日相关性过高，回归倾斜减半；若新旧目标权重差小于 4pct，则不调仓。",
    )
    index_code: str = FREE_CASH_FLOW_PRIMARY_CODE
    benchmark_codes: tuple[str, ...] = (CHINEXT_TOTAL_RETURN_CODE,)
    background_codes: tuple[str, ...] = (SHANGHAI_COMPOSITE_CODE,)
    warmup_calendar_days: int = 900
    backtest_start_date: str = "20100101"
    rebalance_every_sessions: int = 20
    volatility_window: int = 60
    min_volatility_samples: int = 20
    risk_parity_blend: float = 0.50
    base_min_weight: float = 0.35
    base_max_weight: float = 0.65
    zscore_window: int = 500
    min_zscore_samples: int = 120
    entry_zscore: float = 1.00
    zscore_scale: float = 1.35
    confirmation_window: int = 20
    min_confirmation_move: float = 0.005
    max_preconfirm_tilt: float = 0.12
    max_reversion_tilt: float = 0.32
    min_weight: float = 0.20
    max_weight: float = 0.80
    rebalance_threshold: float = 0.04
    correlation_window: int = 120
    min_correlation_samples: int = 60
    correlation_risk_threshold: float = 0.65


FREE_CASH_FLOW_CHINEXT_BALANCED_REVERSION_SPEC = FreeCashFlowChinextBalancedReversionSpec()


def _round(value: float | None, digits: int = 6) -> float | None:
    if value is None or not math.isfinite(float(value)):
        return None
    return round(float(value), digits)


def _clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def _relative_stats(
    frame: pd.DataFrame,
    index: int,
    spec: FreeCashFlowChinextBalancedReversionSpec,
) -> dict[str, float | None]:
    start = max(0, index + 1 - spec.zscore_window)
    sample = frame["log_relative_ratio"].iloc[start : index + 1].dropna()
    zscore: float | None = None
    if len(sample) >= spec.min_zscore_samples:
        std = float(sample.std())
        if std > 0:
            zscore = (float(frame["log_relative_ratio"].iloc[index]) - float(sample.mean())) / std

    relative_momentum: float | None = None
    if index >= spec.confirmation_window:
        relative_momentum = float(
            frame["log_relative_ratio"].iloc[index] - frame["log_relative_ratio"].iloc[index - spec.confirmation_window]
        )

    corr_start = max(1, index + 1 - spec.correlation_window)
    corr_sample = frame.iloc[corr_start : index + 1][["fcf_return", "chinext_return"]].dropna()
    correlation: float | None = None
    if len(corr_sample) >= spec.min_correlation_samples:
        corr_value = corr_sample["fcf_return"].corr(corr_sample["chinext_return"])
        if pd.notna(corr_value):
            correlation = float(corr_value)

    return {
        "relative_zscore": zscore,
        "relative_momentum": relative_momentum,
        "rolling_correlation": correlation,
    }


def _base_weights(
    frame: pd.DataFrame,
    index: int,
    spec: FreeCashFlowChinextBalancedReversionSpec,
) -> tuple[float, float]:
    rp_fcf, rp_chinext = _inverse_volatility_weights(
        frame,
        index,
        window=spec.volatility_window,
        min_samples=spec.min_volatility_samples,
    )
    fcf_weight = (1.0 - spec.risk_parity_blend) * 0.5 + spec.risk_parity_blend * rp_fcf
    chinext_weight = 1.0 - fcf_weight
    chinext_weight = _clamp(chinext_weight, spec.base_min_weight, spec.base_max_weight)
    fcf_weight = 1.0 - chinext_weight
    return round(float(fcf_weight), 6), round(float(chinext_weight), 6)


def _reversion_tilt(
    stats: dict[str, float | None],
    spec: FreeCashFlowChinextBalancedReversionSpec,
) -> tuple[float, str]:
    zscore = stats["relative_zscore"]
    momentum = stats["relative_momentum"]
    correlation = stats["rolling_correlation"]
    if zscore is None or momentum is None:
        return 0.0, "样本不足，暂不启用回归倾斜"
    if abs(zscore) < spec.entry_zscore:
        return 0.0, "相对偏离未达到极端阈值"

    if zscore > 0:
        direction = 1.0
        confirmed = momentum < -spec.min_confirmation_move
        reason = (
            "自由现金流相对偏热且开始回落，满档回归倾斜增配创业板"
            if confirmed
            else "自由现金流相对偏热但尚未回落确认，预备回归倾斜增配创业板"
        )
    else:
        direction = -1.0
        confirmed = momentum > spec.min_confirmation_move
        reason = (
            "创业板相对偏热且开始回落，满档回归倾斜增配自由现金流"
            if confirmed
            else "创业板相对偏热但尚未回落确认，预备回归倾斜增配自由现金流"
        )

    max_tilt = spec.max_reversion_tilt if confirmed else spec.max_preconfirm_tilt
    magnitude = max_tilt * math.tanh((abs(zscore) - spec.entry_zscore) / spec.zscore_scale)
    if correlation is not None and correlation >= spec.correlation_risk_threshold:
        magnitude *= 0.5
        reason += "；近期相关性偏高，倾斜减半"
    return round(float(direction * magnitude), 6), reason


def _target_weights(
    frame: pd.DataFrame,
    index: int,
    spec: FreeCashFlowChinextBalancedReversionSpec,
) -> dict[str, float | None | str]:
    base_fcf, base_chinext = _base_weights(frame, index, spec)
    stats = _relative_stats(frame, index, spec)
    tilt, reason = _reversion_tilt(stats, spec)
    chinext_weight = _clamp(base_chinext + tilt, spec.min_weight, spec.max_weight)
    fcf_weight = 1.0 - chinext_weight
    return {
        FREE_CASH_FLOW_PRIMARY_CODE: round(float(fcf_weight), 6),
        CHINEXT_TOTAL_RETURN_CODE: round(float(chinext_weight), 6),
        "base_fcf_weight": base_fcf,
        "base_chinext_weight": base_chinext,
        "relative_zscore": _round(stats["relative_zscore"]),
        "relative_momentum": _round(stats["relative_momentum"]),
        "rolling_correlation": _round(stats["rolling_correlation"]),
        "tilt_to_chinext": round(float(tilt), 6),
        "tilt_reason": reason,
    }


def _signal_reason(
    target: dict[str, float | None | str],
    previous: dict[str, float] | None,
) -> dict[str, str]:
    fcf_weight = float(target[FREE_CASH_FLOW_PRIMARY_CODE] or 0.0)
    chinext_weight = float(target[CHINEXT_TOTAL_RETURN_CODE] or 0.0)
    zscore = target.get("relative_zscore")
    momentum = target.get("relative_momentum")
    correlation = target.get("rolling_correlation")
    tilt = float(target.get("tilt_to_chinext") or 0.0)
    if previous:
        change = chinext_weight - previous[CHINEXT_TOTAL_RETURN_CODE]
        change_text = f"创业板权重变化 {change:+.1%}"
    else:
        change_text = "初始建仓"
    z_text = "--" if zscore is None else f"{float(zscore):+.2f}"
    momentum_text = "--" if momentum is None else f"{float(momentum):+.2%}"
    corr_text = "--" if correlation is None else f"{float(correlation):.2f}"
    tilt_text = f"{tilt:+.1%}"
    reason = str(target.get("tilt_reason") or "")
    return {
        "label": reason,
        "detail": (
            f"{reason}：底仓 自由现金流R {float(target['base_fcf_weight'] or 0):.1%} / 创业板R {float(target['base_chinext_weight'] or 0):.1%}，"
            f"回归倾斜 {tilt_text}；Z-score {z_text}，20日相对动量 {momentum_text}，120日相关性 {corr_text}；"
            f"目标权重 自由现金流R {fcf_weight:.1%} / 创业板R {chinext_weight:.1%}；{change_text}。"
        ),
    }


def run_free_cash_flow_chinext_balanced_reversion_backtest(
    spec: FreeCashFlowChinextBalancedReversionSpec,
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
    momentums: list[float | None] = []
    correlations: list[float | None] = []
    signals: list[dict[str, object]] = []

    initial_target = {
        FREE_CASH_FLOW_PRIMARY_CODE: 0.5,
        CHINEXT_TOTAL_RETURN_CODE: 0.5,
        "base_fcf_weight": 0.5,
        "base_chinext_weight": 0.5,
        "relative_zscore": None,
        "relative_momentum": None,
        "rolling_correlation": None,
        "tilt_to_chinext": 0.0,
        "tilt_reason": "初始等权建仓",
    }
    signals.append(
        {
            "date": str(frame["date"].iloc[0]),
            "apply_from_next_session": False,
            "strategy_signal": "fcf_chinext_balanced_reversion_init",
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
        momentums.append(stats["relative_momentum"])
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
                        "strategy_signal": "fcf_chinext_balanced_reversion_rebalance",
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
    frame["relative_momentum"] = momentums
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
        group="平衡回归策略",
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
        "latest_relative_momentum": _round(latest_stats["relative_momentum"]),
        "latest_rolling_correlation": _round(latest_stats["rolling_correlation"]),
        "comparison_assets": comparison_assets,
        "metric_comparison_assets": [strategy_metrics, *comparison_assets],
        "latest_signal": signals[-1]["strategy_signal"] if signals else "fcf_chinext_balanced_reversion_hold",
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
        "relative_momentum",
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
            "indicator": "free_cash_flow_chinext_balanced_reversion",
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
            "balanced_reversion_signal": True,
            "dynamic_full_investment": True,
            "sum_weights_one": True,
            "alpha_positive_vs_equal_weight": summary["alpha_vs_equal_weight"] > 0,
            "no_lookahead_bias": True,
            "uses_total_return_indices": True,
        },
    }
