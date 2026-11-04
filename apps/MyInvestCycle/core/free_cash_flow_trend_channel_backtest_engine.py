from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
import pandas as pd

from core.alpha_validation_engine import compound_return, max_drawdown, performance_metrics
from core.etf_return_utils import coerce_price_frame, daily_return_series
from core.strategy_suite_backtest_engine import Asset


FREE_CASH_FLOW_PRIMARY_CODE = "480092.CNI"
CSI500_BENCHMARK_CODE = "000905.SH"

INDEX_RETURN_SOURCE = (
    "Tushare index_daily for 480092.CNI 国证自由现金流R指数. "
    "The same total-return series is used for channel signals, strategy returns, and the primary benchmark."
)


@dataclass(frozen=True)
class FreeCashFlowTrendSpec:
    strategy_id: str
    name: str
    short_name: str
    description: str
    method: list[str]
    index_code: str
    benchmark_codes: tuple[str, ...]
    reduce_exposure: float
    upper_signal: str
    pivot_window: int = 20
    min_pivots: int = 3
    max_pivots: int = 8
    min_tolerance: float = 0.025
    max_tolerance: float = 0.08
    vol_window: int = 60
    vol_horizon_sessions: int = 20
    vol_multiplier: float = 0.5
    warmup_calendar_days: int = 1800
    backtest_start_date: str = "20160101"
    channel_start_date: str = "20160101"
    lower_anchor_dates: tuple[str, ...] = ("20160128", "20211116", "20240911", "20250407", "20260626")
    upper_residual_end_date: str = "20260101"
    upper_residual_quantile: float = 0.985
    upper_position_threshold: float = 0.75
    lower_position_threshold: float = 0.25
    exposure_step: float = 0.05
    use_ladder_sizing: bool = True


FREE_CASH_FLOW_UNIVERSE = (
    Asset(FREE_CASH_FLOW_PRIMARY_CODE, "国证自由现金流R指数", "自由现金流R"),
    Asset("CASH", "现金", "现金/空仓"),
)


FREE_CASH_FLOW_TREND_SPECS: dict[str, FreeCashFlowTrendSpec] = {
    "free-cash-flow-trend-half": FreeCashFlowTrendSpec(
        strategy_id="free-cash-flow-trend-half",
        name="自由现金流趋势通道策略（半仓防守版）",
        short_name="自由现金流半仓",
        description="用自由现金流指数 2016 低点以来的对数直线趋势通道，上轨附近降到半仓，下轨附近恢复满仓。",
        method=[
            "标的、信号轨道和主基准统一使用 480092.CNI 国证自由现金流R指数；不再使用 932365.CSI 价格指数替代。",
            "研究版下轨使用 2016-01-28、2021-11-16、2024-09-11、2025-04-07、2026-06-26 等主要低点，在 log(index) 上拟合一条直线。",
            "上轨不是单独拟合高点，而是在下轨基础上叠加 2026 年前残差的 98.5% 分位；中轨为上下轨在 log 空间的中点。",
            "轨道位置 = (log(价格)-log(下轨)) / (log(上轨)-log(下轨))；>=0.75 视为上轨附近，<=0.25 视为下轨附近。",
            "价格进入上轨附近或触及上轨波动容忍带后，按 5pct 仓位阶梯定卖，最低降到 50%；价格进入下轨附近或触及下轨容忍带后，按 5pct 仓位阶梯定投/加回，最高恢复 100%。该通道包含当前研究锚点，是复盘研究口径，不作为无未来函数实盘信号。",
        ],
        index_code=FREE_CASH_FLOW_PRIMARY_CODE,
        benchmark_codes=(FREE_CASH_FLOW_PRIMARY_CODE, CSI500_BENCHMARK_CODE),
        reduce_exposure=0.50,
        upper_signal="fcf_channel_half_reduce",
    ),
    "free-cash-flow-trend-full": FreeCashFlowTrendSpec(
        strategy_id="free-cash-flow-trend-full",
        name="自由现金流趋势通道策略（满仓/空仓版）",
        short_name="自由现金流空仓",
        description="同样使用自由现金流指数 2016 低点以来的对数直线趋势通道，但上轨附近直接降到 0%。",
        method=[
            "标的、信号轨道和主基准统一使用 480092.CNI 国证自由现金流R指数；不再使用 932365.CSI 价格指数替代。",
            "研究版下轨使用 2016-01-28、2021-11-16、2024-09-11、2025-04-07、2026-06-26 等主要低点，在 log(index) 上拟合一条直线。",
            "上轨不是单独拟合高点，而是在下轨基础上叠加 2026 年前残差的 98.5% 分位；中轨为上下轨在 log 空间的中点。",
            "轨道位置 = (log(价格)-log(下轨)) / (log(上轨)-log(下轨))；>=0.75 视为上轨附近，<=0.25 视为下轨附近。",
            "价格进入上轨附近或触及上轨波动容忍带后，一次性降到 0%；价格进入下轨附近或触及下轨容忍带后，一次性恢复 100%。上下轨触发位是区间，不是单条线；该通道包含当前研究锚点，是复盘研究口径，不作为无未来函数实盘信号。",
        ],
        index_code=FREE_CASH_FLOW_PRIMARY_CODE,
        benchmark_codes=(FREE_CASH_FLOW_PRIMARY_CODE, CSI500_BENCHMARK_CODE),
        reduce_exposure=0.0,
        upper_signal="fcf_channel_full_exit",
        use_ladder_sizing=False,
    ),
}


def _asset_map() -> dict[str, Asset]:
    return {asset.code: asset for asset in FREE_CASH_FLOW_UNIVERSE}


def _benchmark_key(code: str) -> str:
    return code.split(".")[0]


def _benchmark_return_column(code: str) -> str:
    return f"benchmark_{_benchmark_key(code)}_return"


def _benchmark_equity_column(code: str) -> str:
    return f"benchmark_{_benchmark_key(code)}_equity"


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


def _weights(exposure: float) -> dict[str, float]:
    exposure = max(0.0, min(1.0, float(exposure)))
    cash = 1.0 - exposure
    result = {FREE_CASH_FLOW_PRIMARY_CODE: round(exposure, 6)}
    if cash > 0.000001:
        result["CASH"] = round(cash, 6)
    return result


def _target_turnover(previous: Mapping[str, float], current: Mapping[str, float]) -> float:
    keys = set(previous) | set(current)
    return round(sum(abs(float(current.get(key, 0.0)) - float(previous.get(key, 0.0))) for key in keys) / 2.0, 6)


def _confirmed_pivots(prices: pd.Series, *, window: int) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    highs: list[dict[str, object]] = []
    lows: list[dict[str, object]] = []
    values = prices.to_numpy(dtype=float)
    dates = prices.index.astype(str).tolist()
    for index in range(window, len(values) - window):
        segment = values[index - window : index + window + 1]
        current = values[index]
        confirm_index = index + window
        if current >= float(np.nanmax(segment)) and current > float(values[index - 1]) and current >= float(values[index + 1]):
            highs.append(
                {
                    "pivot_index": index,
                    "confirm_index": confirm_index,
                    "date": dates[index],
                    "confirm_date": dates[confirm_index],
                    "price": float(current),
                }
            )
        if current <= float(np.nanmin(segment)) and current < float(values[index - 1]) and current <= float(values[index + 1]):
            lows.append(
                {
                    "pivot_index": index,
                    "confirm_index": confirm_index,
                    "date": dates[index],
                    "confirm_date": dates[confirm_index],
                    "price": float(current),
                }
            )
    return highs, lows


def _fit_log_line(pivots: list[dict[str, object]], *, current_index: int, spec: FreeCashFlowTrendSpec) -> float | None:
    eligible = [pivot for pivot in pivots if int(pivot["confirm_index"]) <= current_index]
    if len(eligible) < spec.min_pivots:
        return None
    selected = eligible[-spec.max_pivots :]
    x = np.array([float(pivot["pivot_index"]) for pivot in selected], dtype=float)
    y = np.log(np.array([float(pivot["price"]) for pivot in selected], dtype=float))
    if len(set(x.tolist())) < 2:
        return None
    slope, intercept = np.polyfit(x, y, 1)
    return float(np.exp(intercept + slope * current_index))


def _tolerance(returns: pd.Series, *, current_date: str, spec: FreeCashFlowTrendSpec) -> float:
    recent = returns.loc[:current_date].dropna().tail(spec.vol_window)
    if len(recent) < max(20, spec.vol_window // 2):
        return spec.min_tolerance
    horizon_vol = float(recent.std() * (spec.vol_horizon_sessions ** 0.5))
    return max(spec.min_tolerance, min(spec.max_tolerance, spec.vol_multiplier * horizon_vol))


def _nearest_anchor(close: pd.Series, anchor_date: str) -> tuple[str, float] | None:
    if close.empty:
        return None
    if anchor_date in close.index:
        return anchor_date, float(close.loc[anchor_date])
    dates = pd.to_datetime(pd.Index(close.index), format="%Y%m%d", errors="coerce")
    target = pd.to_datetime(anchor_date, format="%Y%m%d", errors="coerce")
    if pd.isna(target) or dates.isna().all():
        return None
    deltas = (dates - target).days.to_numpy()
    index = int(np.nanargmin(np.abs(deltas)))
    if abs(float(deltas[index])) > 10:
        return None
    date_text = str(close.index[index])
    return date_text, float(close.iloc[index])


def _build_log_channel(close: pd.Series, spec: FreeCashFlowTrendSpec) -> tuple[pd.DataFrame, dict[str, object]]:
    channel_close = close.loc[close.index >= spec.channel_start_date].astype(float)
    channel_close = channel_close[channel_close > 0]
    if len(channel_close) < 20:
        empty = pd.DataFrame(index=close.index)
        for column in [
            "upper_line",
            "upper_zone_line",
            "mid_line",
            "lower_zone_line",
            "lower_line",
            "channel_position",
            "distance_to_upper",
            "distance_to_mid",
            "distance_to_lower",
        ]:
            empty[column] = np.nan
        return empty, {"anchor_points": [], "status": "insufficient_channel_history"}

    anchors: list[dict[str, object]] = []
    latest_available_date = str(channel_close.index.max())
    for anchor_date in spec.lower_anchor_dates:
        if anchor_date > latest_available_date:
            continue
        match = _nearest_anchor(channel_close, anchor_date)
        if match is None:
            continue
        date_text, price = match
        if anchors and anchors[-1]["date"] == date_text:
            continue
        anchors.append({"date": date_text, "price": price})

    if len(anchors) < 2:
        low_date = str(channel_close.idxmin())
        anchors = [
            {"date": str(channel_close.index[0]), "price": float(channel_close.iloc[0])},
            {"date": low_date, "price": float(channel_close.loc[low_date])},
            {"date": latest_available_date, "price": float(channel_close.iloc[-1])},
        ]

    origin = pd.to_datetime(channel_close.index[0], format="%Y%m%d")
    anchor_dates = pd.to_datetime([item["date"] for item in anchors], format="%Y%m%d")
    anchor_x = ((anchor_dates - origin).days.to_numpy(dtype=float)) / 365.25
    anchor_y = np.log(np.array([float(item["price"]) for item in anchors], dtype=float))
    slope, intercept = np.polyfit(anchor_x, anchor_y, 1)

    channel_dates = pd.to_datetime(channel_close.index, format="%Y%m%d")
    channel_x = ((channel_dates - origin).days.to_numpy(dtype=float)) / 365.25
    lower_log = intercept + slope * channel_x
    price_log = np.log(channel_close.to_numpy(dtype=float))
    residuals = price_log - lower_log
    residual_frame = pd.DataFrame({"date": channel_close.index.astype(str), "residual": residuals})
    pre_2026 = residual_frame[residual_frame["date"] < spec.upper_residual_end_date]["residual"].dropna()
    sample = pre_2026 if len(pre_2026) >= 60 else residual_frame["residual"].dropna()
    offset = float(np.nanquantile(sample.to_numpy(dtype=float), spec.upper_residual_quantile)) if len(sample) else float("nan")
    if not np.isfinite(offset) or offset <= 0:
        offset = float(np.nanmax(residuals)) if len(residuals) else 0.0
    if not np.isfinite(offset) or offset <= 0:
        offset = 0.01

    lower = np.exp(lower_log)
    lower_zone_line = np.exp(lower_log + offset * spec.lower_position_threshold)
    mid = np.exp(lower_log + offset / 2.0)
    upper_zone_line = np.exp(lower_log + offset * spec.upper_position_threshold)
    upper = np.exp(lower_log + offset)
    channel_position = residuals / offset
    channel = pd.DataFrame(
        {
            "upper_line": upper,
            "upper_zone_line": upper_zone_line,
            "mid_line": mid,
            "lower_zone_line": lower_zone_line,
            "lower_line": lower,
            "channel_position": channel_position,
        },
        index=channel_close.index,
    )
    channel["distance_to_upper"] = channel_close / channel["upper_line"] - 1.0
    channel["distance_to_mid"] = channel_close / channel["mid_line"] - 1.0
    channel["distance_to_lower"] = channel_close / channel["lower_line"] - 1.0

    result = pd.DataFrame(index=close.index)
    result = result.join(channel, how="left")
    metadata = {
        "anchor_points": anchors,
        "channel_start_date": spec.channel_start_date,
        "upper_residual_end_date": spec.upper_residual_end_date,
        "upper_residual_quantile": spec.upper_residual_quantile,
        "log_channel_width": offset,
        "channel_width_pct": float(np.exp(offset) - 1.0),
        "log_lower_slope": float(slope),
        "lower_slope_annualized": float(np.exp(slope) - 1.0),
    }
    return result, metadata


def _build_indicator_frame(frame: pd.DataFrame, spec: FreeCashFlowTrendSpec) -> pd.DataFrame:
    prices = coerce_price_frame(frame)
    if prices.empty:
        raise ValueError("no free cash flow index rows available")
    prices = prices.drop_duplicates(subset=["trade_date"], keep="last").sort_values("trade_date")
    close = prices.set_index("trade_date")["close"].astype(float)
    returns = daily_return_series(prices).reindex(close.index).fillna(0.0)
    base_close = float(close.iloc[0])
    channel, channel_metadata = _build_log_channel(close, spec)

    rows: list[dict[str, object]] = []
    for date_text in close.index.astype(str):
        channel_row = channel.loc[date_text] if date_text in channel.index else pd.Series(dtype=float)
        upper = channel_row.get("upper_line")
        upper_zone_line = channel_row.get("upper_zone_line")
        mid = channel_row.get("mid_line")
        lower_zone_line = channel_row.get("lower_zone_line")
        lower = channel_row.get("lower_line")
        position = channel_row.get("channel_position")
        current_close = float(close.loc[date_text])
        tolerance = _tolerance(returns, current_date=date_text, spec=spec)
        valid = (
            upper is not None
            and lower is not None
            and not pd.isna(upper)
            and not pd.isna(lower)
            and float(upper) > float(lower)
            and position is not None
            and not pd.isna(position)
        )
        distance_to_upper = channel_row.get("distance_to_upper") if valid else None
        distance_to_mid = channel_row.get("distance_to_mid") if valid else None
        distance_to_lower = channel_row.get("distance_to_lower") if valid else None
        channel_position = float(position) if valid else None
        near_upper_by_position = bool(
            valid and channel_position is not None and channel_position >= spec.upper_position_threshold
        )
        near_lower_by_position = bool(
            valid and channel_position is not None and channel_position <= spec.lower_position_threshold
        )
        near_upper_by_distance = bool(
            valid and distance_to_upper is not None and not pd.isna(distance_to_upper) and float(distance_to_upper) >= -tolerance
        )
        near_lower_by_distance = bool(
            valid and distance_to_lower is not None and not pd.isna(distance_to_lower) and float(distance_to_lower) <= tolerance
        )
        upper_zone = near_upper_by_position or near_upper_by_distance
        lower_zone = near_lower_by_position or near_lower_by_distance
        rows.append(
            {
                "date": date_text,
                "close": current_close,
                "index_equity": current_close / base_close,
                "upper_line": upper,
                "upper_zone_line": upper_zone_line,
                "mid_line": mid,
                "lower_zone_line": lower_zone_line,
                "lower_line": lower,
                "upper_equity": upper / base_close if upper is not None else None,
                "upper_zone_equity": upper_zone_line / base_close if upper_zone_line is not None else None,
                "mid_equity": mid / base_close if mid is not None else None,
                "lower_zone_equity": lower_zone_line / base_close if lower_zone_line is not None else None,
                "lower_equity": lower / base_close if lower is not None else None,
                "distance_to_upper": distance_to_upper,
                "distance_to_mid": distance_to_mid,
                "distance_to_lower": distance_to_lower,
                "channel_position": channel_position,
                "tolerance": tolerance,
                "upper_position_threshold": spec.upper_position_threshold,
                "lower_position_threshold": spec.lower_position_threshold,
                "near_upper_by_position": near_upper_by_position,
                "near_lower_by_position": near_lower_by_position,
                "near_upper_by_distance": near_upper_by_distance,
                "near_lower_by_distance": near_lower_by_distance,
                "upper_zone": upper_zone,
                "lower_zone": lower_zone,
                "confirmed_high_count": 0,
                "confirmed_low_count": len(channel_metadata.get("anchor_points", [])),
                "benchmark_return": float(returns.loc[date_text]),
            }
        )
    result = pd.DataFrame(rows)
    result.attrs["channel_metadata"] = channel_metadata
    return result


def _clip(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, float(value)))


def _step_down(value: float, step: float) -> float:
    if step <= 0:
        return value
    return np.floor((value + 1e-12) / step) * step


def _step_up(value: float, step: float) -> float:
    if step <= 0:
        return value
    return np.ceil((value - 1e-12) / step) * step


def _upper_ladder_target(row: pd.Series, spec: FreeCashFlowTrendSpec) -> float:
    position = row.get("channel_position")
    scale = 0.0
    if position is not None and not pd.isna(position):
        width = max(1.0 - spec.upper_position_threshold, 1e-9)
        scale = _clip((float(position) - spec.upper_position_threshold) / width, 0.0, 1.0)
    raw_target = 1.0 - scale * (1.0 - spec.reduce_exposure)
    target = _step_down(raw_target, spec.exposure_step)
    if target >= 1.0:
        target = 1.0 - spec.exposure_step
    return round(_clip(target, spec.reduce_exposure, 1.0), 6)


def _lower_ladder_target(row: pd.Series, spec: FreeCashFlowTrendSpec) -> float:
    position = row.get("channel_position")
    scale = 0.0
    if position is not None and not pd.isna(position):
        width = max(spec.lower_position_threshold, 1e-9)
        scale = _clip((spec.lower_position_threshold - float(position)) / width, 0.0, 1.0)
    raw_target = spec.reduce_exposure + scale * (1.0 - spec.reduce_exposure)
    target = _step_up(raw_target, spec.exposure_step)
    if target <= spec.reduce_exposure:
        target = spec.reduce_exposure + spec.exposure_step
    return round(_clip(target, spec.reduce_exposure, 1.0), 6)


def _signal_for_row(row: pd.Series, current_exposure: float, spec: FreeCashFlowTrendSpec) -> tuple[float, str, list[str]]:
    if bool(row.get("upper_zone")) and bool(row.get("lower_zone")):
        return current_exposure, "fcf_channel_hold", ["上下轨距离过近或价格同时触发上下轨容忍带，维持原仓位。"]
    if bool(row.get("upper_zone")):
        target = (
            min(current_exposure, _upper_ladder_target(row, spec))
            if spec.use_ladder_sizing
            else min(current_exposure, spec.reduce_exposure)
        )
        if abs(target - current_exposure) < 0.000001:
            return current_exposure, "fcf_channel_hold", ["已处于当前上轨区域对应仓位，维持原仓位。"]
        if not spec.use_ladder_sizing:
            return target, spec.upper_signal, [
                f"轨道位置 {float(row['channel_position']):.2f}，进入上轨卖出区间，按满仓/空仓规则降至 {target:.0%}。",
            ]
        return target, spec.upper_signal, [
            f"轨道位置 {float(row['channel_position']):.2f}，进入上轨附近，按 {spec.exposure_step:.0%} 仓位阶梯定卖至 {target:.0%}。",
        ]
    if bool(row.get("lower_zone")):
        target = (
            max(current_exposure, _lower_ladder_target(row, spec))
            if spec.use_ladder_sizing
            else max(current_exposure, 1.0)
        )
        if abs(target - current_exposure) < 0.000001:
            return current_exposure, "fcf_channel_hold", ["已处于当前下轨区域对应仓位，维持原仓位。"]
        if not spec.use_ladder_sizing:
            return target, "fcf_channel_full_buy", [
                f"轨道位置 {float(row['channel_position']):.2f}，进入下轨买入区间，按满仓/空仓规则恢复 {target:.0%}。",
            ]
        return target, "fcf_channel_full_buy", [
            f"轨道位置 {float(row['channel_position']):.2f}，进入下轨附近，按 {spec.exposure_step:.0%} 仓位阶梯定投/加回至 {target:.0%}。",
        ]
    return current_exposure, "fcf_channel_hold", ["价格位于趋势通道中部，维持原仓位。"]


def _signal_label(value: str) -> str:
    labels = {
        "fcf_channel_half_reduce": "上轨定卖",
        "fcf_channel_full_exit": "上轨空仓",
        "fcf_channel_full_buy": "下轨买入",
        "fcf_channel_hold": "通道内持有",
    }
    return labels.get(value, value)


def _top_candidates(row: pd.Series, target_exposure: float) -> list[dict[str, object]]:
    return [
        {
            "code": FREE_CASH_FLOW_PRIMARY_CODE,
            "name": "国证自由现金流R指数",
            "group": "自由现金流R",
            "score": round(float(target_exposure), 6),
            "target_weight": round(float(target_exposure), 6),
            "distance_to_upper": None if pd.isna(row.get("distance_to_upper")) else round(float(row["distance_to_upper"]), 6),
            "distance_to_lower": None if pd.isna(row.get("distance_to_lower")) else round(float(row["distance_to_lower"]), 6),
            "channel_position": None if pd.isna(row.get("channel_position")) else round(float(row["channel_position"]), 6),
            "tolerance": round(float(row.get("tolerance", 0.0)), 6),
        },
        {
            "code": "CASH",
            "name": "现金",
            "group": "现金/空仓",
            "score": round(float(1.0 - target_exposure), 6),
            "target_weight": round(float(1.0 - target_exposure), 6),
        },
    ]


def _curve_records(frame: pd.DataFrame, spec: FreeCashFlowTrendSpec) -> list[dict[str, object]]:
    columns = ["date", "strategy_equity", "equal_weight_equity", *[_benchmark_equity_column(code) for code in spec.benchmark_codes]]
    rows = []
    for _, row in frame[columns].iterrows():
        rows.append({key: (str(row[key]) if key == "date" else round(float(row[key]), 6)) for key in columns if key in row})
    return rows


def _return_records(frame: pd.DataFrame, spec: FreeCashFlowTrendSpec) -> list[dict[str, object]]:
    columns = ["date", "strategy_return", "equal_weight_return", "turnover", "target_exposure", *[_benchmark_return_column(code) for code in spec.benchmark_codes]]
    rows = []
    for _, row in frame[columns].iterrows():
        rows.append({key: (str(row[key]) if key == "date" else round(float(row[key]), 8)) for key in columns if key in row})
    return rows


def _indicator_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    columns = [
        "date",
        "index_equity",
        "upper_equity",
        "upper_zone_equity",
        "mid_equity",
        "lower_zone_equity",
        "lower_equity",
        "distance_to_upper",
        "distance_to_mid",
        "distance_to_lower",
        "channel_position",
        "tolerance",
        "target_exposure",
    ]
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


def run_free_cash_flow_trend_backtest(
    spec: FreeCashFlowTrendSpec,
    index_history: Mapping[str, pd.DataFrame],
    *,
    start_date: str,
    end_date: str,
    resolved_index_code: str | None = None,
    resolved_index_type: str = "price",
) -> dict[str, object]:
    source_code = resolved_index_code or spec.index_code
    if source_code not in index_history:
        raise ValueError(f"missing free cash flow index history: {source_code}")
    indicator = _build_indicator_frame(index_history[source_code], spec)
    channel_metadata = dict(indicator.attrs.get("channel_metadata", {}))
    indicator = indicator[(indicator["date"] >= start_date) & (indicator["date"] <= end_date)].copy()
    if indicator.empty:
        raise ValueError("no overlapping free cash flow index dates in backtest window")
    base_close = float(indicator["close"].iloc[0])
    indicator["index_equity"] = indicator["close"].astype(float) / base_close
    indicator["upper_equity"] = indicator["upper_line"].apply(lambda value: None if pd.isna(value) else float(value) / base_close)
    indicator["upper_zone_equity"] = indicator["upper_zone_line"].apply(lambda value: None if pd.isna(value) else float(value) / base_close)
    indicator["mid_equity"] = indicator["mid_line"].apply(lambda value: None if pd.isna(value) else float(value) / base_close)
    indicator["lower_zone_equity"] = indicator["lower_zone_line"].apply(lambda value: None if pd.isna(value) else float(value) / base_close)
    indicator["lower_equity"] = indicator["lower_line"].apply(lambda value: None if pd.isna(value) else float(value) / base_close)

    benchmark_returns_by_code: dict[str, pd.Series] = {
        spec.index_code: indicator.set_index("date")["benchmark_return"].astype(float)
    }
    for code in spec.benchmark_codes:
        if code == spec.index_code:
            continue
        if code not in index_history:
            raise ValueError(f"missing benchmark index history: {code}")
        returns = daily_return_series(index_history[code]).reindex(indicator["date"].astype(str)).fillna(0.0)
        benchmark_returns_by_code[code] = returns.astype(float)

    current_exposure = 1.0
    current_weights = _weights(current_exposure)
    pending_turnover = 0.0
    daily_records: list[dict[str, object]] = []
    signal_records: list[dict[str, object]] = []

    for _, row in indicator.iterrows():
        date_text = str(row["date"])
        benchmark_return = float(row["benchmark_return"])
        strategy_return = current_exposure * benchmark_return
        benchmark_record = {
            _benchmark_return_column(code): float(series.loc[date_text])
            for code, series in benchmark_returns_by_code.items()
        }
        daily_records.append(
            {
                "date": date_text,
                "strategy_return": strategy_return,
                "equal_weight_return": benchmark_return,
                "turnover": pending_turnover,
                "target_exposure": current_exposure,
                "applied_weights": dict(current_weights),
                **benchmark_record,
            }
        )
        pending_turnover = 0.0

        target_exposure, signal, drivers = _signal_for_row(row, current_exposure, spec)
        target_weights = _weights(target_exposure)
        turnover = _target_turnover(current_weights, target_weights)
        if turnover > 0:
            signal_records.append(
                {
                    "date": date_text,
                    "apply_from_next_session": True,
                    "strategy_signal": signal,
                    "target_weights": dict(target_weights),
                    "turnover_to_target": turnover,
                    "top_candidates": _top_candidates(row, target_exposure),
                    "rebalance_reason": {
                        "label": _signal_label(signal),
                        "detail": drivers[0] if drivers else _signal_label(signal),
                        "drivers": drivers,
                    },
                }
            )
            pending_turnover = turnover
            current_exposure = target_exposure
            current_weights = target_weights

    frame = pd.DataFrame(daily_records)
    if frame.empty:
        raise ValueError("no free cash flow trend backtest returns generated")
    return_column = _benchmark_return_column(spec.index_code)
    benchmark_return_columns = [_benchmark_return_column(code) for code in spec.benchmark_codes]
    for column in ["strategy_return", "equal_weight_return", *benchmark_return_columns]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
        frame[column.replace("_return", "_equity")] = (1.0 + frame[column]).cumprod()

    indicator_by_date = indicator.set_index("date")
    frame = frame.join(indicator_by_date[[
        "index_equity",
        "upper_equity",
        "upper_zone_equity",
        "mid_equity",
        "lower_zone_equity",
        "lower_equity",
        "distance_to_upper",
        "distance_to_mid",
        "distance_to_lower",
        "channel_position",
        "tolerance",
    ]], on="date")

    primary = performance_metrics(frame["strategy_return"], benchmark_returns=frame[return_column], turnover=frame["turnover"])
    benchmark_metrics = performance_metrics(frame[return_column])
    strategy_total = compound_return(frame["strategy_return"])
    benchmark_total = compound_return(frame[return_column])
    strategy_drawdown = max_drawdown(frame["strategy_equity"])
    benchmark_drawdown = max_drawdown(frame[_benchmark_equity_column(spec.index_code)])
    latest_signal = signal_records[-1] if signal_records else {}
    latest_indicator = indicator.iloc[-1]
    average_exposure = float(frame["target_exposure"].mean())
    comparison_assets = []
    for code in spec.benchmark_codes:
        return_series = frame[_benchmark_return_column(code)]
        total_return = compound_return(return_series)
        drawdown = max_drawdown(frame[_benchmark_equity_column(code)])
        asset = _benchmark_asset(code)
        comparison_assets.append(
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
    summary = {
        "strategy_id": spec.strategy_id,
        "strategy_name": spec.name,
        "short_name": spec.short_name,
        "start_date": str(frame["date"].iloc[0]),
        "end_date": str(frame["date"].iloc[-1]),
        "sessions": int(len(frame)),
        "rebalance_count": len(signal_records),
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
        "sharpe": primary["sharpe"],
        "max_drawdown": strategy_drawdown,
        "equal_weight_max_drawdown": benchmark_drawdown,
        "hit_rate_vs_primary_benchmark": primary.get("hit_rate"),
        "average_turnover": primary.get("average_turnover"),
        "cumulative_turnover": primary.get("cumulative_turnover"),
        "average_target_exposure": round(average_exposure, 6),
        "latest_signal": latest_signal.get("strategy_signal"),
        "latest_signal_date": latest_signal.get("date"),
        "latest_weights": latest_signal.get("target_weights", _weights(current_exposure)),
        "latest_channel_position": None
        if pd.isna(latest_indicator.get("channel_position"))
        else round(float(latest_indicator["channel_position"]), 6),
        "latest_distance_to_upper": None
        if pd.isna(latest_indicator.get("distance_to_upper"))
        else round(float(latest_indicator["distance_to_upper"]), 6),
        "latest_distance_to_mid": None
        if pd.isna(latest_indicator.get("distance_to_mid"))
        else round(float(latest_indicator["distance_to_mid"]), 6),
        "latest_distance_to_lower": None
        if pd.isna(latest_indicator.get("distance_to_lower"))
        else round(float(latest_indicator["distance_to_lower"]), 6),
        "channel_anchor_points": channel_metadata.get("anchor_points", []),
        "channel_width_pct": round(float(channel_metadata.get("channel_width_pct", 0.0)), 6),
        "channel_lower_slope_annualized": round(float(channel_metadata.get("lower_slope_annualized", 0.0)), 6),
        "channel_upper_residual_quantile": spec.upper_residual_quantile,
        "comparison_assets": comparison_assets,
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
            "method": spec.method,
            "universe": [
                {"code": asset.code, "name": asset.name, "group": asset.group, "label": asset.label}
                for asset in FREE_CASH_FLOW_UNIVERSE
            ],
            "index_code": spec.index_code,
            "resolved_index_code": source_code,
            "resolved_index_type": resolved_index_type,
            "benchmark_codes": list(spec.benchmark_codes),
            "requested_total_return_code": FREE_CASH_FLOW_PRIMARY_CODE,
            "indicator": "free_cash_flow_trend_channel",
            "channel_fit": {
                **channel_metadata,
                "fit_mode": "fixed_log_lower_anchors_plus_pre_2026_residual_quantile",
                "upper_position_threshold": spec.upper_position_threshold,
                "lower_position_threshold": spec.lower_position_threshold,
            },
            "return_source": INDEX_RETURN_SOURCE,
            "signal_timing": "Signal is generated after close on date t and applied starting t+1.",
            "no_lookahead_bias": False,
            "lookahead_note": "The current research channel uses fixed major-low anchors including 2026-06-26. It is useful for visual research and hypothesis testing, not a strict live-trading backtest.",
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
        "indicator_curve": _indicator_records(frame),
        "signals": signal_records,
        "validation": {
            "alpha_positive_vs_equal_weight": summary["alpha_vs_equal_weight"] > 0,
            "alpha_positive_vs_primary_benchmark": (primary.get("excess_return") or 0) > 0,
            "stable_signal_count": len(signal_records),
            "effective_start_after_first_signal": summary["start_date"],
            "trend_channel_signal": True,
            "uses_confirmed_pivots_only": False,
            "uses_fixed_research_channel": True,
            "ex_post_channel_fit": True,
        },
    }
