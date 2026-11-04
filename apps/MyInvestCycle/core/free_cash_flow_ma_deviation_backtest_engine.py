from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import pandas as pd

from core.alpha_validation_engine import compound_return, max_drawdown, performance_metrics
from core.etf_return_utils import coerce_price_frame, daily_return_series
from core.free_cash_flow_buy_hold_backtest_engine import _calmar
from core.free_cash_flow_trend_channel_backtest_engine import (
    FREE_CASH_FLOW_PRIMARY_CODE,
    FREE_CASH_FLOW_UNIVERSE,
    _benchmark_equity_column,
    _benchmark_key,
    _benchmark_return_column,
    _target_turnover,
    _weights,
)


BEST_FULL_SAMPLE_CODE = "fcf_ma_best_full_sample"


@dataclass(frozen=True)
class FreeCashFlowMaDeviationSpec:
    strategy_id: str = "free-cash-flow-ma-deviation"
    name: str = "自由现金流R均线偏离策略"
    short_name: str = "FCF均线偏离"
    description: str = "只交易 480092.CNI 国证自由现金流R指数，依据价格相对均线的偏离程度在满仓和半仓之间切换。"
    method: tuple[str, ...] = (
        "标的、信号和主基准统一使用 480092.CNI 国证自由现金流R指数，全仓持有 480092.CNI 作为基准。",
        "默认实盘规则为 MA120 和 5% 偏离：收盘低于 MA120 下方 5% 后，下一交易日恢复满仓；收盘高于 MA120 上方 5% 后，下一交易日降到 50%。",
        "价格处于 MA 偏离带内时保持上一仓位；初始仓位为 100%；现金收益暂按 0 处理。",
        "页面同时扫描 MA=60/90/120/150/180/200/250/300 与偏离=3%/5%/7%/10%/12%/15%，按 Calmar、年化收益、最大回撤排序寻找全样本最优。",
        "默认 MA120/5% 策略不使用未来数据；参数扫描为全样本回看筛参，只能用于研究，不能当作已验证实盘参数。",
    )
    index_code: str = FREE_CASH_FLOW_PRIMARY_CODE
    benchmark_codes: tuple[str, ...] = (FREE_CASH_FLOW_PRIMARY_CODE,)
    ma_windows: tuple[int, ...] = (60, 90, 120, 150, 180, 200, 250, 300)
    deviations: tuple[float, ...] = (0.03, 0.05, 0.07, 0.10, 0.12, 0.15)
    default_ma_window: int = 120
    default_deviation: float = 0.05
    high_exposure: float = 1.0
    low_exposure: float = 0.5
    warmup_calendar_days: int = 900
    backtest_start_date: str = "20130101"


FREE_CASH_FLOW_MA_DEVIATION_SPEC = FreeCashFlowMaDeviationSpec()


def _parameter_key(ma_window: int, deviation: float) -> str:
    return f"ma{ma_window}_d{int(round(deviation * 100))}"


def _parameter_label(ma_window: int, deviation: float) -> str:
    return f"MA{ma_window} / ±{deviation:.0%}"


def _variant_return_column(ma_window: int, deviation: float) -> str:
    return f"variant_{_parameter_key(ma_window, deviation)}_return"


def _variant_equity_column(ma_window: int, deviation: float) -> str:
    return f"variant_{_parameter_key(ma_window, deviation)}_equity"


def _variant_exposure_column(ma_window: int, deviation: float) -> str:
    return f"variant_{_parameter_key(ma_window, deviation)}_exposure"


def _variant_turnover_column(ma_window: int, deviation: float) -> str:
    return f"variant_{_parameter_key(ma_window, deviation)}_turnover"


def _signal_name(target_exposure: float, spec: FreeCashFlowMaDeviationSpec) -> str:
    return "fcf_ma_deviation_buy" if target_exposure >= spec.high_exposure else "fcf_ma_deviation_reduce"


def _candidate_list(ma_window: int, deviation: float, target_exposure: float, close_value: float, ma_value: float) -> list[dict[str, object]]:
    deviation_value = close_value / ma_value - 1.0 if ma_value > 0 else 0.0
    return [
        {
            "code": FREE_CASH_FLOW_PRIMARY_CODE,
            "name": "国证自由现金流R指数",
            "group": "自由现金流R",
            "score": round(float(-deviation_value), 6),
            "target_weight": round(float(target_exposure), 6),
            "ma_window": ma_window,
            "deviation_threshold": round(float(deviation), 6),
            "current_deviation": round(float(deviation_value), 6),
        },
        {
            "code": "CASH",
            "name": "现金",
            "group": "现金/空仓",
            "score": round(float(1.0 - target_exposure), 6),
            "target_weight": round(float(1.0 - target_exposure), 6),
        },
    ]


def _simulate_variant(
    close: pd.Series,
    returns: pd.Series,
    *,
    ma_window: int,
    deviation: float,
    spec: FreeCashFlowMaDeviationSpec,
    collect_signals: bool = False,
) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    ma = close.rolling(ma_window, min_periods=ma_window).mean()
    current_exposure = spec.high_exposure
    current_weights = _weights(current_exposure)
    pending_turnover = 0.0
    records: list[dict[str, object]] = []
    signals: list[dict[str, object]] = [
        {
            "date": str(close.index[0]),
            "apply_from_next_session": False,
            "strategy_signal": "fcf_ma_deviation_init",
            "target_weights": _weights(current_exposure),
            "turnover_to_target": 1.0,
            "top_candidates": [],
            "rebalance_reason": {
                "label": "初始满仓",
                "detail": f"{_parameter_label(ma_window, deviation)}：初始按 100% 持有自由现金流R，等待 MA 样本形成。",
            },
        }
    ] if collect_signals else []

    for date_text, close_value in close.items():
        date_text = str(date_text)
        current_return = float(returns.loc[date_text])
        records.append(
            {
                "date": date_text,
                _variant_return_column(ma_window, deviation): current_exposure * current_return,
                _variant_exposure_column(ma_window, deviation): current_exposure,
                _variant_turnover_column(ma_window, deviation): pending_turnover,
            }
        )
        pending_turnover = 0.0

        ma_value = ma.loc[date_text]
        if pd.isna(ma_value) or float(ma_value) <= 0:
            continue
        close_float = float(close_value)
        ma_float = float(ma_value)
        current_deviation = close_float / ma_float - 1.0
        target_exposure = current_exposure
        label = ""
        if current_deviation <= -deviation:
            target_exposure = spec.high_exposure
            label = "低位加仓"
        elif current_deviation >= deviation:
            target_exposure = spec.low_exposure
            label = "高位减仓"

        if abs(target_exposure - current_exposure) < 0.000001:
            continue

        target_weights = _weights(target_exposure)
        turnover = _target_turnover(current_weights, target_weights)
        if collect_signals:
            direction_text = "恢复满仓" if target_exposure >= spec.high_exposure else "降到半仓"
            signals.append(
                {
                    "date": date_text,
                    "apply_from_next_session": True,
                    "strategy_signal": _signal_name(target_exposure, spec),
                    "target_weights": target_weights,
                    "turnover_to_target": turnover,
                    "top_candidates": _candidate_list(ma_window, deviation, target_exposure, close_float, ma_float),
                    "rebalance_reason": {
                        "label": label,
                        "detail": (
                            f"{_parameter_label(ma_window, deviation)}：收盘 {close_float:.2f}，MA{ma_window} {ma_float:.2f}，"
                            f"偏离 {current_deviation:.1%}，触发{label}，下一交易日{direction_text}。"
                        ),
                    },
                }
            )
        current_exposure = target_exposure
        current_weights = target_weights
        pending_turnover = turnover

    return pd.DataFrame(records), signals


def _calmar_from_metrics(metrics: dict[str, object]) -> float | None:
    return _calmar(metrics.get("annualized_return"), metrics.get("max_drawdown"))


def _variant_summary(
    variant_frame: pd.DataFrame,
    *,
    ma_window: int,
    deviation: float,
    benchmark_returns: pd.Series,
    signal_count: int,
) -> dict[str, object]:
    return_column = _variant_return_column(ma_window, deviation)
    exposure_column = _variant_exposure_column(ma_window, deviation)
    turnover_column = _variant_turnover_column(ma_window, deviation)
    aligned_benchmark = pd.Series(
        benchmark_returns.reindex(variant_frame["date"].astype(str)).fillna(0.0).to_numpy()
    )
    metrics = performance_metrics(
        variant_frame[return_column],
        benchmark_returns=aligned_benchmark,
        turnover=variant_frame[turnover_column],
    )
    total = compound_return(variant_frame[return_column])
    return {
        "variant": _parameter_key(ma_window, deviation),
        "ma_window": int(ma_window),
        "deviation": round(float(deviation), 6),
        "label": _parameter_label(ma_window, deviation),
        "equity_key": _variant_equity_column(ma_window, deviation),
        "return_key": return_column,
        "total_return": round(float(total), 6),
        "annualized_return": metrics.get("annualized_return"),
        "max_drawdown": metrics.get("max_drawdown"),
        "sharpe": metrics.get("sharpe"),
        "calmar": _calmar_from_metrics(metrics),
        "rebalance_count": int(signal_count),
        "average_target_exposure": round(float(variant_frame[exposure_column].mean()), 6),
        "cumulative_turnover": metrics.get("cumulative_turnover"),
        "full_sample_optimized": True,
    }


def _best_parameter_key(item: dict[str, object]) -> tuple[float, float, float]:
    calmar = item.get("calmar")
    annualized = item.get("annualized_return")
    drawdown = item.get("max_drawdown")
    return (
        float(calmar) if isinstance(calmar, (int, float)) else float("-inf"),
        float(annualized) if isinstance(annualized, (int, float)) else float("-inf"),
        float(drawdown) if isinstance(drawdown, (int, float)) else float("-inf"),
    )


def _best_annualized_parameter_key(item: dict[str, object]) -> tuple[float, float, float]:
    annualized = item.get("annualized_return")
    calmar = item.get("calmar")
    drawdown = item.get("max_drawdown")
    return (
        float(annualized) if isinstance(annualized, (int, float)) else float("-inf"),
        float(calmar) if isinstance(calmar, (int, float)) else float("-inf"),
        float(drawdown) if isinstance(drawdown, (int, float)) else float("-inf"),
    )


def _metric_row(
    *,
    code: str,
    label: str,
    group: str,
    returns: pd.Series,
    dates: pd.Series,
    equity_key: str | None = None,
    is_strategy: bool = False,
    full_sample_optimized: bool = False,
) -> dict[str, object]:
    clean = pd.Series(returns.fillna(0.0).to_numpy(), index=dates.astype(str).to_numpy())
    metrics = performance_metrics(clean)
    row = {
        "code": code,
        "name": label,
        "group": group,
        "label": label,
        "start_date": str(clean.index.min()) if len(clean) else None,
        "end_date": str(clean.index.max()) if len(clean) else None,
        "sessions": int(len(clean)),
        "total_return": round(float(compound_return(clean)), 6),
        "annualized_return": metrics.get("annualized_return"),
        "max_drawdown": metrics.get("max_drawdown"),
        "sharpe": metrics.get("sharpe"),
        "calmar": _calmar_from_metrics(metrics),
        "full_sample_optimized": full_sample_optimized,
    }
    if equity_key:
        row["equity_key"] = equity_key
    if is_strategy:
        row["isStrategy"] = True
    return row


def _curve_records(frame: pd.DataFrame, columns: list[str]) -> list[dict[str, object]]:
    rows = []
    for _, row in frame[["date", *columns]].iterrows():
        item: dict[str, object] = {"date": str(row["date"])}
        for column in columns:
            value = row.get(column)
            item[column] = None if pd.isna(value) else round(float(value), 6)
        rows.append(item)
    return rows


def _indicator_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    columns = ["date", "index_equity", "ma_equity", "upper_band_equity", "lower_band_equity", "ma_deviation", "target_exposure"]
    rows = []
    for _, row in frame[columns].iterrows():
        item: dict[str, object] = {"date": str(row["date"])}
        for column in columns[1:]:
            value = row.get(column)
            item[column] = None if pd.isna(value) else round(float(value), 6)
        rows.append(item)
    return rows


def run_free_cash_flow_ma_deviation_backtest(
    spec: FreeCashFlowMaDeviationSpec,
    index_history: Mapping[str, pd.DataFrame],
    *,
    start_date: str,
    end_date: str,
    resolved_index_code: str | None = None,
    resolved_index_type: str = "total_return",
) -> dict[str, object]:
    source_code = resolved_index_code or spec.index_code
    if source_code not in index_history:
        raise ValueError(f"missing free cash flow index history: {source_code}")

    prices = coerce_price_frame(index_history[source_code])
    prices = prices[(prices["trade_date"] >= start_date) & (prices["trade_date"] <= end_date)].copy()
    prices = prices.drop_duplicates(subset=["trade_date"], keep="last").sort_values("trade_date")
    if prices.empty:
        raise ValueError("no overlapping free cash flow index dates in backtest window")

    close = prices.set_index("trade_date")["close"].astype(float)
    returns = daily_return_series(prices).reindex(close.index).fillna(0.0)
    frame = pd.DataFrame({"date": close.index.astype(str)})

    variant_summaries: list[dict[str, object]] = []
    variant_frames: dict[str, pd.DataFrame] = {}
    all_signals_by_variant: dict[str, list[dict[str, object]]] = {}
    for ma_window in spec.ma_windows:
        for deviation in spec.deviations:
            is_default = ma_window == spec.default_ma_window and abs(deviation - spec.default_deviation) < 0.000001
            variant_frame, signals = _simulate_variant(
                close,
                returns,
                ma_window=ma_window,
                deviation=deviation,
                spec=spec,
                collect_signals=is_default,
            )
            return_column = _variant_return_column(ma_window, deviation)
            equity_column = _variant_equity_column(ma_window, deviation)
            variant_frame[return_column] = pd.to_numeric(variant_frame[return_column], errors="coerce").fillna(0.0)
            variant_frame[equity_column] = (1.0 + variant_frame[return_column]).cumprod()
            turnover_column = _variant_turnover_column(ma_window, deviation)
            signal_count = len(signals) if is_default else int((variant_frame[turnover_column] > 0).sum())
            summary = _variant_summary(
                variant_frame,
                ma_window=ma_window,
                deviation=deviation,
                benchmark_returns=returns,
                signal_count=signal_count,
            )
            summary["is_default"] = is_default
            summary["full_sample_optimized"] = not is_default
            variant_summaries.append(summary)
            variant_frames[str(summary["variant"])] = variant_frame
            if is_default:
                all_signals_by_variant[str(summary["variant"])] = signals

    default_variant_key = _parameter_key(spec.default_ma_window, spec.default_deviation)
    best_variant = max(variant_summaries, key=_best_parameter_key)
    best_annualized_variant = max(variant_summaries, key=_best_annualized_parameter_key)
    best_variant_key = str(best_variant["variant"])
    default_frame = variant_frames[default_variant_key]
    best_frame = variant_frames[best_variant_key]
    frame = frame.merge(default_frame, on="date", how="left", suffixes=("", "_default"))
    if best_variant_key != default_variant_key:
        best_columns = ["date", str(best_variant["return_key"]), str(best_variant["equity_key"])]
        frame = frame.merge(best_frame[best_columns], on="date", how="left")

    default_return_column = _variant_return_column(spec.default_ma_window, spec.default_deviation)
    default_equity_column = _variant_equity_column(spec.default_ma_window, spec.default_deviation)
    default_exposure_column = _variant_exposure_column(spec.default_ma_window, spec.default_deviation)
    default_turnover_column = _variant_turnover_column(spec.default_ma_window, spec.default_deviation)
    best_return_column = str(best_variant["return_key"])
    best_equity_column = str(best_variant["equity_key"])

    frame["strategy_return"] = frame[default_return_column].fillna(0.0)
    frame["strategy_equity"] = frame[default_equity_column].ffill().fillna(1.0)
    frame["target_exposure"] = frame[default_exposure_column].ffill().fillna(spec.high_exposure)
    frame["turnover"] = frame[default_turnover_column].fillna(0.0)
    frame[_benchmark_return_column(spec.index_code)] = frame["date"].map(returns.to_dict()).fillna(0.0).astype(float)
    frame[_benchmark_equity_column(spec.index_code)] = (1.0 + frame[_benchmark_return_column(spec.index_code)]).cumprod()
    frame["index_equity"] = frame[_benchmark_equity_column(spec.index_code)]

    default_ma = close.rolling(spec.default_ma_window, min_periods=spec.default_ma_window).mean()
    first_close = float(close.dropna().iloc[0])
    frame["close"] = frame["date"].map(close.to_dict()).astype(float)
    frame["ma_value"] = frame["date"].map(default_ma.to_dict()).astype(float)
    frame["ma_equity"] = frame["ma_value"] / first_close
    frame["upper_band_equity"] = frame["ma_value"] * (1.0 + spec.default_deviation) / first_close
    frame["lower_band_equity"] = frame["ma_value"] * (1.0 - spec.default_deviation) / first_close
    frame["ma_deviation"] = frame["close"] / frame["ma_value"] - 1.0

    if best_variant_key == default_variant_key:
        frame["best_full_sample_return"] = frame["strategy_return"]
        frame["best_full_sample_equity"] = frame["strategy_equity"]
    else:
        frame["best_full_sample_return"] = frame[best_return_column].fillna(0.0)
        frame["best_full_sample_equity"] = frame[best_equity_column].ffill().fillna(1.0)

    primary = performance_metrics(
        frame["strategy_return"],
        benchmark_returns=frame[_benchmark_return_column(spec.index_code)],
        turnover=frame["turnover"],
    )
    benchmark_metrics = performance_metrics(frame[_benchmark_return_column(spec.index_code)])
    best_metrics = performance_metrics(
        frame["best_full_sample_return"],
        benchmark_returns=frame[_benchmark_return_column(spec.index_code)],
    )
    strategy_total = compound_return(frame["strategy_return"])
    benchmark_total = compound_return(frame[_benchmark_return_column(spec.index_code)])
    best_total = compound_return(frame["best_full_sample_return"])
    strategy_drawdown = max_drawdown(frame["strategy_equity"])
    benchmark_drawdown = max_drawdown(frame[_benchmark_equity_column(spec.index_code)])
    best_drawdown = max_drawdown(frame["best_full_sample_equity"])

    strategy_row = _metric_row(
        code=spec.strategy_id,
        label=f"{spec.short_name} 默认 MA{spec.default_ma_window}/±{spec.default_deviation:.0%}",
        group="默认规则",
        returns=frame["strategy_return"],
        dates=frame["date"],
        is_strategy=True,
    )
    benchmark_row = _metric_row(
        code=spec.index_code,
        label="自由现金流R满仓 480092.CNI",
        group="全仓基准",
        returns=frame[_benchmark_return_column(spec.index_code)],
        dates=frame["date"],
        equity_key=_benchmark_equity_column(spec.index_code),
    )
    best_row = _metric_row(
        code=BEST_FULL_SAMPLE_CODE,
        label=f"回看Calmar最优 {best_variant['label']}",
        group="全样本筛参",
        returns=frame["best_full_sample_return"],
        dates=frame["date"],
        equity_key="best_full_sample_equity",
        full_sample_optimized=True,
    )
    comparison_assets = []
    for item in (benchmark_row, best_row):
        item = dict(item)
        item["return_advantage"] = (
            None
            if item["total_return"] is None
            else round(float(strategy_row["total_return"]) - float(item["total_return"]), 6)
        )
        item["drawdown_reduction"] = (
            None
            if item["max_drawdown"] is None
            else round(float(strategy_row["max_drawdown"]) - float(item["max_drawdown"]), 6)
        )
        comparison_assets.append(item)

    for item in variant_summaries:
        item["return_advantage_vs_buy_hold"] = round(float(item["total_return"]) - benchmark_total, 6)
        item["drawdown_reduction_vs_buy_hold"] = round(float(item["max_drawdown"]) - benchmark_drawdown, 6)

    parameter_scan = sorted(variant_summaries, key=_best_parameter_key, reverse=True)
    default_variant = next(item for item in variant_summaries if item.get("is_default"))
    signals = all_signals_by_variant.get(default_variant_key, [])
    latest_signal = signals[-1] if signals else {}
    latest_indicator = frame.iloc[-1]
    summary = {
        "strategy_id": spec.strategy_id,
        "strategy_name": spec.name,
        "short_name": f"{spec.short_name} MA{spec.default_ma_window}/±{spec.default_deviation:.0%}",
        "start_date": str(frame["date"].iloc[0]),
        "end_date": str(frame["date"].iloc[-1]),
        "sessions": int(len(frame)),
        "rebalance_count": len(signals),
        "strategy_total_return": round(strategy_total, 6),
        "annualized_return": primary.get("annualized_return"),
        "equal_weight_label": "自由现金流R满仓",
        "equal_weight_return": round(benchmark_total, 6),
        "equal_weight_annualized_return": benchmark_metrics.get("annualized_return"),
        "annualized_alpha_vs_equal_weight": None
        if primary.get("annualized_return") is None or benchmark_metrics.get("annualized_return") is None
        else round(float(primary["annualized_return"]) - float(benchmark_metrics["annualized_return"]), 6),
        "alpha_vs_equal_weight": round(strategy_total - benchmark_total, 6),
        "sharpe": primary.get("sharpe"),
        "calmar": _calmar_from_metrics(primary),
        "max_drawdown": strategy_drawdown,
        "equal_weight_max_drawdown": benchmark_drawdown,
        "hit_rate_vs_primary_benchmark": primary.get("hit_rate"),
        "average_turnover": primary.get("average_turnover"),
        "cumulative_turnover": primary.get("cumulative_turnover"),
        "average_target_exposure": round(float(frame["target_exposure"].mean()), 6),
        "default_parameter": default_variant,
        "best_parameter": best_variant,
        "best_parameter_objective": "Calmar first, then annualized return, then max drawdown",
        "best_annualized_parameter": best_annualized_variant,
        "best_parameter_total_return": round(best_total, 6),
        "best_parameter_annualized_return": best_metrics.get("annualized_return"),
        "best_parameter_max_drawdown": best_drawdown,
        "parameter_scan": parameter_scan,
        "parameter_scan_sorted_by": "Calmar, annualized return, max drawdown",
        "parameter_scan_lookahead_note": "全样本筛参使用完整回测区间选择参数，属于未来函数研究结果，不应直接当作实盘参数。",
        "comparison_assets": comparison_assets,
        "metric_comparison_assets": [strategy_row, *comparison_assets],
        "latest_signal": latest_signal.get("strategy_signal"),
        "latest_signal_date": latest_signal.get("date"),
        "latest_weights": latest_signal.get("target_weights", _weights(float(frame["target_exposure"].iloc[-1]))),
        "latest_ma_deviation": None if pd.isna(latest_indicator.get("ma_deviation")) else round(float(latest_indicator["ma_deviation"]), 6),
        "latest_ma_value": None if pd.isna(latest_indicator.get("ma_value")) else round(float(latest_indicator["ma_value"]), 4),
        "latest_close": round(float(latest_indicator["close"]), 4),
    }
    for item in comparison_assets:
        key = _benchmark_key(str(item["code"]))
        summary[f"benchmark_{key}_return"] = item["total_return"]
        summary[f"benchmark_{key}_max_drawdown"] = item["max_drawdown"]
        summary[f"alpha_vs_{key}"] = item.get("return_advantage")

    curve_columns = [
        "strategy_equity",
        _benchmark_equity_column(spec.index_code),
        "best_full_sample_equity",
        "index_equity",
        "ma_equity",
        "upper_band_equity",
        "lower_band_equity",
        "target_exposure",
        "ma_deviation",
    ]
    return {
        "metadata": {
            "engine": f"{spec.name} Backtest",
            "strategy_id": spec.strategy_id,
            "description": spec.description,
            "method": list(spec.method),
            "universe": [
                {"code": asset.code, "name": asset.name, "group": asset.group, "label": asset.label}
                for asset in FREE_CASH_FLOW_UNIVERSE
            ],
            "index_code": spec.index_code,
            "resolved_index_code": source_code,
            "resolved_index_type": resolved_index_type,
            "benchmark_codes": list(spec.benchmark_codes),
            "indicator": "free_cash_flow_ma_deviation",
            "return_source": "Tushare index_daily for 480092.CNI total-return index series.",
            "signal_timing": "Default MA120/5% signal is generated after close on date t and applied starting t+1.",
            "no_lookahead_bias": True,
            "lookahead_note": "默认 MA120/5% 策略无未来函数；页面包含全样本参数扫描，最优参数属于回看筛参研究结果。",
            "parameter_scan_lookahead": True,
            "evaluation_only": True,
            "no_stock_selection": True,
            "no_trade_execution": True,
            "no_order_generation": True,
            "cash_return_assumption": "Uninvested cash earns 0 in this research version.",
        },
        "summary": summary,
        "performance_metrics": primary,
        "equity_curve": _curve_records(frame, curve_columns),
        "indicator_curve": _indicator_records(frame),
        "signals": signals,
        "validation": {
            "alpha_positive_vs_equal_weight": summary["alpha_vs_equal_weight"] > 0,
            "alpha_positive_vs_primary_benchmark": (primary.get("excess_return") or 0) > 0,
            "ma_deviation_signal": True,
            "default_rule_no_lookahead_bias": True,
            "parameter_scan_has_lookahead_bias": True,
            "uses_total_return_index": resolved_index_type == "total_return",
        },
    }
