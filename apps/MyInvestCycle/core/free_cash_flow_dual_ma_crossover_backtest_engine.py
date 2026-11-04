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


BEST_FULL_SAMPLE_CODE = "fcf_dual_ma_best_full_sample"
DRAWDOWN20_MA_RULE_CODE = "fcf_peak_drawdown10_clear_20_full"
DRAWDOWN20_MA_RULE_EQUITY = "drawdown20_ma_equity"
DRAWDOWN20_MA_RULE_RETURN = "drawdown20_ma_return"
DRAWDOWN20_MA_RULE_EXPOSURE = "drawdown20_ma_exposure"
DRAWDOWN20_MA_RULE_TURNOVER = "drawdown20_ma_turnover"


@dataclass(frozen=True)
class FreeCashFlowDualMaCrossoverSpec:
    strategy_id: str = "free-cash-flow-dual-ma-crossover"
    name: str = "自由现金流R双均线金叉死叉策略"
    short_name: str = "FCF双均线"
    description: str = "只交易 480092.CNI 国证自由现金流R指数，按快慢均线金叉满仓、死叉空仓。"
    method: tuple[str, ...] = (
        "标的、信号和主基准统一使用 480092.CNI 国证自由现金流R指数，全仓持有 480092.CNI 作为基准。",
        "默认研究规则为 MA30 / MA90：快线上穿慢线后，下一交易日恢复 100% 仓位；快线下穿慢线后，下一交易日降到 0%。",
        "均线样本不足时维持初始 100% 仓位；信号按收盘后计算，下一交易日生效；空仓现金收益暂按 0 处理。",
        "页面同时扫描快线=10/20/30/40/60/90/120 与慢线=90/120/150/180/200/250/300，且只保留快线小于慢线的组合。",
        "额外测试规则：初始满仓，跟踪已发生最高收盘价；满仓时从高点回撤达到 10% 后下一交易日清仓，空仓后若继续回撤达到 20% 后下一交易日恢复满仓；深跌买回后，需先收复到 10% 回撤以内才重新触发下一次 10% 清仓。",
        "默认 MA30/MA90 信号本身不使用未来价格；但该默认参数来自全样本筛参观察，只能用于研究，不能当作已验证实盘参数。",
    )
    index_code: str = FREE_CASH_FLOW_PRIMARY_CODE
    benchmark_codes: tuple[str, ...] = (FREE_CASH_FLOW_PRIMARY_CODE,)
    fast_windows: tuple[int, ...] = (10, 20, 30, 40, 60, 90, 120)
    slow_windows: tuple[int, ...] = (90, 120, 150, 180, 200, 250, 300)
    default_fast_window: int = 30
    default_slow_window: int = 90
    high_exposure: float = 1.0
    low_exposure: float = 0.0
    warmup_calendar_days: int = 1400
    backtest_start_date: str = "20130101"
    validation_split_date: str = "20210101"


FREE_CASH_FLOW_DUAL_MA_CROSSOVER_SPEC = FreeCashFlowDualMaCrossoverSpec()


def _parameter_key(fast_window: int, slow_window: int) -> str:
    return f"ma{fast_window}_{slow_window}"


def _parameter_label(fast_window: int, slow_window: int) -> str:
    return f"MA{fast_window} / MA{slow_window}"


def _variant_return_column(fast_window: int, slow_window: int) -> str:
    return f"variant_{_parameter_key(fast_window, slow_window)}_return"


def _variant_equity_column(fast_window: int, slow_window: int) -> str:
    return f"variant_{_parameter_key(fast_window, slow_window)}_equity"


def _variant_exposure_column(fast_window: int, slow_window: int) -> str:
    return f"variant_{_parameter_key(fast_window, slow_window)}_exposure"


def _variant_turnover_column(fast_window: int, slow_window: int) -> str:
    return f"variant_{_parameter_key(fast_window, slow_window)}_turnover"


def _signal_name(target_exposure: float, spec: FreeCashFlowDualMaCrossoverSpec) -> str:
    return "fcf_dual_ma_golden_cross_buy" if target_exposure >= spec.high_exposure else "fcf_dual_ma_death_cross_sell"


def _candidate_list(
    fast_window: int,
    slow_window: int,
    target_exposure: float,
    close_value: float,
    fast_ma: float,
    slow_ma: float,
) -> list[dict[str, object]]:
    spread = fast_ma / slow_ma - 1.0 if slow_ma > 0 else 0.0
    return [
        {
            "code": FREE_CASH_FLOW_PRIMARY_CODE,
            "name": "国证自由现金流R指数",
            "group": "自由现金流R",
            "score": round(float(spread), 6),
            "target_weight": round(float(target_exposure), 6),
            "fast_window": fast_window,
            "slow_window": slow_window,
            "close": round(float(close_value), 4),
            "fast_ma": round(float(fast_ma), 4),
            "slow_ma": round(float(slow_ma), 4),
            "ma_spread": round(float(spread), 6),
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
    fast_window: int,
    slow_window: int,
    spec: FreeCashFlowDualMaCrossoverSpec,
    collect_signals: bool = False,
) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    fast_ma = close.rolling(fast_window, min_periods=fast_window).mean()
    slow_ma = close.rolling(slow_window, min_periods=slow_window).mean()
    spread = fast_ma / slow_ma - 1.0
    current_exposure = spec.high_exposure
    current_weights = _weights(current_exposure)
    pending_turnover = 0.0
    previous_spread: float | None = None
    records: list[dict[str, object]] = []
    signals: list[dict[str, object]] = [
        {
            "date": str(close.index[0]),
            "apply_from_next_session": False,
            "strategy_signal": "fcf_dual_ma_init",
            "target_weights": _weights(current_exposure),
            "turnover_to_target": 1.0,
            "top_candidates": [],
            "rebalance_reason": {
                "label": "初始满仓",
                "detail": f"{_parameter_label(fast_window, slow_window)}：初始按 100% 持有自由现金流R，等待慢均线样本形成。",
            },
        }
    ] if collect_signals else []

    for date_text, close_value in close.items():
        date_text = str(date_text)
        current_return = float(returns.loc[date_text])
        records.append(
            {
                "date": date_text,
                _variant_return_column(fast_window, slow_window): current_exposure * current_return,
                _variant_exposure_column(fast_window, slow_window): current_exposure,
                _variant_turnover_column(fast_window, slow_window): pending_turnover,
            }
        )
        pending_turnover = 0.0

        current_spread_value = spread.loc[date_text]
        if pd.isna(current_spread_value):
            continue
        current_spread = float(current_spread_value)
        close_float = float(close_value)
        fast_value = float(fast_ma.loc[date_text])
        slow_value = float(slow_ma.loc[date_text])
        target_exposure = current_exposure
        label = ""

        if previous_spread is None:
            target_exposure = spec.high_exposure if current_spread >= 0 else spec.low_exposure
            label = "首次均线状态确认"
        elif previous_spread <= 0 < current_spread:
            target_exposure = spec.high_exposure
            label = "金叉买入"
        elif previous_spread >= 0 > current_spread:
            target_exposure = spec.low_exposure
            label = "死叉卖出"
        previous_spread = current_spread

        if abs(target_exposure - current_exposure) < 0.000001:
            continue

        target_weights = _weights(target_exposure)
        turnover = _target_turnover(current_weights, target_weights)
        if collect_signals:
            direction_text = "恢复满仓" if target_exposure >= spec.high_exposure else "降为空仓"
            signals.append(
                {
                    "date": date_text,
                    "apply_from_next_session": True,
                    "strategy_signal": _signal_name(target_exposure, spec),
                    "target_weights": target_weights,
                    "turnover_to_target": turnover,
                    "top_candidates": _candidate_list(
                        fast_window,
                        slow_window,
                        target_exposure,
                        close_float,
                        fast_value,
                        slow_value,
                    ),
                    "rebalance_reason": {
                        "label": label,
                        "detail": (
                            f"{_parameter_label(fast_window, slow_window)}：收盘 {close_float:.2f}，"
                            f"快线 {fast_value:.2f}，慢线 {slow_value:.2f}，快慢线差 {current_spread:.2%}，"
                            f"触发{label}，下一交易日{direction_text}。"
                        ),
                    },
                }
            )
        current_exposure = target_exposure
        current_weights = target_weights
        pending_turnover = turnover

    return pd.DataFrame(records), signals


def _simulate_drawdown20_ma_rule(
    close: pd.Series,
    returns: pd.Series,
    *,
    sell_drawdown_threshold: float = 0.10,
    buy_drawdown_threshold: float = 0.20,
) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    current_exposure = 1.0
    current_weights = _weights(current_exposure)
    pending_turnover = 0.0
    running_high: float | None = None
    sell_armed = True
    records: list[dict[str, object]] = []
    signals: list[dict[str, object]] = [
        {
            "date": str(close.index[0]),
            "apply_from_next_session": False,
            "strategy_signal": "fcf_peak_drawdown_init",
            "variant": "peak_drawdown10_clear_20_full",
            "target_weights": _weights(current_exposure),
            "turnover_to_target": 1.0,
            "top_candidates": [],
            "rebalance_reason": {
                "label": "初始满仓",
                "detail": "初始按 100% 持有自由现金流R，跟踪历史最高收盘价与回撤阈值。",
            },
        }
    ]

    for date_text, close_value in close.items():
        date_text = str(date_text)
        close_float = float(close_value)
        running_high = close_float if running_high is None else max(running_high, close_float)
        drawdown = close_float / running_high - 1.0 if running_high else 0.0
        current_return = float(returns.loc[date_text])
        records.append(
            {
                "date": date_text,
                DRAWDOWN20_MA_RULE_RETURN: current_exposure * current_return,
                DRAWDOWN20_MA_RULE_EXPOSURE: current_exposure,
                DRAWDOWN20_MA_RULE_TURNOVER: pending_turnover,
            }
        )
        pending_turnover = 0.0

        if drawdown > -sell_drawdown_threshold:
            sell_armed = True

        if current_exposure >= 0.5:
            if sell_armed and drawdown <= -sell_drawdown_threshold:
                target_exposure = 0.0
                target_weights = _weights(target_exposure)
                turnover = _target_turnover(current_weights, target_weights)
                signals.append(
                    {
                        "date": date_text,
                        "apply_from_next_session": True,
                        "strategy_signal": "fcf_peak_drawdown10_clear",
                        "variant": "peak_drawdown10_clear_20_full",
                        "target_weights": target_weights,
                        "turnover_to_target": turnover,
                        "top_candidates": [
                            {
                                "code": FREE_CASH_FLOW_PRIMARY_CODE,
                                "name": "国证自由现金流R指数",
                                "group": "自由现金流R",
                                "score": round(float(-drawdown), 6),
                                "target_weight": 0.0,
                                "sell_drawdown_threshold": round(float(sell_drawdown_threshold), 6),
                                "running_high": round(float(running_high), 4),
                                "current_drawdown": round(float(drawdown), 6),
                            },
                            {
                                "code": "CASH",
                                "name": "现金",
                                "group": "现金/空仓",
                                "score": 1.0,
                                "target_weight": 1.0,
                            },
                        ],
                        "rebalance_reason": {
                            "label": f"高点回撤{sell_drawdown_threshold:.0%}清仓",
                            "detail": (
                                f"历史最高收盘 {running_high:.2f}，当前收盘 {close_float:.2f}，"
                                f"回撤 {drawdown:.1%} 达到 {sell_drawdown_threshold:.0%} 清仓阈值，下一交易日清仓。"
                            ),
                            "drivers": [
                                f"历史最高收盘价 {running_high:.2f}",
                                f"当前回撤 {drawdown:.1%}",
                                f"清仓阈值 {-sell_drawdown_threshold:.1%}",
                            ],
                        },
                    }
                )
                current_exposure = target_exposure
                current_weights = target_weights
                pending_turnover = turnover
                sell_armed = False
        else:
            if drawdown <= -buy_drawdown_threshold:
                target_exposure = 1.0
                target_weights = _weights(target_exposure)
                turnover = _target_turnover(current_weights, target_weights)
                signals.append(
                    {
                        "date": date_text,
                        "apply_from_next_session": True,
                        "strategy_signal": "fcf_peak_drawdown20_full",
                        "variant": "peak_drawdown10_clear_20_full",
                        "target_weights": target_weights,
                        "turnover_to_target": turnover,
                        "top_candidates": [
                            {
                                "code": FREE_CASH_FLOW_PRIMARY_CODE,
                                "name": "国证自由现金流R指数",
                                "group": "自由现金流R",
                                "score": round(float(-drawdown), 6),
                                "target_weight": 1.0,
                                "buy_drawdown_threshold": round(float(buy_drawdown_threshold), 6),
                                "running_high": round(float(running_high), 4),
                                "current_drawdown": round(float(drawdown), 6),
                            }
                        ],
                        "rebalance_reason": {
                            "label": f"高点回撤{buy_drawdown_threshold:.0%}满仓",
                            "detail": (
                                f"历史最高收盘 {running_high:.2f}，当前收盘 {close_float:.2f}，"
                                f"回撤 {drawdown:.1%} 达到 {buy_drawdown_threshold:.0%} 买入阈值，下一交易日满仓。"
                            ),
                            "drivers": [
                                f"历史最高收盘价 {running_high:.2f}",
                                f"当前回撤 {drawdown:.1%}",
                                f"买入阈值 {-buy_drawdown_threshold:.1%}",
                            ],
                        },
                    }
                )
                current_exposure = target_exposure
                current_weights = target_weights
                pending_turnover = turnover
                sell_armed = False

    return pd.DataFrame(records), signals


def _calmar_from_metrics(metrics: dict[str, object]) -> float | None:
    return _calmar(metrics.get("annualized_return"), metrics.get("max_drawdown"))


def _variant_summary(
    variant_frame: pd.DataFrame,
    *,
    fast_window: int,
    slow_window: int,
    benchmark_returns: pd.Series,
    signal_count: int,
) -> dict[str, object]:
    return_column = _variant_return_column(fast_window, slow_window)
    exposure_column = _variant_exposure_column(fast_window, slow_window)
    turnover_column = _variant_turnover_column(fast_window, slow_window)
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
        "variant": _parameter_key(fast_window, slow_window),
        "fast_window": int(fast_window),
        "slow_window": int(slow_window),
        "label": _parameter_label(fast_window, slow_window),
        "equity_key": _variant_equity_column(fast_window, slow_window),
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


def _candidate_parameters(spec: FreeCashFlowDualMaCrossoverSpec) -> list[tuple[int, int]]:
    return [(fast, slow) for fast in spec.fast_windows for slow in spec.slow_windows if fast < slow]


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
    columns = ["date", "index_equity", "fast_ma_equity", "slow_ma_equity", "ma_spread", "target_exposure"]
    rows = []
    for _, row in frame[columns].iterrows():
        item: dict[str, object] = {"date": str(row["date"])}
        for column in columns[1:]:
            value = row.get(column)
            item[column] = None if pd.isna(value) else round(float(value), 6)
        rows.append(item)
    return rows


def _subset_summary(
    variant_frames: dict[str, pd.DataFrame],
    *,
    variant: dict[str, object],
    benchmark_returns: pd.Series,
    split_start: str,
    split_end: str,
) -> dict[str, object] | None:
    frame = variant_frames.get(str(variant.get("variant")))
    if frame is None:
        return None
    subset = frame[(frame["date"] >= split_start) & (frame["date"] <= split_end)].copy()
    if subset.empty:
        return None
    return_column = str(variant["return_key"])
    exposure_column = _variant_exposure_column(int(variant["fast_window"]), int(variant["slow_window"]))
    turnover_column = _variant_turnover_column(int(variant["fast_window"]), int(variant["slow_window"]))
    aligned_benchmark = benchmark_returns.reindex(subset["date"].astype(str)).fillna(0.0)
    metrics = performance_metrics(
        subset[return_column],
        benchmark_returns=pd.Series(aligned_benchmark.to_numpy()),
        turnover=subset[turnover_column],
    )
    return {
        "variant": variant.get("variant"),
        "label": variant.get("label"),
        "start_date": str(subset["date"].iloc[0]),
        "end_date": str(subset["date"].iloc[-1]),
        "sessions": int(len(subset)),
        "total_return": round(float(compound_return(subset[return_column])), 6),
        "annualized_return": metrics.get("annualized_return"),
        "max_drawdown": metrics.get("max_drawdown"),
        "sharpe": metrics.get("sharpe"),
        "calmar": _calmar_from_metrics(metrics),
        "average_target_exposure": round(float(subset[exposure_column].mean()), 6),
    }


def _build_sample_validation(
    variant_summaries: list[dict[str, object]],
    variant_frames: dict[str, pd.DataFrame],
    *,
    benchmark_returns: pd.Series,
    split_date: str,
) -> dict[str, object]:
    train = []
    test = []
    test_start = split_date
    first_date = min(str(frame["date"].iloc[0]) for frame in variant_frames.values() if not frame.empty)
    last_date = max(str(frame["date"].iloc[-1]) for frame in variant_frames.values() if not frame.empty)
    train_end = (pd.to_datetime(split_date, format="%Y%m%d") - pd.Timedelta(days=1)).strftime("%Y%m%d")
    for item in variant_summaries:
        train_item = _subset_summary(
            variant_frames,
            variant=item,
            benchmark_returns=benchmark_returns,
            split_start=first_date,
            split_end=train_end,
        )
        test_item = _subset_summary(
            variant_frames,
            variant=item,
            benchmark_returns=benchmark_returns,
            split_start=test_start,
            split_end=last_date,
        )
        if train_item:
            train.append(train_item)
        if test_item:
            test.append(test_item)
    train_best_calmar = max(train, key=_best_parameter_key) if train else None
    train_best_annualized = max(train, key=_best_annualized_parameter_key) if train else None
    train_best_calmar_test = None
    train_best_annualized_test = None
    if train_best_calmar:
        source = next((item for item in variant_summaries if item["variant"] == train_best_calmar["variant"]), None)
        if source:
            train_best_calmar_test = _subset_summary(
                variant_frames,
                variant=source,
                benchmark_returns=benchmark_returns,
                split_start=test_start,
                split_end=last_date,
            )
    if train_best_annualized:
        source = next((item for item in variant_summaries if item["variant"] == train_best_annualized["variant"]), None)
        if source:
            train_best_annualized_test = _subset_summary(
                variant_frames,
                variant=source,
                benchmark_returns=benchmark_returns,
                split_start=test_start,
                split_end=last_date,
            )
    return {
        "split_date": split_date,
        "train_range": {"start_date": first_date, "end_date": train_end},
        "test_range": {"start_date": test_start, "end_date": last_date},
        "train_best_calmar": train_best_calmar,
        "train_best_calmar_test": train_best_calmar_test,
        "train_best_annualized": train_best_annualized,
        "train_best_annualized_test": train_best_annualized_test,
        "note": "样本外验证先用训练段筛参数，再把该参数放到测试段观察；仍然只是研究辅助，不代表未来收益。",
    }


def run_free_cash_flow_dual_ma_crossover_backtest(
    spec: FreeCashFlowDualMaCrossoverSpec,
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
    for fast_window, slow_window in _candidate_parameters(spec):
        is_default = fast_window == spec.default_fast_window and slow_window == spec.default_slow_window
        variant_frame, signals = _simulate_variant(
            close,
            returns,
            fast_window=fast_window,
            slow_window=slow_window,
            spec=spec,
            collect_signals=is_default,
        )
        return_column = _variant_return_column(fast_window, slow_window)
        equity_column = _variant_equity_column(fast_window, slow_window)
        variant_frame[return_column] = pd.to_numeric(variant_frame[return_column], errors="coerce").fillna(0.0)
        variant_frame[equity_column] = (1.0 + variant_frame[return_column]).cumprod()
        turnover_column = _variant_turnover_column(fast_window, slow_window)
        signal_count = len(signals) if is_default else int((variant_frame[turnover_column] > 0).sum())
        summary = _variant_summary(
            variant_frame,
            fast_window=fast_window,
            slow_window=slow_window,
            benchmark_returns=returns,
            signal_count=signal_count,
        )
        summary["is_default"] = is_default
        summary["full_sample_optimized"] = not is_default
        variant_summaries.append(summary)
        variant_frames[str(summary["variant"])] = variant_frame
        if is_default:
            all_signals_by_variant[str(summary["variant"])] = signals

    default_variant_key = _parameter_key(spec.default_fast_window, spec.default_slow_window)
    best_variant = max(variant_summaries, key=_best_parameter_key)
    best_annualized_variant = max(variant_summaries, key=_best_annualized_parameter_key)
    best_variant_key = str(best_variant["variant"])
    default_frame = variant_frames[default_variant_key]
    best_frame = variant_frames[best_variant_key]
    frame = frame.merge(default_frame, on="date", how="left", suffixes=("", "_default"))
    if best_variant_key != default_variant_key:
        best_columns = ["date", str(best_variant["return_key"]), str(best_variant["equity_key"])]
        frame = frame.merge(best_frame[best_columns], on="date", how="left")

    default_return_column = _variant_return_column(spec.default_fast_window, spec.default_slow_window)
    default_equity_column = _variant_equity_column(spec.default_fast_window, spec.default_slow_window)
    default_exposure_column = _variant_exposure_column(spec.default_fast_window, spec.default_slow_window)
    default_turnover_column = _variant_turnover_column(spec.default_fast_window, spec.default_slow_window)
    best_return_column = str(best_variant["return_key"])
    best_equity_column = str(best_variant["equity_key"])

    frame["strategy_return"] = frame[default_return_column].fillna(0.0)
    frame["strategy_equity"] = frame[default_equity_column].ffill().fillna(1.0)
    frame["target_exposure"] = frame[default_exposure_column].ffill().fillna(spec.high_exposure)
    frame["turnover"] = frame[default_turnover_column].fillna(0.0)
    frame[_benchmark_return_column(spec.index_code)] = frame["date"].map(returns.to_dict()).fillna(0.0).astype(float)
    frame[_benchmark_equity_column(spec.index_code)] = (1.0 + frame[_benchmark_return_column(spec.index_code)]).cumprod()
    frame["index_equity"] = frame[_benchmark_equity_column(spec.index_code)]

    default_fast_ma = close.rolling(spec.default_fast_window, min_periods=spec.default_fast_window).mean()
    default_slow_ma = close.rolling(spec.default_slow_window, min_periods=spec.default_slow_window).mean()
    first_close = float(close.dropna().iloc[0])
    frame["close"] = frame["date"].map(close.to_dict()).astype(float)
    frame["fast_ma_value"] = frame["date"].map(default_fast_ma.to_dict()).astype(float)
    frame["slow_ma_value"] = frame["date"].map(default_slow_ma.to_dict()).astype(float)
    frame["fast_ma_equity"] = frame["fast_ma_value"] / first_close
    frame["slow_ma_equity"] = frame["slow_ma_value"] / first_close
    frame["ma_spread"] = frame["fast_ma_value"] / frame["slow_ma_value"] - 1.0

    if best_variant_key == default_variant_key:
        frame["best_full_sample_return"] = frame["strategy_return"]
        frame["best_full_sample_equity"] = frame["strategy_equity"]
    else:
        frame["best_full_sample_return"] = frame[best_return_column].fillna(0.0)
        frame["best_full_sample_equity"] = frame[best_equity_column].ffill().fillna(1.0)

    drawdown_rule_frame, drawdown_rule_signals = _simulate_drawdown20_ma_rule(close, returns)
    drawdown_rule_frame[DRAWDOWN20_MA_RULE_RETURN] = pd.to_numeric(
        drawdown_rule_frame[DRAWDOWN20_MA_RULE_RETURN], errors="coerce"
    ).fillna(0.0)
    drawdown_rule_frame[DRAWDOWN20_MA_RULE_EQUITY] = (1.0 + drawdown_rule_frame[DRAWDOWN20_MA_RULE_RETURN]).cumprod()
    frame = frame.merge(
        drawdown_rule_frame[
            [
                "date",
                DRAWDOWN20_MA_RULE_RETURN,
                DRAWDOWN20_MA_RULE_EQUITY,
                DRAWDOWN20_MA_RULE_EXPOSURE,
                DRAWDOWN20_MA_RULE_TURNOVER,
            ]
        ],
        on="date",
        how="left",
    )
    frame[DRAWDOWN20_MA_RULE_RETURN] = frame[DRAWDOWN20_MA_RULE_RETURN].fillna(0.0)
    frame[DRAWDOWN20_MA_RULE_EQUITY] = frame[DRAWDOWN20_MA_RULE_EQUITY].ffill().fillna(1.0)
    frame[DRAWDOWN20_MA_RULE_EXPOSURE] = frame[DRAWDOWN20_MA_RULE_EXPOSURE].ffill().fillna(0.0)
    frame[DRAWDOWN20_MA_RULE_TURNOVER] = frame[DRAWDOWN20_MA_RULE_TURNOVER].fillna(0.0)

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
        label=f"{spec.short_name} 默认 MA{spec.default_fast_window}/MA{spec.default_slow_window}",
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
    drawdown_rule_row = _metric_row(
        code=DRAWDOWN20_MA_RULE_CODE,
        label="高点回撤10%清仓 / 20%满仓",
        group="测试规则",
        returns=frame[DRAWDOWN20_MA_RULE_RETURN],
        dates=frame["date"],
        equity_key=DRAWDOWN20_MA_RULE_EQUITY,
    )
    drawdown_rule_row["rebalance_count"] = len(drawdown_rule_signals)
    drawdown_rule_row["average_target_exposure"] = round(float(frame[DRAWDOWN20_MA_RULE_EXPOSURE].mean()), 6)
    comparison_assets = []
    for item in (drawdown_rule_row, benchmark_row, best_row):
        item = dict(item)
        item["return_advantage"] = None if item["total_return"] is None else round(float(strategy_row["total_return"]) - float(item["total_return"]), 6)
        item["drawdown_reduction"] = None if item["max_drawdown"] is None else round(float(strategy_row["max_drawdown"]) - float(item["max_drawdown"]), 6)
        comparison_assets.append(item)

    for item in variant_summaries:
        item["return_advantage_vs_buy_hold"] = round(float(item["total_return"]) - benchmark_total, 6)
        item["drawdown_reduction_vs_buy_hold"] = round(float(item["max_drawdown"]) - benchmark_drawdown, 6)

    parameter_scan = sorted(variant_summaries, key=_best_parameter_key, reverse=True)
    sample_validation = _build_sample_validation(
        variant_summaries,
        variant_frames,
        benchmark_returns=returns,
        split_date=spec.validation_split_date,
    )
    default_variant = next(item for item in variant_summaries if item.get("is_default"))
    signals = all_signals_by_variant.get(default_variant_key, [])
    latest_signal = signals[-1] if signals else {}
    latest_indicator = frame.iloc[-1]
    summary = {
        "strategy_id": spec.strategy_id,
        "strategy_name": spec.name,
        "short_name": f"{spec.short_name} MA{spec.default_fast_window}/MA{spec.default_slow_window}",
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
        "drawdown20_ma_rule": drawdown_rule_row,
        "drawdown20_ma_rule_signal_count": len(drawdown_rule_signals),
        "drawdown20_ma_rule_latest_signal": drawdown_rule_signals[-1] if drawdown_rule_signals else None,
        "sample_validation": sample_validation,
        "parameter_scan": parameter_scan,
        "parameter_scan_sorted_by": "Calmar, annualized return, max drawdown",
        "parameter_scan_lookahead_note": "全样本筛参使用完整回测区间选择参数，属于未来函数研究结果；样本外验证只是辅助观察。",
        "comparison_assets": comparison_assets,
        "metric_comparison_assets": [strategy_row, *comparison_assets],
        "latest_signal": latest_signal.get("strategy_signal"),
        "latest_signal_date": latest_signal.get("date"),
        "latest_weights": latest_signal.get("target_weights", _weights(float(frame["target_exposure"].iloc[-1]))),
        "latest_ma_spread": None if pd.isna(latest_indicator.get("ma_spread")) else round(float(latest_indicator["ma_spread"]), 6),
        "latest_fast_ma_value": None if pd.isna(latest_indicator.get("fast_ma_value")) else round(float(latest_indicator["fast_ma_value"]), 4),
        "latest_slow_ma_value": None if pd.isna(latest_indicator.get("slow_ma_value")) else round(float(latest_indicator["slow_ma_value"]), 4),
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
        DRAWDOWN20_MA_RULE_EQUITY,
        "index_equity",
        "fast_ma_equity",
        "slow_ma_equity",
        "target_exposure",
        "ma_spread",
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
            "indicator": "free_cash_flow_dual_ma_crossover",
            "return_source": "Tushare index_daily for 480092.CNI total-return index series.",
            "signal_timing": "Default MA30/MA90 signal is generated after close on date t and applied starting t+1.",
            "no_lookahead_bias": True,
            "lookahead_note": "默认 MA30/MA90 信号计算无未来价格；但默认参数来自全样本筛参观察，页面整体仍按含未来函数研究结果标注。",
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
            "dual_ma_crossover_signal": True,
            "default_rule_no_lookahead_bias": True,
            "parameter_scan_has_lookahead_bias": True,
            "uses_total_return_index": resolved_index_type == "total_return",
        },
    }
