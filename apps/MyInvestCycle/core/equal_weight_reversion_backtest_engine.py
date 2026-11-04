from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import pandas as pd

from core.alpha_validation_engine import compound_return, max_drawdown, performance_metrics
from core.etf_return_utils import coerce_price_frame, daily_return_series
from core.strategy_suite_backtest_engine import Asset, RETURN_SOURCE


@dataclass(frozen=True)
class EqualWeightReversionSpec:
    strategy_id: str
    name: str
    short_name: str
    description: str
    method: list[str]
    universe: tuple[Asset, ...]
    risky_codes: tuple[str, ...]
    cash_code: str
    benchmark_codes: tuple[str, ...]
    risk_controlled: bool
    ma_window: int = 250
    z_window: int = 250
    z_min_periods: int = 120
    trend_slope_window: int = 60
    downtrend_cap: float = 0.60
    warmup_calendar_days: int = 900


REVERSION_UNIVERSE = (
    Asset("510300.SH", "沪深300ETF", "价值/大盘"),
    Asset("510880.SH", "红利ETF", "红利/低波"),
    Asset("510500.SH", "中证500ETF", "中小盘"),
    Asset("159915.SZ", "创业板ETF", "成长/科技"),
    Asset("511880.SH", "银华日利ETF", "现金/债券代理"),
)
REVERSION_RISKY_CODES = ("510300.SH", "510880.SH", "510500.SH", "159915.SZ")
REVERSION_BENCHMARK_CODES = ("510300.SH", "510880.SH", "510500.SH", "159915.SZ", "511880.SH")


EQUAL_WEIGHT_REVERSION_SPECS: dict[str, EqualWeightReversionSpec] = {
    "equal-weight-reversion-basic": EqualWeightReversionSpec(
        strategy_id="equal-weight-reversion-basic",
        name="四 ETF 等权均线回归策略（基础版）",
        short_name="等权回归基础",
        description="构造 510300、510880、510500、159915 四 ETF 等权净值，按其偏离 MA250 的 z-score 分档增减权益仓位。",
        method=[
            "先用 510300、510880、510500、159915 的日收益构造内部四 ETF 等权净值曲线。",
            "用 MA250 作为长期中枢，计算偏离率 equal_weight_equity / MA250 - 1。",
            "用最近 250 日偏离率标准差把偏离率标准化为 z-score，信号在收盘后生成并从下一交易日生效。",
            "z<=-2.0 配 100% 权益；-2.0<z<=-1.2 配 80%；-1.2<z<=-0.5 配 60%；-0.5<z<1.0 配 50%；1.0<=z<1.8 配 30%；z>=1.8 配 10%。",
            "权益部分四只 ETF 等权，剩余资金进入 511880；该基础版不做趋势过滤，用于检验纯均值回归想法。",
        ],
        universe=REVERSION_UNIVERSE,
        risky_codes=REVERSION_RISKY_CODES,
        cash_code="511880.SH",
        benchmark_codes=REVERSION_BENCHMARK_CODES,
        risk_controlled=False,
    ),
    "equal-weight-reversion-guarded": EqualWeightReversionSpec(
        strategy_id="equal-weight-reversion-guarded",
        name="四 ETF 等权均线回归策略（风控版）",
        short_name="等权回归风控",
        description="在基础 z-score 均值回归规则上增加 MA250 下行过滤，限制熊市中越跌越买。",
        method=[
            "先用 510300、510880、510500、159915 的日收益构造内部四 ETF 等权净值曲线。",
            "基础仓位仍由等权净值偏离 MA250 的 z-score 分档决定。",
            "如果等权净值低于 MA250 且 MA250 的 60 日斜率为负，最高权益仓位限制为 60%。",
            "趋势过滤只限制加仓上限，不改变高位减仓逻辑；权益部分四 ETF 等权，剩余资金进入 511880。",
            "该风控版用于检验：均值回归信号在加入熊市防接刀规则后，能否改善回撤和收益质量。",
        ],
        universe=REVERSION_UNIVERSE,
        risky_codes=REVERSION_RISKY_CODES,
        cash_code="511880.SH",
        benchmark_codes=REVERSION_BENCHMARK_CODES,
        risk_controlled=True,
    ),
}


def _asset_map(spec: EqualWeightReversionSpec) -> dict[str, Asset]:
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
        raise ValueError("no ETF price history available for equal-weight reversion backtest")
    return pd.DataFrame(returns).sort_index()


def _target_turnover(previous: Mapping[str, float], current: Mapping[str, float]) -> float:
    keys = set(previous) | set(current)
    return round(sum(abs(float(current.get(key, 0.0)) - float(previous.get(key, 0.0))) for key in keys) / 2.0, 6)


def _normalize_weights(weights: Mapping[str, float]) -> dict[str, float]:
    clean = {code: max(0.0, float(weight)) for code, weight in weights.items() if float(weight) > 0.000001}
    total = sum(clean.values())
    if total <= 0:
        return {}
    return {code: round(weight / total, 6) for code, weight in clean.items()}


def _target_equity_from_z(z_score: float) -> tuple[float, str]:
    if z_score <= -2.0:
        return 1.00, "reversion_full_buy"
    if z_score <= -1.2:
        return 0.80, "reversion_buy"
    if z_score <= -0.5:
        return 0.60, "reversion_mild_buy"
    if z_score < 1.0:
        return 0.50, "reversion_neutral"
    if z_score < 1.8:
        return 0.30, "reversion_reduce"
    return 0.10, "reversion_light"


def _build_indicator_frame(returns: pd.DataFrame, spec: EqualWeightReversionSpec) -> pd.DataFrame:
    complete = returns.dropna(subset=list(spec.risky_codes)).copy()
    if complete.empty:
        raise ValueError("no complete four-ETF history for equal-weight reversion")
    equal_return = complete[list(spec.risky_codes)].mean(axis=1)
    indicator = pd.DataFrame(index=complete.index.astype(str))
    indicator["equal_weight_return"] = equal_return
    indicator["equal_weight_equity"] = (1.0 + indicator["equal_weight_return"].fillna(0.0)).cumprod()
    indicator["ma_equity"] = indicator["equal_weight_equity"].rolling(spec.ma_window, min_periods=spec.ma_window).mean()
    indicator["deviation"] = indicator["equal_weight_equity"] / indicator["ma_equity"] - 1.0
    indicator["deviation_std"] = indicator["deviation"].rolling(spec.z_window, min_periods=spec.z_min_periods).std()
    indicator["z_score"] = indicator["deviation"] / indicator["deviation_std"]
    indicator["ma_slope"] = indicator["ma_equity"] / indicator["ma_equity"].shift(spec.trend_slope_window) - 1.0
    return indicator


def _weights_for_signal(
    spec: EqualWeightReversionSpec,
    *,
    target_equity: float,
) -> dict[str, float]:
    target_equity = max(0.0, min(1.0, float(target_equity)))
    risky_weight = target_equity / len(spec.risky_codes)
    weights = {code: risky_weight for code in spec.risky_codes}
    weights[spec.cash_code] = 1.0 - target_equity
    return _normalize_weights(weights)


def _top_candidates(
    spec: EqualWeightReversionSpec,
    *,
    target_equity: float,
    z_score: float,
    deviation: float,
) -> list[dict[str, object]]:
    asset_lookup = _asset_map(spec)
    risky_weight = target_equity / len(spec.risky_codes)
    rows = []
    for code in spec.risky_codes:
        asset = asset_lookup.get(code)
        rows.append(
            {
                "code": code,
                "name": asset.name if asset else code,
                "group": asset.group if asset else "--",
                "score": round(float(risky_weight), 6),
                "target_weight": round(float(risky_weight), 6),
                "z_score": round(float(z_score), 6),
                "deviation": round(float(deviation), 6),
            }
        )
    if target_equity < 1.0:
        cash_asset = asset_lookup.get(spec.cash_code)
        rows.append(
            {
                "code": spec.cash_code,
                "name": cash_asset.name if cash_asset else spec.cash_code,
                "group": cash_asset.group if cash_asset else "现金",
                "score": round(float(1.0 - target_equity), 6),
                "target_weight": round(float(1.0 - target_equity), 6),
                "z_score": round(float(z_score), 6),
                "deviation": round(float(deviation), 6),
            }
        )
    return sorted(rows, key=lambda row: float(row["target_weight"]), reverse=True)


def _curve_records(frame: pd.DataFrame, spec: EqualWeightReversionSpec) -> list[dict[str, object]]:
    columns = ["date", "strategy_equity", "equal_weight_equity", *[_benchmark_equity_column(code) for code in spec.benchmark_codes]]
    rows = []
    for _, row in frame[columns].iterrows():
        rows.append({key: (str(row[key]) if key == "date" else round(float(row[key]), 6)) for key in columns if key in row})
    return rows


def _return_records(frame: pd.DataFrame, spec: EqualWeightReversionSpec) -> list[dict[str, object]]:
    columns = ["date", "strategy_return", "equal_weight_return", "turnover", *[_benchmark_return_column(code) for code in spec.benchmark_codes]]
    rows = []
    for _, row in frame[columns].iterrows():
        rows.append({key: (str(row[key]) if key == "date" else round(float(row[key]), 8)) for key in columns if key in row})
    return rows


def _indicator_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    columns = ["date", "equal_weight_equity", "ma_equity", "deviation", "z_score", "ma_slope", "target_equity"]
    rows = []
    for _, row in frame[columns].iterrows():
        item: dict[str, object] = {"date": str(row["date"])}
        for column in columns:
            if column == "date":
                continue
            value = row.get(column)
            item[column] = None if pd.isna(value) else round(float(value), 6)
        rows.append(item)
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


def _signal_detail(
    spec: EqualWeightReversionSpec,
    *,
    date_text: str,
    signal: str,
    base_equity: float,
    target_equity: float,
    z_score: float,
    deviation: float,
    ma_slope: float,
    guard_active: bool,
) -> list[str]:
    direction = "低于中枢，按均值回归加仓" if z_score < -0.5 else "高于中枢，按均值回归降仓" if z_score >= 1.0 else "处于中性区间"
    drivers = [
        f"{date_text} 等权 ETF 偏离 MA250 为 {deviation:.2%}，z-score 为 {z_score:.2f}，{direction}。",
        f"基础权益仓位 {base_equity:.0%}，最终权益仓位 {target_equity:.0%}，权益部分四 ETF 等权，剩余进入 511880。",
    ]
    if spec.risk_controlled:
        if guard_active:
            drivers.append(f"风控触发：等权净值低于 MA250 且 MA250 的 60 日斜率 {ma_slope:.2%} 为负，最高权益仓位压到 {spec.downtrend_cap:.0%}。")
        else:
            drivers.append(f"风控未触发：MA250 的 60 日斜率为 {ma_slope:.2%}，未限制基础仓位。")
    else:
        drivers.append("基础版不做趋势过滤，用于观察纯均值回归规则本身的收益和回撤。")
    return drivers


def run_equal_weight_reversion_backtest(
    spec: EqualWeightReversionSpec,
    price_history: Mapping[str, pd.DataFrame],
    *,
    start_date: str,
    end_date: str,
    rebalance_every_sessions: int = 20,
) -> dict[str, object]:
    asset_lookup = _asset_map(spec)
    returns = _returns_matrix(price_history)
    required_codes = [*spec.risky_codes, spec.cash_code]
    missing_codes = [code for code in required_codes if code not in returns.columns]
    if missing_codes:
        raise ValueError(f"missing equal-weight reversion ETF history: {', '.join(missing_codes)}")

    indicator = _build_indicator_frame(returns, spec)
    dates = [
        date_text for date_text in sorted(date for date in returns.index.astype(str) if start_date <= date <= end_date)
        if date_text in indicator.index and all(pd.notna(returns.loc[date_text, code]) for code in required_codes)
    ]
    if not dates:
        raise ValueError("no overlapping dates with complete equal-weight reversion inputs")

    current_weights: dict[str, float] = {}
    pending_turnover = 0.0
    last_rebalance_index = -max(1, rebalance_every_sessions)
    daily_records: list[dict[str, object]] = []
    signal_records: list[dict[str, object]] = []
    last_target_equity: float | None = None

    for index, date_text in enumerate(dates):
        day_returns = returns.loc[date_text].fillna(0.0)
        indicator_row = indicator.loc[date_text]
        if current_weights:
            strategy_return = sum(float(weight) * float(day_returns.get(code, 0.0)) for code, weight in current_weights.items())
            record = {
                "date": date_text,
                "strategy_return": strategy_return,
                "equal_weight_return": float(indicator_row["equal_weight_return"]),
                "turnover": pending_turnover,
                "applied_weights": dict(current_weights),
                "equal_weight_equity_indicator": float(indicator_row["equal_weight_equity"]),
                "ma_equity": float(indicator_row["ma_equity"]) if pd.notna(indicator_row["ma_equity"]) else None,
                "deviation": float(indicator_row["deviation"]) if pd.notna(indicator_row["deviation"]) else None,
                "z_score": float(indicator_row["z_score"]) if pd.notna(indicator_row["z_score"]) else None,
                "ma_slope": float(indicator_row["ma_slope"]) if pd.notna(indicator_row["ma_slope"]) else None,
                "target_equity": last_target_equity,
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
        z_score = indicator_row.get("z_score")
        ma_equity = indicator_row.get("ma_equity")
        ma_slope = indicator_row.get("ma_slope")
        deviation = indicator_row.get("deviation")
        equal_weight_equity = indicator_row.get("equal_weight_equity")
        if should_rebalance and all(pd.notna(value) for value in (z_score, ma_equity, ma_slope, deviation, equal_weight_equity)):
            base_equity, signal = _target_equity_from_z(float(z_score))
            guard_active = False
            target_equity = base_equity
            if (
                spec.risk_controlled
                and float(equal_weight_equity) < float(ma_equity)
                and float(ma_slope) < 0
                and target_equity > spec.downtrend_cap
            ):
                target_equity = spec.downtrend_cap
                signal = "reversion_guard_cap"
                guard_active = True
            new_weights = _weights_for_signal(spec, target_equity=target_equity)
            pending_turnover = _target_turnover(current_weights, new_weights)
            current_weights = dict(new_weights)
            last_target_equity = target_equity
            last_rebalance_index = index
            drivers = _signal_detail(
                spec,
                date_text=date_text,
                signal=signal,
                base_equity=base_equity,
                target_equity=target_equity,
                z_score=float(z_score),
                deviation=float(deviation),
                ma_slope=float(ma_slope),
                guard_active=guard_active,
            )
            signal_records.append(
                {
                    "date": date_text,
                    "apply_from_next_session": True,
                    "strategy_signal": signal,
                    "target_weights": dict(current_weights),
                    "turnover_to_target": pending_turnover,
                    "target_equity": round(float(target_equity), 6),
                    "base_equity": round(float(base_equity), 6),
                    "z_score": round(float(z_score), 6),
                    "deviation": round(float(deviation), 6),
                    "ma_slope": round(float(ma_slope), 6),
                    "top_candidates": _top_candidates(
                        spec,
                        target_equity=target_equity,
                        z_score=float(z_score),
                        deviation=float(deviation),
                    ),
                    "rebalance_reason": {
                        "label": signal,
                        "detail": drivers[0],
                        "drivers": drivers,
                    },
                }
            )

    frame = pd.DataFrame(daily_records)
    if frame.empty:
        raise ValueError("no equal-weight reversion backtest returns generated")

    return_columns = ["strategy_return", "equal_weight_return", *[_benchmark_return_column(code) for code in spec.benchmark_codes]]
    for column in return_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
        frame[column.replace("_return", "_equity")] = (1.0 + frame[column]).cumprod()

    primary = performance_metrics(frame["strategy_return"], benchmark_returns=frame["equal_weight_return"], turnover=frame["turnover"])
    strategy_total = compound_return(frame["strategy_return"])
    strategy_drawdown = max_drawdown(frame["strategy_equity"])
    equal_total = compound_return(frame["equal_weight_return"])
    equal_drawdown = max_drawdown(frame["equal_weight_equity"])

    comparison_assets = []
    for code in spec.benchmark_codes:
        asset = asset_lookup.get(code)
        comparison_assets.append(
            _comparison_row(
                code=code,
                name=asset.name if asset else code,
                group=asset.group if asset else "基准",
                label=asset.label if asset else code,
                returns=frame[_benchmark_return_column(code)],
                equity=frame[_benchmark_equity_column(code)],
                strategy_total=strategy_total,
                strategy_drawdown=strategy_drawdown,
            )
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
        "latest_z_score": latest_signal.get("z_score"),
        "latest_deviation": latest_signal.get("deviation"),
        "latest_target_equity": latest_signal.get("target_equity"),
        "comparison_assets": comparison_assets,
    }
    for item in comparison_assets:
        if item["code"] == "equal_weight":
            continue
        key = _benchmark_key(str(item["code"]))
        summary[f"benchmark_{key}_return"] = item["total_return"]
        summary[f"benchmark_{key}_max_drawdown"] = item["max_drawdown"]
        summary[f"alpha_vs_{key}"] = item["return_advantage"]

    indicator_frame = frame[
        ["date", "equal_weight_equity_indicator", "ma_equity", "deviation", "z_score", "ma_slope", "target_equity"]
    ].rename(columns={"equal_weight_equity_indicator": "equal_weight_equity"})

    return {
        "metadata": {
            "engine": "Equal-Weight ETF Mean Reversion Backtest",
            "strategy_id": spec.strategy_id,
            "description": spec.description,
            "method": spec.method,
            "universe": [
                {"code": asset.code, "name": asset.name, "group": asset.group, "label": asset.label}
                for asset in spec.universe
            ],
            "risky_codes": list(spec.risky_codes),
            "cash_code": spec.cash_code,
            "indicator": "equal_weight_ma_reversion",
            "ma_window": spec.ma_window,
            "z_window": spec.z_window,
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
        "indicator_curve": _indicator_records(indicator_frame),
        "signals": signal_records,
        "validation": {
            "alpha_positive_vs_equal_weight": summary["alpha_vs_equal_weight"] > 0,
            "alpha_positive_vs_primary_benchmark": (primary.get("excess_return") or 0) > 0,
            "stable_signal_count": len(signal_records),
            "effective_start_after_first_signal": summary["start_date"],
            "mean_reversion_signal": True,
            "risk_controlled": spec.risk_controlled,
            "not_guaranteed_profit": True,
        },
    }
