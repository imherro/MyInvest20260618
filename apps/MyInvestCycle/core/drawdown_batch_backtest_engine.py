from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import pandas as pd

from core.alpha_validation_engine import compound_return, max_drawdown, performance_metrics
from core.etf_return_utils import coerce_price_frame, daily_return_series
from core.strategy_suite_backtest_engine import Asset, RETURN_SOURCE


@dataclass(frozen=True)
class DrawdownBatchSpec:
    strategy_id: str
    name: str
    short_name: str
    description: str
    method: list[str]
    universe: tuple[Asset, ...]
    cash_code: str
    benchmark_codes: tuple[str, ...]
    risky_codes: tuple[str, ...]
    sleeve_cap: float = 0.25
    max_risky_exposure: float = 0.90
    min_buy_drawdown: float = 0.08


MAX_DRAWDOWN_BATCH_SPEC = DrawdownBatchSpec(
    strategy_id="max-drawdown-batch",
    name="最大回撤分批买入策略",
    short_name="回撤分批买入",
    description=(
        "用每只 ETF 自身历史回撤分布定义左侧分批买入档位；"
        "回撤修复后按档位自动降仓，未投入资金进入 511880 现金代理。"
    ),
    method=[
        "候选权益资产为 510300、510880、510500、159915；511880 只作为现金/债券代理和未投入资金承接，不参与回撤买入评分。",
        "每 20 个交易日重新计算各 ETF 截至当日的历史回撤深度分布，信号在收盘后生成并从下一交易日生效。",
        "当前回撤深度进入历史 70/80/90/95 分位时，分别配置该 ETF 目标袖珍仓位的 25%/50%/75%/100%。",
        "单只 ETF 满档上限 25%，组合权益总上限 90%；低于 70 分位或低于 8% 最低回撤门槛时该 ETF 退出，资金回到 511880。",
        "卖出不是主观止盈，而是回撤修复后的规则化降档；该策略用于验证左侧买入思想，不代表稳赚或真实交易建议。",
    ],
    universe=(
        Asset("510300.SH", "沪深300ETF", "价值/大盘"),
        Asset("510880.SH", "红利ETF", "红利/低波"),
        Asset("510500.SH", "中证500ETF", "中小盘"),
        Asset("159915.SZ", "创业板ETF", "成长/科技"),
        Asset("511880.SH", "银华日利ETF", "现金/债券代理"),
    ),
    cash_code="511880.SH",
    benchmark_codes=("510300.SH", "510880.SH", "510500.SH", "159915.SZ", "511880.SH"),
    risky_codes=("510300.SH", "510880.SH", "510500.SH", "159915.SZ"),
)


def _asset_map(spec: DrawdownBatchSpec) -> dict[str, Asset]:
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
        raise ValueError("no ETF price history available for drawdown batch backtest")
    return pd.DataFrame(returns).sort_index()


def _target_turnover(previous: Mapping[str, float], current: Mapping[str, float]) -> float:
    keys = set(previous) | set(current)
    return round(sum(abs(float(current.get(key, 0.0)) - float(previous.get(key, 0.0))) for key in keys) / 2.0, 6)


def _round_weights(weights: Mapping[str, float], cash_code: str) -> dict[str, float]:
    clean = {code: max(0.0, float(weight)) for code, weight in weights.items() if float(weight) > 0.000001}
    total = sum(clean.values())
    if total <= 0:
        return {cash_code: 1.0}
    if total > 1.0:
        clean = {code: weight / total for code, weight in clean.items()}
    else:
        clean[cash_code] = clean.get(cash_code, 0.0) + (1.0 - total)
    return {code: round(weight, 6) for code, weight in clean.items() if weight > 0.000001}


def _compound_window(series: pd.Series, window: int) -> float | None:
    clean = series.dropna().tail(window)
    if len(clean) < window:
        return None
    return float((1.0 + clean).prod() - 1.0)


def _drawdown_depth(series: pd.Series) -> pd.Series:
    equity = (1.0 + series.fillna(0.0)).cumprod()
    return (1.0 - equity / equity.cummax()).clip(lower=0.0)


def _batch_level(current_depth: float, thresholds: Mapping[str, float]) -> float:
    if current_depth >= thresholds["p95"]:
        return 1.0
    if current_depth >= thresholds["p90"]:
        return 0.75
    if current_depth >= thresholds["p80"]:
        return 0.50
    if current_depth >= thresholds["p70"]:
        return 0.25
    return 0.0


def _drawdown_features(
    returns: pd.DataFrame,
    date_text: str,
    spec: DrawdownBatchSpec,
    *,
    min_history_sessions: int,
) -> dict[str, dict[str, float]]:
    features: dict[str, dict[str, float]] = {}
    for code in spec.risky_codes:
        if code not in returns:
            continue
        series = returns.loc[:date_text, code].dropna()
        if len(series) < min_history_sessions:
            continue
        depth = _drawdown_depth(series).dropna()
        if len(depth) < min_history_sessions:
            continue
        quantiles = depth.quantile([0.50, 0.70, 0.80, 0.90, 0.95])
        thresholds = {
            "p50": max(float(quantiles.loc[0.50]), 0.04),
            "p70": max(float(quantiles.loc[0.70]), spec.min_buy_drawdown),
            "p80": max(float(quantiles.loc[0.80]), 0.10),
            "p90": max(float(quantiles.loc[0.90]), 0.14),
            "p95": max(float(quantiles.loc[0.95]), 0.18),
        }
        current_depth = float(depth.iloc[-1])
        drawdown_percentile = float((depth <= current_depth).mean())
        level = _batch_level(current_depth, thresholds)
        return_60 = _compound_window(series, 60)
        return_120 = _compound_window(series, 120)
        features[code] = {
            "score": round(drawdown_percentile, 6),
            "batch_level": level,
            "target_weight": round(spec.sleeve_cap * level, 6),
            "current_drawdown": round(current_depth, 6),
            "drawdown_percentile": round(drawdown_percentile, 6),
            "threshold_p50": round(thresholds["p50"], 6),
            "threshold_p70": round(thresholds["p70"], 6),
            "threshold_p80": round(thresholds["p80"], 6),
            "threshold_p90": round(thresholds["p90"], 6),
            "threshold_p95": round(thresholds["p95"], 6),
            "return_60": round(float(return_60 or 0.0), 6),
            "return_120": round(float(return_120 or 0.0), 6),
        }
    return features


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
                "batch_level": round(float(item.get("batch_level", 0.0)), 6),
                "target_weight": round(float(item.get("target_weight", 0.0)), 6),
                "current_drawdown": round(float(item.get("current_drawdown", 0.0)), 6),
                "drawdown_percentile": round(float(item.get("drawdown_percentile", 0.0)), 6),
                "threshold_p70": round(float(item.get("threshold_p70", 0.0)), 6),
                "threshold_p80": round(float(item.get("threshold_p80", 0.0)), 6),
                "threshold_p90": round(float(item.get("threshold_p90", 0.0)), 6),
                "threshold_p95": round(float(item.get("threshold_p95", 0.0)), 6),
                "return_60": round(float(item.get("return_60", 0.0)), 6),
                "return_120": round(float(item.get("return_120", 0.0)), 6),
            }
        )
    return rows


def _allocate_drawdown_batches(
    features: Mapping[str, dict[str, float]],
    spec: DrawdownBatchSpec,
) -> tuple[dict[str, float], str, list[str]]:
    target_weights = {
        code: float(item["target_weight"])
        for code, item in features.items()
        if float(item.get("target_weight", 0.0)) > 0
    }
    risky_total = sum(target_weights.values())
    if risky_total > spec.max_risky_exposure:
        scale = spec.max_risky_exposure / risky_total
        target_weights = {code: weight * scale for code, weight in target_weights.items()}
        risky_total = spec.max_risky_exposure
    target_weights[spec.cash_code] = 1.0 - risky_total
    weights = _round_weights(target_weights, spec.cash_code)

    active = [
        (code, item)
        for code, item in sorted(features.items(), key=lambda pair: pair[1].get("target_weight", 0.0), reverse=True)
        if float(item.get("target_weight", 0.0)) > 0
    ]
    if not active:
        return weights, "drawdown_cash_wait", [
            "四只权益 ETF 当前回撤未进入历史 70 分位或 8% 最低回撤门槛，维持 511880 现金代理。"
        ]
    drivers = []
    for code, item in active:
        drivers.append(
            f"{code} 回撤 {item['current_drawdown']:.1%}，处于自身历史回撤约 {item['drawdown_percentile']:.1%} 分位，买入档位 {item['batch_level']:.0%}。"
        )
    return weights, "drawdown_ladder_buy", [
        f"{len(active)} 只 ETF 进入回撤分批买入档位；单 ETF 满档 25%，权益总仓位上限 90%，其余资金放入 511880。",
        *drivers,
    ]


def _curve_records(frame: pd.DataFrame, spec: DrawdownBatchSpec) -> list[dict[str, object]]:
    columns = ["date", "strategy_equity", "equal_weight_equity", *[_benchmark_equity_column(code) for code in spec.benchmark_codes]]
    rows = []
    for _, row in frame[columns].iterrows():
        rows.append({key: (str(row[key]) if key == "date" else round(float(row[key]), 6)) for key in columns if key in row})
    return rows


def _return_records(frame: pd.DataFrame, spec: DrawdownBatchSpec) -> list[dict[str, object]]:
    columns = ["date", "strategy_return", "equal_weight_return", "turnover", *[_benchmark_return_column(code) for code in spec.benchmark_codes]]
    rows = []
    for _, row in frame[columns].iterrows():
        rows.append({key: (str(row[key]) if key == "date" else round(float(row[key]), 8)) for key in columns if key in row})
    return rows


def run_max_drawdown_batch_backtest(
    price_history: Mapping[str, pd.DataFrame],
    *,
    start_date: str,
    end_date: str,
    rebalance_every_sessions: int = 20,
    min_history_sessions: int = 252,
    spec: DrawdownBatchSpec = MAX_DRAWDOWN_BATCH_SPEC,
) -> dict[str, object]:
    asset_lookup = _asset_map(spec)
    returns = _returns_matrix(price_history)
    required_codes = [asset.code for asset in spec.universe]
    dates = sorted(date for date in returns.index.astype(str) if start_date <= date <= end_date)
    if not dates:
        raise ValueError("no overlapping dates between ETF returns and drawdown batch backtest window")

    current_weights: dict[str, float] = {}
    pending_turnover = 0.0
    last_rebalance_index = -max(1, rebalance_every_sessions)
    daily_records: list[dict[str, object]] = []
    signal_records: list[dict[str, object]] = []

    for index, date_text in enumerate(dates):
        day_returns = returns.loc[date_text].fillna(0.0)
        available_codes = [code for code in required_codes if code in day_returns.index]
        risky_available = [code for code in spec.risky_codes if code in day_returns.index]
        if current_weights:
            strategy_return = sum(float(weight) * float(day_returns.get(code, 0.0)) for code, weight in current_weights.items())
            record = {
                "date": date_text,
                "strategy_return": strategy_return,
                "equal_weight_return": float(day_returns[risky_available].mean()) if risky_available else 0.0,
                "turnover": pending_turnover,
                "applied_weights": dict(current_weights),
            }
            for code in spec.benchmark_codes:
                record[_benchmark_return_column(code)] = float(day_returns.get(code, 0.0))
            daily_records.append(record)
            pending_turnover = 0.0

        should_rebalance = index - last_rebalance_index >= max(1, rebalance_every_sessions)
        if should_rebalance:
            features = _drawdown_features(
                returns,
                date_text,
                spec,
                min_history_sessions=min_history_sessions,
            )
            if not features:
                continue
            new_weights, signal, drivers = _allocate_drawdown_batches(features, spec)
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
        raise ValueError("no drawdown batch backtest returns generated")

    return_columns = ["strategy_return", "equal_weight_return", *[_benchmark_return_column(code) for code in spec.benchmark_codes]]
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
    comparison_assets.append(
        {
            "code": "equal_weight",
            "name": "四 ETF 等权组合",
            "group": "基准",
            "label": "四 ETF 等权组合",
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
            "engine": "Max Drawdown Batch Backtest",
            "strategy_id": spec.strategy_id,
            "description": spec.description,
            "method": spec.method,
            "universe": [
                {"code": asset.code, "name": asset.name, "group": asset.group, "label": asset.label}
                for asset in spec.universe
            ],
            "risky_codes": list(spec.risky_codes),
            "cash_code": spec.cash_code,
            "return_source": RETURN_SOURCE,
            "signal_timing": "Signal is generated after close on date t and applied starting t+1.",
            "drawdown_basis": "Each ETF uses only its own history available up to signal date to calculate drawdown percentiles.",
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
            "not_guaranteed_profit": True,
        },
    }
