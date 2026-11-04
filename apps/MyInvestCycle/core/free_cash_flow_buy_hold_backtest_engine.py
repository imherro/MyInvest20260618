from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import pandas as pd

from core.alpha_validation_engine import annualized_return, compound_return, max_drawdown, performance_metrics
from core.etf_return_utils import coerce_price_frame, daily_return_series
from core.free_cash_flow_trend_channel_backtest_engine import (
    FREE_CASH_FLOW_PRIMARY_CODE,
    _benchmark_equity_column,
    _benchmark_key,
    _benchmark_return_column,
)
from core.strategy_suite_backtest_engine import Asset
from engine.cycle_detector import detect_major_cycles


CSI300_TOTAL_RETURN_CODE = "h00300.CSI"
CSI500_TOTAL_RETURN_CODE = "h00905.CSI"
CHINEXT_TOTAL_RETURN_CODE = "399606.SZ"
DIVIDEND_LOW_VOL_TOTAL_RETURN_CODE = "h20269.CSI"
SHANGHAI_COMPOSITE_CODE = "000001.SH"


@dataclass(frozen=True)
class FreeCashFlowBuyHoldSpec:
    strategy_id: str = "free-cash-flow-buy-hold-480092"
    name: str = "自由现金流R满仓持有策略"
    short_name: str = "满仓持有480092"
    description: str = "从 480092.CNI 国证自由现金流R指数有数据开始，模拟满仓持有并与主要全收益指数对比。"
    method: tuple[str, ...] = (
        "策略标的为 480092.CNI 国证自由现金流R指数，回测从该指数本地/Tushare 可得第一条日线开始。",
        "组合始终 100% 持有 480092.CNI，不择时、不调仓、不使用未来函数。",
        "对比指数全部使用全收益口径：h00300.CSI 300收益、h00905.CSI 500收益、399606.SZ 创业板R、h20269.CSI 红利低波全收益。",
        "图表背景叠加长期牛熊周期色块，并用上证指数归一化曲线作为灰色背景参考。",
    )
    index_code: str = FREE_CASH_FLOW_PRIMARY_CODE
    benchmark_codes: tuple[str, ...] = (
        CSI300_TOTAL_RETURN_CODE,
        CSI500_TOTAL_RETURN_CODE,
        CHINEXT_TOTAL_RETURN_CODE,
        DIVIDEND_LOW_VOL_TOTAL_RETURN_CODE,
    )
    background_codes: tuple[str, ...] = (SHANGHAI_COMPOSITE_CODE,)
    warmup_calendar_days: int = 900
    backtest_start_date: str = "20100101"


FREE_CASH_FLOW_BUY_HOLD_SPEC = FreeCashFlowBuyHoldSpec()
FREE_CASH_FLOW_BUY_HOLD_UNIVERSE = (
    Asset(FREE_CASH_FLOW_PRIMARY_CODE, "国证自由现金流R指数", "自由现金流R"),
)


def _round(value: float | None, digits: int = 6) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _calmar(annualized: float | None, drawdown: float | None) -> float | None:
    if annualized is None or drawdown is None:
        return None
    drawdown_abs = abs(float(drawdown))
    if drawdown_abs <= 0:
        return None
    return round(float(annualized) / drawdown_abs, 6)


def _asset_meta(code: str) -> dict[str, str]:
    assets = {
        FREE_CASH_FLOW_PRIMARY_CODE: {
            "name": "国证自由现金流R指数",
            "group": "自由现金流",
            "label": "自由现金流R 480092.CNI",
        },
        CSI300_TOTAL_RETURN_CODE: {
            "name": "300收益",
            "group": "沪深300全收益",
            "label": "沪深300全收益 h00300.CSI",
        },
        CSI500_TOTAL_RETURN_CODE: {
            "name": "500收益",
            "group": "中证500全收益",
            "label": "中证500全收益 h00905.CSI",
        },
        CHINEXT_TOTAL_RETURN_CODE: {
            "name": "创业板R",
            "group": "创业板全收益",
            "label": "创业板全收益 399606.SZ",
        },
        DIVIDEND_LOW_VOL_TOTAL_RETURN_CODE: {
            "name": "红利低波全收益",
            "group": "红利低波全收益",
            "label": "红利低波全收益 h20269.CSI",
        },
    }
    return assets.get(code, {"name": code, "group": "指数对比", "label": code})


def _asset_metrics(code: str, returns: pd.Series) -> dict[str, object]:
    clean = returns.dropna().fillna(0.0)
    if clean.empty:
        meta = _asset_meta(code)
        return {
            "code": code,
            "name": meta["name"],
            "group": meta["group"],
            "label": meta["label"],
            "start_date": None,
            "end_date": None,
            "sessions": 0,
            "total_return": None,
            "annualized_return": None,
            "max_drawdown": None,
            "sharpe": None,
            "calmar": None,
        }
    equity = (1.0 + clean).cumprod()
    total = compound_return(clean)
    annualized = annualized_return(total, len(clean))
    metrics = performance_metrics(clean)
    meta = _asset_meta(code)
    return {
        "code": code,
        "name": meta["name"],
        "group": meta["group"],
        "label": meta["label"],
        "start_date": str(clean.index.min()),
        "end_date": str(clean.index.max()),
        "sessions": int(len(clean)),
        "total_return": round(total, 6),
        "annualized_return": _round(annualized),
        "max_drawdown": max_drawdown(equity),
        "sharpe": metrics.get("sharpe"),
        "calmar": _calmar(_round(annualized), max_drawdown(equity)),
    }


def _equity_on_primary_dates(primary_dates: pd.Index, returns: pd.Series) -> pd.Series:
    aligned = returns.reindex(primary_dates)
    available = aligned.notna()
    result = pd.Series(index=primary_dates, dtype=float)
    if not available.any():
        return result
    result.loc[available] = (1.0 + aligned.loc[available].fillna(0.0)).cumprod()
    return result


def _curve_records(frame: pd.DataFrame, columns: list[str]) -> list[dict[str, object]]:
    rows = []
    for _, row in frame[["date", *columns]].iterrows():
        item: dict[str, object] = {"date": str(row["date"])}
        for column in columns:
            value = row.get(column)
            item[column] = None if pd.isna(value) else round(float(value), 6)
        rows.append(item)
    return rows


def _shanghai_background(index_history: Mapping[str, pd.DataFrame], primary_dates: pd.Index) -> pd.Series:
    if SHANGHAI_COMPOSITE_CODE not in index_history:
        return pd.Series(index=primary_dates, dtype=float)
    shanghai = coerce_price_frame(index_history[SHANGHAI_COMPOSITE_CODE])
    if shanghai.empty:
        return pd.Series(index=primary_dates, dtype=float)
    close = shanghai.drop_duplicates("trade_date", keep="last").set_index("trade_date")["close"].astype(float)
    close = close.reindex(primary_dates).ffill()
    first = close.dropna().iloc[0] if not close.dropna().empty else None
    if not first:
        return pd.Series(index=primary_dates, dtype=float)
    return close / float(first)


def _cycle_blocks(index_history: Mapping[str, pd.DataFrame]) -> list[dict[str, object]]:
    if SHANGHAI_COMPOSITE_CODE not in index_history:
        return []
    try:
        cycle = detect_major_cycles(coerce_price_frame(index_history[SHANGHAI_COMPOSITE_CODE]))
    except Exception:
        return []
    return [
        block
        for block in cycle.get("cycle_blocks", [])
        if isinstance(block, dict) and block.get("state") in {"bull", "bear"}
    ]


def run_free_cash_flow_buy_hold_backtest(
    spec: FreeCashFlowBuyHoldSpec,
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

    primary_prices = coerce_price_frame(index_history[source_code])
    primary_prices = primary_prices[(primary_prices["trade_date"] >= start_date) & (primary_prices["trade_date"] <= end_date)]
    primary_prices = primary_prices.drop_duplicates("trade_date", keep="last").sort_values("trade_date")
    if primary_prices.empty:
        raise ValueError("no 480092.CNI rows available in backtest window")

    primary_dates = pd.Index(primary_prices["trade_date"].astype(str), name="date")
    primary_returns = daily_return_series(primary_prices).reindex(primary_dates).fillna(0.0)
    if not primary_returns.empty:
        primary_returns.iloc[0] = 0.0
    frame = pd.DataFrame({"date": primary_dates.astype(str)})
    frame["strategy_return"] = primary_returns.to_numpy()
    frame["strategy_equity"] = (1.0 + frame["strategy_return"]).cumprod()
    frame["target_exposure"] = 1.0
    frame["turnover"] = [1.0, *([0.0] * (len(frame) - 1))]
    frame["shanghai_equity"] = _shanghai_background(index_history, primary_dates).to_numpy()

    comparison_assets = []
    metric_assets = []
    strategy_metrics = _asset_metrics(spec.index_code, primary_returns)
    strategy_metrics["isStrategy"] = True
    metric_assets.append(strategy_metrics)

    for code in spec.benchmark_codes:
        if code not in index_history:
            raise ValueError(f"missing comparison index history: {code}")
        prices = coerce_price_frame(index_history[code])
        prices = prices[(prices["trade_date"] >= start_date) & (prices["trade_date"] <= end_date)]
        prices = prices.drop_duplicates("trade_date", keep="last").sort_values("trade_date")
        returns = daily_return_series(prices)
        aligned_returns = returns.reindex(primary_dates).fillna(0.0)
        if not aligned_returns.empty:
            aligned_returns.iloc[0] = 0.0
        metrics = _asset_metrics(code, aligned_returns)
        metrics["return_advantage"] = (
            None
            if metrics["total_return"] is None or strategy_metrics["total_return"] is None
            else round(float(strategy_metrics["total_return"]) - float(metrics["total_return"]), 6)
        )
        metrics["drawdown_reduction"] = (
            None
            if metrics["max_drawdown"] is None or strategy_metrics["max_drawdown"] is None
            else round(float(strategy_metrics["max_drawdown"]) - float(metrics["max_drawdown"]), 6)
        )
        comparison_assets.append(metrics)
        metric_assets.append(metrics)
        frame[_benchmark_return_column(code)] = aligned_returns.to_numpy()
        frame[_benchmark_equity_column(code)] = (1.0 + aligned_returns).cumprod().to_numpy()

    primary = performance_metrics(frame["strategy_return"], turnover=frame["turnover"])
    strategy_total = compound_return(frame["strategy_return"])
    strategy_drawdown = max_drawdown(frame["strategy_equity"])
    strategy_annualized = primary.get("annualized_return")
    summary = {
        "strategy_id": spec.strategy_id,
        "strategy_name": spec.name,
        "short_name": spec.short_name,
        "start_date": str(frame["date"].iloc[0]),
        "end_date": str(frame["date"].iloc[-1]),
        "sessions": int(len(frame)),
        "rebalance_count": 1,
        "strategy_total_return": round(strategy_total, 6),
        "annualized_return": strategy_annualized,
        "equal_weight_label": "沪深300全收益",
        "equal_weight_return": comparison_assets[0]["total_return"] if comparison_assets else None,
        "alpha_vs_equal_weight": (
            None
            if not comparison_assets or comparison_assets[0]["total_return"] is None
            else round(strategy_total - float(comparison_assets[0]["total_return"]), 6)
        ),
        "sharpe": primary.get("sharpe"),
        "calmar": _calmar(strategy_annualized, strategy_drawdown),
        "max_drawdown": strategy_drawdown,
        "hit_rate_vs_primary_benchmark": None,
        "average_turnover": primary.get("average_turnover"),
        "cumulative_turnover": primary.get("cumulative_turnover"),
        "comparison_assets": comparison_assets,
        "metric_comparison_assets": metric_assets,
        "latest_signal": "fcf_buy_hold_full",
        "latest_signal_date": str(frame["date"].iloc[0]),
        "latest_weights": {spec.index_code: 1.0},
    }
    for item in comparison_assets:
        key = _benchmark_key(str(item["code"]))
        summary[f"benchmark_{key}_return"] = item["total_return"]
        summary[f"benchmark_{key}_max_drawdown"] = item["max_drawdown"]
        summary[f"alpha_vs_{key}"] = item.get("return_advantage")

    curve_columns = [
        "strategy_equity",
        "shanghai_equity",
        *[_benchmark_equity_column(code) for code in spec.benchmark_codes],
    ]
    signals = [
        {
            "date": str(frame["date"].iloc[0]),
            "apply_from_next_session": False,
            "strategy_signal": "fcf_buy_hold_full",
            "target_weights": {spec.index_code: 1.0},
            "turnover_to_target": 1.0,
            "top_candidates": [
                {
                    "code": spec.index_code,
                    "name": "国证自由现金流R指数",
                    "group": "自由现金流R",
                    "score": 1.0,
                    "target_weight": 1.0,
                }
            ],
            "rebalance_reason": {
                "label": "满仓持有",
                "detail": "起始日建仓 480092.CNI，之后保持 100% 持有，不做择时调仓。",
            },
        }
    ]
    return {
        "metadata": {
            "engine": f"{spec.name} Backtest",
            "strategy_id": spec.strategy_id,
            "description": spec.description,
            "method": list(spec.method),
            "universe": [
                {"code": asset.code, "name": asset.name, "group": asset.group, "label": asset.label}
                for asset in FREE_CASH_FLOW_BUY_HOLD_UNIVERSE
            ],
            "index_code": spec.index_code,
            "resolved_index_code": source_code,
            "resolved_index_type": resolved_index_type,
            "benchmark_codes": list(spec.benchmark_codes),
            "background_codes": list(spec.background_codes),
            "indicator": "free_cash_flow_buy_hold",
            "return_source": "Tushare index_daily total-return index series where available.",
            "signal_timing": "Buy at the first available 480092.CNI observation and hold.",
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
            "static_allocation": True,
            "full_hold_benchmark": True,
            "alpha_positive_vs_equal_weight": bool(summary["alpha_vs_equal_weight"] and summary["alpha_vs_equal_weight"] > 0),
            "no_lookahead_bias": True,
            "uses_total_return_indices": True,
        },
    }
