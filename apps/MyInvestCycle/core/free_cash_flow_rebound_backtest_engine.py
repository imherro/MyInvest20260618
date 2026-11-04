from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import pandas as pd

from core.alpha_validation_engine import compound_return, max_drawdown, performance_metrics
from core.etf_return_utils import coerce_price_frame, daily_return_series
from core.free_cash_flow_trend_channel_backtest_engine import (
    CSI500_BENCHMARK_CODE,
    FREE_CASH_FLOW_PRIMARY_CODE,
    _benchmark_equity_column,
    _benchmark_key,
    _benchmark_return_column,
)
from core.strategy_suite_backtest_engine import Asset


@dataclass(frozen=True)
class FreeCashFlowReboundSpec:
    strategy_id: str = "free-cash-flow-drawdown-rebound"
    name: str = "自由现金流回撤反弹策略（五阈值）"
    short_name: str = "自由现金流回撤反弹"
    description: str = "空仓等待国证自由现金流R从阶段高点回撤 n%，满仓后等待从阶段低点反弹 n% 后卖出。"
    method: tuple[str, ...] = (
        "标的、信号和主基准统一使用 480092.CNI 国证自由现金流R指数，并额外对比 000905.SH 中证500指数。",
        "初始为空仓；空仓期间只记录已经发生的最高收盘价，当前价较该高点回撤 n% 后，收盘生成买入信号，下一交易日满仓。",
        "满仓期间只记录已经发生的最低收盘价，当前价较该低点反弹 n% 后，收盘生成卖出信号，下一交易日空仓。",
        "n 同时测试 10%、12%、15%、18%、20% 五个阈值，图上显示五条净值曲线；策略目录默认使用年化收益最高的阈值作为代表结果。",
        "所有判断只使用当日及历史收盘价，不使用未来高低点；现金收益暂按 0 处理，不连接券商、不生成订单。",
    )
    index_code: str = FREE_CASH_FLOW_PRIMARY_CODE
    benchmark_codes: tuple[str, ...] = (FREE_CASH_FLOW_PRIMARY_CODE, CSI500_BENCHMARK_CODE)
    thresholds: tuple[float, ...] = (0.10, 0.12, 0.15, 0.18, 0.20)
    warmup_calendar_days: int = 30
    backtest_start_date: str = "20160101"


FREE_CASH_FLOW_REBOUND_SPEC = FreeCashFlowReboundSpec()
FREE_CASH_FLOW_REBOUND_UNIVERSE = (
    Asset(FREE_CASH_FLOW_PRIMARY_CODE, "国证自由现金流R指数", "自由现金流R"),
    Asset("CASH", "现金", "现金/空仓"),
)


def _threshold_key(threshold: float) -> str:
    return f"n{int(round(threshold * 100))}"


def _variant_return_column(threshold: float) -> str:
    return f"variant_{_threshold_key(threshold)}_return"


def _variant_equity_column(threshold: float) -> str:
    return f"variant_{_threshold_key(threshold)}_equity"


def _threshold_label(threshold: float) -> str:
    return f"n={threshold:.0%}"


def _weights(exposure: float) -> dict[str, float]:
    exposure = max(0.0, min(1.0, float(exposure)))
    result: dict[str, float] = {}
    if exposure > 0.000001:
        result[FREE_CASH_FLOW_PRIMARY_CODE] = round(exposure, 6)
    cash = 1.0 - exposure
    if cash > 0.000001:
        result["CASH"] = round(cash, 6)
    return result


def _target_turnover(previous: Mapping[str, float], current: Mapping[str, float]) -> float:
    keys = set(previous) | set(current)
    return round(sum(abs(float(current.get(key, 0.0)) - float(previous.get(key, 0.0))) for key in keys) / 2.0, 6)


def _candidate_list(threshold: float, exposure: float, reference_close: float | None, trigger_pct: float | None) -> list[dict[str, object]]:
    return [
        {
            "code": FREE_CASH_FLOW_PRIMARY_CODE,
            "name": "国证自由现金流R指数",
            "group": "自由现金流R",
            "score": round(float(threshold), 6),
            "target_weight": round(float(exposure), 6),
            "threshold": round(float(threshold), 6),
            "reference_close": None if reference_close is None else round(float(reference_close), 4),
            "trigger_pct": None if trigger_pct is None else round(float(trigger_pct), 6),
        },
        {
            "code": "CASH",
            "name": "现金",
            "group": "现金/空仓",
            "score": round(float(1.0 - exposure), 6),
            "target_weight": round(float(1.0 - exposure), 6),
        },
    ]


def _simulate_variant(
    close: pd.Series,
    returns: pd.Series,
    *,
    threshold: float,
) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    current_exposure = 0.0
    current_weights = _weights(current_exposure)
    pending_turnover = 0.0
    high_since_exit: float | None = None
    low_since_entry: float | None = None
    records: list[dict[str, object]] = []
    signals: list[dict[str, object]] = []

    for date_text, close_value in close.items():
        # Use exposure decided after the previous close for today's return.
        date_text = str(date_text)
        current_close = float(close_value)
        current_return = float(returns.loc[date_text])
        records.append(
            {
                "date": date_text,
                _variant_return_column(threshold): current_exposure * current_return,
                f"target_exposure_{_threshold_key(threshold)}": current_exposure,
                f"turnover_{_threshold_key(threshold)}": pending_turnover,
            }
        )
        pending_turnover = 0.0

        if current_exposure < 0.5:
            high_since_exit = current_close if high_since_exit is None else max(high_since_exit, current_close)
            drawdown = current_close / high_since_exit - 1.0 if high_since_exit else 0.0
            if drawdown <= -threshold:
                target_exposure = 1.0
                target_weights = _weights(target_exposure)
                turnover = _target_turnover(current_weights, target_weights)
                signals.append(
                    {
                        "date": date_text,
                        "apply_from_next_session": True,
                        "strategy_signal": "fcf_rebound_buy",
                        "variant": _threshold_key(threshold),
                        "threshold": round(float(threshold), 6),
                        "target_weights": dict(target_weights),
                        "turnover_to_target": turnover,
                        "top_candidates": _candidate_list(threshold, target_exposure, high_since_exit, drawdown),
                        "rebalance_reason": {
                            "label": "回撤买入",
                            "detail": f"{_threshold_label(threshold)}：空仓期高点 {high_since_exit:.2f}，当前回撤 {drawdown:.1%}，下一交易日满仓。",
                            "drivers": [
                                f"空仓期最高收盘价 {high_since_exit:.2f}",
                                f"当前回撤 {drawdown:.1%}",
                                f"买入阈值 {-threshold:.1%}",
                            ],
                        },
                    }
                )
                current_exposure = target_exposure
                current_weights = target_weights
                pending_turnover = turnover
                low_since_entry = current_close
        else:
            low_since_entry = current_close if low_since_entry is None else min(low_since_entry, current_close)
            rebound = current_close / low_since_entry - 1.0 if low_since_entry else 0.0
            if rebound >= threshold:
                target_exposure = 0.0
                target_weights = _weights(target_exposure)
                turnover = _target_turnover(current_weights, target_weights)
                signals.append(
                    {
                        "date": date_text,
                        "apply_from_next_session": True,
                        "strategy_signal": "fcf_rebound_sell",
                        "variant": _threshold_key(threshold),
                        "threshold": round(float(threshold), 6),
                        "target_weights": dict(target_weights),
                        "turnover_to_target": turnover,
                        "top_candidates": _candidate_list(threshold, target_exposure, low_since_entry, rebound),
                        "rebalance_reason": {
                            "label": "反弹卖出",
                            "detail": f"{_threshold_label(threshold)}：持仓期低点 {low_since_entry:.2f}，当前反弹 {rebound:.1%}，下一交易日空仓。",
                            "drivers": [
                                f"持仓期最低收盘价 {low_since_entry:.2f}",
                                f"当前反弹 {rebound:.1%}",
                                f"卖出阈值 {threshold:.1%}",
                            ],
                        },
                    }
                )
                current_exposure = target_exposure
                current_weights = target_weights
                pending_turnover = turnover
                high_since_exit = current_close

    return pd.DataFrame(records), signals


def _benchmark_asset(code: str) -> dict[str, str]:
    assets = {
        FREE_CASH_FLOW_PRIMARY_CODE: {
            "name": "国证自由现金流R指数",
            "group": "自由现金流R基准",
            "label": f"国证自由现金流R {FREE_CASH_FLOW_PRIMARY_CODE}",
        },
        CSI500_BENCHMARK_CODE: {
            "name": "中证500指数",
            "group": "宽基对比",
            "label": f"中证500指数 {CSI500_BENCHMARK_CODE}",
        },
    }
    return assets.get(code, {"name": code, "group": "基准对比", "label": code})


def _comparison_assets(frame: pd.DataFrame, strategy_total: float, strategy_drawdown: float, spec: FreeCashFlowReboundSpec) -> list[dict[str, object]]:
    assets = []
    for code in spec.benchmark_codes:
        total_return = compound_return(frame[_benchmark_return_column(code)])
        drawdown = max_drawdown(frame[_benchmark_equity_column(code)])
        asset = _benchmark_asset(code)
        assets.append(
            {
                "code": code,
                "name": asset["name"],
                "group": asset["group"],
                "label": asset["label"],
                "total_return": round(total_return, 6),
                "max_drawdown": drawdown,
                "return_advantage": round(strategy_total - total_return, 6),
                "drawdown_reduction": round(strategy_drawdown - drawdown, 6),
            }
        )
    return assets


def _curve_records(frame: pd.DataFrame, spec: FreeCashFlowReboundSpec) -> list[dict[str, object]]:
    columns = [
        "date",
        "strategy_equity",
        *[_variant_equity_column(threshold) for threshold in spec.thresholds],
        "equal_weight_equity",
        *[_benchmark_equity_column(code) for code in spec.benchmark_codes],
    ]
    rows = []
    for _, row in frame[columns].iterrows():
        rows.append({key: (str(row[key]) if key == "date" else round(float(row[key]), 6)) for key in columns if key in row})
    return rows


def _return_records(frame: pd.DataFrame, spec: FreeCashFlowReboundSpec) -> list[dict[str, object]]:
    columns = [
        "date",
        "strategy_return",
        "equal_weight_return",
        "turnover",
        "target_exposure",
        *[_variant_return_column(threshold) for threshold in spec.thresholds],
        *[_benchmark_return_column(code) for code in spec.benchmark_codes],
    ]
    rows = []
    for _, row in frame[columns].iterrows():
        rows.append({key: (str(row[key]) if key == "date" else round(float(row[key]), 8)) for key in columns if key in row})
    return rows


def run_free_cash_flow_rebound_backtest(
    spec: FreeCashFlowReboundSpec,
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
    all_signals_by_variant: dict[str, list[dict[str, object]]] = {}
    variant_summaries: list[dict[str, object]] = []
    variant_frames: list[pd.DataFrame] = []
    for threshold in spec.thresholds:
        variant_frame, signals = _simulate_variant(close, returns, threshold=threshold)
        variant_key = _threshold_key(threshold)
        return_column = _variant_return_column(threshold)
        equity_column = _variant_equity_column(threshold)
        variant_frame[return_column] = pd.to_numeric(variant_frame[return_column], errors="coerce").fillna(0.0)
        variant_frame[equity_column] = (1.0 + variant_frame[return_column]).cumprod()
        metrics = performance_metrics(
            variant_frame[return_column],
            benchmark_returns=returns.reindex(variant_frame["date"].astype(str)).fillna(0.0),
            turnover=variant_frame[f"turnover_{variant_key}"],
        )
        total_return = compound_return(variant_frame[return_column])
        variant_summaries.append(
            {
                "variant": variant_key,
                "threshold": round(float(threshold), 6),
                "label": _threshold_label(threshold),
                "equity_key": equity_column,
                "return_key": return_column,
                "total_return": round(total_return, 6),
                "annualized_return": metrics.get("annualized_return"),
                "max_drawdown": metrics.get("max_drawdown"),
                "sharpe": metrics.get("sharpe"),
                "rebalance_count": len(signals),
                "average_target_exposure": round(float(variant_frame[f"target_exposure_{variant_key}"].mean()), 6),
                "cumulative_turnover": metrics.get("cumulative_turnover"),
            }
        )
        all_signals_by_variant[variant_key] = signals
        variant_frames.append(variant_frame)

    for variant_frame in variant_frames:
        frame = frame.merge(variant_frame, on="date", how="left")

    benchmark_returns: dict[str, pd.Series] = {spec.index_code: returns}
    for code in spec.benchmark_codes:
        if code == spec.index_code:
            continue
        if code not in index_history:
            raise ValueError(f"missing benchmark index history: {code}")
        benchmark_returns[code] = daily_return_series(index_history[code]).reindex(close.index).fillna(0.0)

    for code, series in benchmark_returns.items():
        column = _benchmark_return_column(code)
        frame[column] = frame["date"].map(series.to_dict()).fillna(0.0).astype(float)
        frame[_benchmark_equity_column(code)] = (1.0 + frame[column]).cumprod()

    frame["equal_weight_return"] = frame[_benchmark_return_column(spec.index_code)]
    frame["equal_weight_equity"] = frame[_benchmark_equity_column(spec.index_code)]

    best_variant = max(
        variant_summaries,
        key=lambda item: (
            item["annualized_return"] if isinstance(item.get("annualized_return"), (int, float)) else float("-inf"),
            item["total_return"],
        ),
    )
    best_return_column = str(best_variant["return_key"])
    best_equity_column = str(best_variant["equity_key"])
    best_variant_key = str(best_variant["variant"])
    frame["strategy_return"] = frame[best_return_column]
    frame["strategy_equity"] = frame[best_equity_column]
    frame["turnover"] = frame[f"turnover_{best_variant_key}"]
    frame["target_exposure"] = frame[f"target_exposure_{best_variant_key}"]

    primary = performance_metrics(frame["strategy_return"], benchmark_returns=frame[_benchmark_return_column(spec.index_code)], turnover=frame["turnover"])
    benchmark_metrics = performance_metrics(frame[_benchmark_return_column(spec.index_code)])
    strategy_total = compound_return(frame["strategy_return"])
    benchmark_total = compound_return(frame[_benchmark_return_column(spec.index_code)])
    strategy_drawdown = max_drawdown(frame["strategy_equity"])
    benchmark_drawdown = max_drawdown(frame[_benchmark_equity_column(spec.index_code)])
    comparison_assets = _comparison_assets(frame, strategy_total, strategy_drawdown, spec)

    for item in variant_summaries:
        item["return_advantage"] = round(strategy_total - float(item["total_return"]), 6)
        item["drawdown_reduction"] = round(strategy_drawdown - float(item["max_drawdown"]), 6)

    signals = all_signals_by_variant.get(best_variant_key, [])
    latest_signal = signals[-1] if signals else {}
    summary = {
        "strategy_id": spec.strategy_id,
        "strategy_name": spec.name,
        "short_name": f"{spec.short_name} {best_variant['label']}",
        "start_date": str(frame["date"].iloc[0]),
        "end_date": str(frame["date"].iloc[-1]),
        "sessions": int(len(frame)),
        "rebalance_count": len(signals),
        "rebalance_every_sessions": 1,
        "strategy_total_return": round(strategy_total, 6),
        "annualized_return": primary.get("annualized_return"),
        "equal_weight_label": "国证自由现金流R基准",
        "equal_weight_return": round(benchmark_total, 6),
        "equal_weight_annualized_return": benchmark_metrics.get("annualized_return"),
        "annualized_alpha_vs_equal_weight": None
        if primary.get("annualized_return") is None or benchmark_metrics.get("annualized_return") is None
        else round(float(primary["annualized_return"]) - float(benchmark_metrics["annualized_return"]), 6),
        "alpha_vs_equal_weight": round(strategy_total - benchmark_total, 6),
        "sharpe": primary.get("sharpe"),
        "max_drawdown": strategy_drawdown,
        "equal_weight_max_drawdown": benchmark_drawdown,
        "hit_rate_vs_primary_benchmark": primary.get("hit_rate"),
        "average_turnover": primary.get("average_turnover"),
        "cumulative_turnover": primary.get("cumulative_turnover"),
        "average_target_exposure": round(float(frame["target_exposure"].mean()), 6),
        "best_variant": best_variant,
        "variants": variant_summaries,
        "variant_assets": [
            {
                "code": item["variant"],
                "label": item["label"],
                "total_return": item["total_return"],
                "annualized_return": item["annualized_return"],
                "max_drawdown": item["max_drawdown"],
                "return_advantage": item["return_advantage"],
                "drawdown_reduction": item["drawdown_reduction"],
            }
            for item in variant_summaries
        ],
        "comparison_assets": comparison_assets,
        "latest_signal": latest_signal.get("strategy_signal"),
        "latest_signal_date": latest_signal.get("date"),
        "latest_weights": latest_signal.get("target_weights", _weights(float(frame["target_exposure"].iloc[-1]))),
    }
    for item in comparison_assets:
        key = _benchmark_key(str(item["code"]))
        summary[f"benchmark_{key}_return"] = item["total_return"]
        summary[f"benchmark_{key}_max_drawdown"] = item["max_drawdown"]
        summary[f"alpha_vs_{key}"] = round(strategy_total - float(item["total_return"]), 6)

    return {
        "metadata": {
            "engine": f"{spec.name} Backtest",
            "strategy_id": spec.strategy_id,
            "description": spec.description,
            "method": list(spec.method),
            "universe": [
                {"code": asset.code, "name": asset.name, "group": asset.group, "label": asset.label}
                for asset in FREE_CASH_FLOW_REBOUND_UNIVERSE
            ],
            "index_code": spec.index_code,
            "resolved_index_code": source_code,
            "resolved_index_type": resolved_index_type,
            "benchmark_codes": list(spec.benchmark_codes),
            "indicator": "free_cash_flow_drawdown_rebound",
            "thresholds": list(spec.thresholds),
            "return_source": "Tushare index_daily for 480092.CNI and 000905.SH.",
            "signal_timing": "Signal is generated after close on date t and applied starting t+1.",
            "no_lookahead_bias": True,
            "evaluation_only": True,
            "no_stock_selection": True,
            "no_trade_execution": True,
            "no_order_generation": True,
            "cash_return_assumption": "Uninvested cash earns 0 in this research version.",
        },
        "summary": summary,
        "performance_metrics": primary,
        "equity_curve": _curve_records(frame, spec),
        "daily_returns": _return_records(frame, spec),
        "signals": signals,
        "variant_signals": all_signals_by_variant,
        "validation": {
            "alpha_positive_vs_equal_weight": summary["alpha_vs_equal_weight"] > 0,
            "alpha_positive_vs_primary_benchmark": (primary.get("excess_return") or 0) > 0,
            "stable_signal_count": len(signals),
            "effective_start_after_first_signal": summary["start_date"],
            "free_cash_flow_drawdown_rebound_signal": True,
            "uses_confirmed_pivots_only": False,
            "no_lookahead_bias": True,
        },
    }
