from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from shortterm_trader.config import Settings, ensure_runtime_dirs
from shortterm_trader.etf_compare import _fetch_tushare_yearly
from shortterm_trader.trend_channels import TrendInstrument, _fetch_cnindex_history


@dataclass(frozen=True)
class CapitalBucket:
    key: str
    name: str
    role: str
    description: str
    color: str


@dataclass(frozen=True)
class CapitalInstrument:
    code: str
    name: str
    bucket: str
    source: str
    color: str
    provider: str = "tushare_index_daily"
    start_year: int = 2012


CAPITAL_BUCKETS: tuple[CapitalBucket, ...] = (
    CapitalBucket("broad", "宽基", "source", "沪深300、中证500、创业板、上证50、中证全指等市场底仓方向。", "#2563EB"),
    CapitalBucket("technology", "科技成长", "target", "AI算力、通信、电子、半导体、新能源和电力设备。", "#7C3AED"),
    CapitalBucket("dividend", "红利现金流", "target", "红利低波、自由现金流等现金流质量和股息方向。", "#15803D"),
    CapitalBucket("cyclical", "周期稳增长", "target", "资源、建材和稳增长修复方向。", "#B45309"),
    CapitalBucket("consumer_health", "消费医药", "target", "消费、传媒、创新药和医药生物。", "#BE185D"),
    CapitalBucket("defensive_cash", "防御现金", "target", "货币ETF、国债ETF等防御和现金替代代理。", "#0F766E"),
)


DEFAULT_CAPITAL_INSTRUMENTS: tuple[CapitalInstrument, ...] = (
    CapitalInstrument("000985.CSI", "中证全指", "broad", "Tushare index_daily", "#0F766E", start_year=2005),
    CapitalInstrument("000300.SH", "沪深300", "broad", "Tushare index_daily", "#DC2626", start_year=2005),
    CapitalInstrument("000905.SH", "中证500", "broad", "Tushare index_daily", "#EA580C", start_year=2005),
    CapitalInstrument("399006.SZ", "创业板指", "broad", "Tushare index_daily", "#DB2777", start_year=2010),
    CapitalInstrument("000016.SH", "上证50", "broad", "Tushare index_daily", "#7C3AED", start_year=2004),
    CapitalInstrument("399363.SZ", "国证算力", "technology", "Tushare index_daily", "#2563EB", start_year=2009),
    CapitalInstrument("000994.CSI", "全指通信", "technology", "Tushare index_daily", "#0891B2", start_year=2011),
    CapitalInstrument("399811.CSI", "CSSW电子", "technology", "Tushare index_daily", "#4F46E5", start_year=2015),
    CapitalInstrument("h30184.CSI", "全指半导体", "technology", "Tushare index_daily", "#9333EA", start_year=2013),
    CapitalInstrument("000941.CSI", "新能源", "technology", "Tushare index_daily", "#16A34A", start_year=2009),
    CapitalInstrument("930683.CSI", "中证500电力设备", "technology", "Tushare index_daily", "#65A30D", start_year=2015),
    CapitalInstrument("h30269.CSI", "红利低波", "dividend", "Tushare index_daily", "#15803D", start_year=2005),
    CapitalInstrument("980092.CNI", "国证自由现金流", "dividend", "CNIndex getIndexDailyData", "#B23A48", "cnindex_daily", 2012),
    CapitalInstrument("000805.CSI", "A股资源", "cyclical", "Tushare index_daily", "#B45309", start_year=2012),
    CapitalInstrument("980048.CNI", "国证建材", "cyclical", "CNIndex getIndexDailyData", "#A16207", "cnindex_daily", 2002),
    CapitalInstrument("000990.CSI", "全指消费", "consumer_health", "Tushare index_daily", "#E11D48", start_year=2011),
    CapitalInstrument("399971.SZ", "中证传媒", "consumer_health", "Tushare index_daily", "#F97316", start_year=2014),
    CapitalInstrument("931152.CSI", "CS创新药", "consumer_health", "Tushare index_daily", "#BE185D", start_year=2019),
    CapitalInstrument("000808.CSI", "医药生物", "consumer_health", "Tushare index_daily", "#0D9488", start_year=2012),
    CapitalInstrument("511880.SH", "银华日利ETF", "defensive_cash", "Tushare fund_daily + fund_adj", "#0F766E", "tushare_fund_daily_adj", 2013),
    CapitalInstrument("511990.SH", "华宝添益ETF", "defensive_cash", "Tushare fund_daily + fund_adj", "#14B8A6", "tushare_fund_daily_adj", 2013),
    CapitalInstrument("511010.SH", "国债ETF", "defensive_cash", "Tushare fund_daily + fund_adj", "#64748B", "tushare_fund_daily_adj", 2013),
)


WINDOWS = (3, 5, 10, 20)
DEFAULT_BENCHMARK = "000985.CSI"


def get_capital_migration_payload(
    settings: Settings,
    *,
    refresh: bool = False,
    window: int = 5,
) -> dict[str, object]:
    ensure_runtime_dirs(settings)
    active_window = window if window in WINDOWS else 5
    histories: dict[str, pd.DataFrame] = {}
    errors: list[dict[str, str]] = []

    for instrument in DEFAULT_CAPITAL_INSTRUMENTS:
        try:
            histories[instrument.code] = load_or_fetch_capital_history(settings, instrument, refresh=refresh)
        except Exception as exc:
            errors.append({"code": instrument.code, "name": instrument.name, "error": str(exc)})

    benchmark_code, benchmark = _select_benchmark(histories)
    instrument_metrics = [
        _instrument_metrics(instrument, histories[instrument.code], benchmark, active_window)
        for instrument in DEFAULT_CAPITAL_INSTRUMENTS
        if instrument.code in histories
    ]
    bucket_metrics = _bucket_metrics(instrument_metrics)
    matrix = _migration_matrix(bucket_metrics)
    flows = [row for row in matrix if row["score"] >= 30]
    flows.sort(key=lambda row: float(row["score"]), reverse=True)

    return {
        "ok": bool(instrument_metrics),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "refresh": refresh,
        "window": active_window,
        "windows": list(WINDOWS),
        "benchmark": benchmark_code,
        "latest_date": _latest_date(histories),
        "style_status": _style_status(flows),
        "proxy_note": "资金迁移雷达当前使用价量承接代理：相对收益、短期动量、回撤修复和成交活跃度。不是资金净流入或交易指令。",
        "buckets": [asdict(item) for item in CAPITAL_BUCKETS],
        "instruments": [asdict(item) for item in DEFAULT_CAPITAL_INSTRUMENTS],
        "instrument_metrics": instrument_metrics,
        "bucket_metrics": bucket_metrics,
        "matrix": matrix,
        "flows": flows[:12],
        "leaders": _leaders(instrument_metrics),
        "series": _bucket_series(histories, benchmark),
        "errors": errors,
    }


def load_or_fetch_capital_history(
    settings: Settings,
    instrument: CapitalInstrument,
    *,
    refresh: bool = False,
) -> pd.DataFrame:
    path = _cache_path(settings, instrument)
    if path.exists() and not refresh:
        return _load_cached_history(path)

    fallback = _fallback_cache_path(settings, instrument)
    if fallback.exists() and not refresh:
        return _load_cached_history(fallback)

    if instrument.provider == "tushare_index_daily":
        history = _fetch_tushare_index_history(settings, instrument)
    elif instrument.provider == "cnindex_daily":
        trend_instrument = TrendInstrument(
            instrument.code,
            instrument.name,
            instrument.bucket,
            instrument.source,
            instrument.color,
            "cnindex_daily",
            instrument.start_year,
        )
        history = _normalize_capital_history(_fetch_cnindex_history(trend_instrument))
    elif instrument.provider == "tushare_fund_daily_adj":
        history = _fetch_tushare_fund_history(settings, instrument)
    else:
        raise RuntimeError(f"Unsupported capital provider: {instrument.provider}")

    path.parent.mkdir(parents=True, exist_ok=True)
    history.to_csv(path, index=False, encoding="utf-8")
    return history


def _instrument_metrics(
    instrument: CapitalInstrument,
    history: pd.DataFrame,
    benchmark: pd.DataFrame | None,
    window: int,
) -> dict[str, object]:
    frame = _normalize_capital_history(history)
    returns = {f"return{item}": _window_return(frame, item) for item in WINDOWS}
    relative_returns = {
        f"relativeReturn{item}": _relative_return(frame, benchmark, item)
        for item in WINDOWS
    }
    active_return = returns.get(f"return{window}")
    active_relative = relative_returns.get(f"relativeReturn{window}")
    amount_ratio = _amount_ratio(frame)
    drawdown = _recent_drawdown(frame, 20)
    acceleration = _acceleration(returns)
    pressure = _outflow_pressure(active_return, active_relative, drawdown, amount_ratio)
    absorption = _absorption_score(active_return, active_relative, acceleration, amount_ratio, instrument.bucket)
    latest = frame.iloc[-1]

    return {
        "code": instrument.code,
        "name": instrument.name,
        "bucket": instrument.bucket,
        "bucketName": _bucket_name(instrument.bucket),
        "source": instrument.source,
        "latestDate": pd.Timestamp(latest["date"]).strftime("%Y-%m-%d"),
        "rows": int(len(frame)),
        "close": _round_float(latest["close"]),
        "value": _round_float(latest["value"]),
        **{key: _round_optional(value) for key, value in returns.items()},
        **{key: _round_optional(value) for key, value in relative_returns.items()},
        "activeReturn": _round_optional(active_return),
        "activeRelativeReturn": _round_optional(active_relative),
        "amountRatio": _round_optional(amount_ratio),
        "drawdown20": _round_optional(drawdown),
        "acceleration": _round_optional(acceleration),
        "outflowPressure": _round_float(pressure),
        "absorptionScore": _round_float(absorption),
        "status": _signal_status(pressure, absorption),
    }


def _bucket_metrics(instrument_metrics: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    output: dict[str, dict[str, object]] = {}
    for bucket in CAPITAL_BUCKETS:
        rows = [item for item in instrument_metrics if item["bucket"] == bucket.key]
        if not rows:
            continue
        absorption_leaders = sorted(rows, key=lambda item: float(item["absorptionScore"]), reverse=True)[:3]
        pressure_leaders = sorted(rows, key=lambda item: float(item["outflowPressure"]), reverse=True)[:3]
        output[bucket.key] = {
            "key": bucket.key,
            "name": bucket.name,
            "role": bucket.role,
            "description": bucket.description,
            "color": bucket.color,
            "count": len(rows),
            "latestDate": max(str(item["latestDate"]) for item in rows),
            "activeReturn": _round_optional(_median([item.get("activeReturn") for item in rows])),
            "activeRelativeReturn": _round_optional(_median([item.get("activeRelativeReturn") for item in rows])),
            "return20": _round_optional(_median([item.get("return20") for item in rows])),
            "amountRatio": _round_optional(_median([item.get("amountRatio") for item in rows])),
            "drawdown20": _round_optional(_median([item.get("drawdown20") for item in rows])),
            "outflowPressure": _round_float(_median([item.get("outflowPressure") for item in rows]) or 0),
            "absorptionScore": _round_float(_median([item.get("absorptionScore") for item in rows]) or 0),
            "status": _signal_status(
                _median([item.get("outflowPressure") for item in rows]) or 0,
                _median([item.get("absorptionScore") for item in rows]) or 0,
            ),
            "absorptionLeaders": [_compact_metric(item) for item in absorption_leaders],
            "pressureLeaders": [_compact_metric(item) for item in pressure_leaders],
        }
    return output


def _migration_matrix(bucket_metrics: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for source in CAPITAL_BUCKETS:
        source_metric = bucket_metrics.get(source.key)
        if not source_metric:
            continue
        source_pressure = float(source_metric["outflowPressure"])
        for target in CAPITAL_BUCKETS:
            if target.key == source.key:
                continue
            target_metric = bucket_metrics.get(target.key)
            if not target_metric:
                continue
            target_absorption = float(target_metric["absorptionScore"])
            score = _migration_score(source_pressure, target_absorption)
            output.append(
                {
                    "source": source.key,
                    "sourceName": source.name,
                    "target": target.key,
                    "targetName": target.name,
                    "score": _round_float(score),
                    "sourcePressure": _round_float(source_pressure),
                    "targetAbsorption": _round_float(target_absorption),
                    "label": _migration_label(score),
                }
            )
    output.sort(key=lambda row: (str(row["sourceName"]), -float(row["score"])))
    return output


def _bucket_series(histories: dict[str, pd.DataFrame], benchmark: pd.DataFrame | None) -> dict[str, list[dict[str, object]]]:
    if benchmark is None:
        return {}
    benchmark_frame = _normalize_capital_history(benchmark).set_index("date")["value"].astype(float)
    output: dict[str, list[dict[str, object]]] = {}
    for bucket in CAPITAL_BUCKETS:
        columns: list[pd.Series] = []
        for instrument in DEFAULT_CAPITAL_INSTRUMENTS:
            if instrument.bucket != bucket.key or instrument.code not in histories:
                continue
            frame = _normalize_capital_history(histories[instrument.code]).set_index("date")["value"].astype(float)
            joined = pd.concat([frame.rename("asset"), benchmark_frame.rename("benchmark")], axis=1, join="inner").dropna()
            if len(joined) < 2:
                continue
            window = joined.tail(90).copy()
            rel = (window["asset"] / float(window["asset"].iloc[0])) / (
                window["benchmark"] / float(window["benchmark"].iloc[0])
            ) - 1
            columns.append(rel.rename(instrument.code))
        if not columns:
            continue
        bucket_frame = pd.concat(columns, axis=1).sort_index()
        median = bucket_frame.median(axis=1, skipna=True).dropna()
        output[bucket.key] = [
            {"date": pd.Timestamp(date).strftime("%Y-%m-%d"), "relativeStrength": _round_float(value)}
            for date, value in median.items()
        ]
    return output


def _leaders(instrument_metrics: list[dict[str, object]]) -> list[dict[str, object]]:
    rows = sorted(instrument_metrics, key=lambda item: float(item["absorptionScore"]), reverse=True)
    return [_compact_metric(item) for item in rows[:10]]


def _compact_metric(item: dict[str, object]) -> dict[str, object]:
    return {
        "code": item["code"],
        "name": item["name"],
        "bucket": item["bucket"],
        "bucketName": item["bucketName"],
        "activeReturn": item["activeReturn"],
        "activeRelativeReturn": item["activeRelativeReturn"],
        "amountRatio": item["amountRatio"],
        "outflowPressure": item["outflowPressure"],
        "absorptionScore": item["absorptionScore"],
        "status": item["status"],
    }


def _fetch_tushare_index_history(settings: Settings, instrument: CapitalInstrument) -> pd.DataFrame:
    if not settings.tushare_token:
        raise RuntimeError("TUSHARE_TOKEN is not configured")
    try:
        import tushare as ts
    except Exception as exc:  # pragma: no cover - import guard
        raise RuntimeError(f"tushare import failed: {exc}") from exc

    pro = ts.pro_api(settings.tushare_token)
    frames: list[pd.DataFrame] = []
    history_end = datetime.now().strftime("%Y%m%d")
    end_year = int(history_end[:4])
    for year in range(instrument.start_year, end_year + 1):
        start = f"{year}0101"
        end = history_end if year == end_year else f"{year}1231"
        part = pro.index_daily(ts_code=instrument.code, start_date=start, end_date=end)
        if part is not None and not part.empty:
            frames.append(part)
    if not frames:
        raise RuntimeError(f"Tushare returned no index_daily rows for {instrument.code}")

    daily = pd.concat(frames, ignore_index=True).drop_duplicates(["trade_date"]).sort_values("trade_date")
    frame = daily[["trade_date", "close"]].copy()
    frame["date"] = pd.to_datetime(frame["trade_date"], format="%Y%m%d", errors="coerce")
    frame["value"] = pd.to_numeric(frame["close"], errors="coerce")
    if "amount" in daily:
        frame["amount"] = pd.to_numeric(daily["amount"], errors="coerce")
    if "vol" in daily:
        frame["volume"] = pd.to_numeric(daily["vol"], errors="coerce")
    return _normalize_capital_history(frame)


def _fetch_tushare_fund_history(settings: Settings, instrument: CapitalInstrument) -> pd.DataFrame:
    if not settings.tushare_token:
        raise RuntimeError("TUSHARE_TOKEN is not configured")
    try:
        import tushare as ts
    except Exception as exc:  # pragma: no cover - import guard
        raise RuntimeError(f"tushare import failed: {exc}") from exc

    pro = ts.pro_api(settings.tushare_token)
    daily = _fetch_tushare_yearly(pro, "fund_daily", instrument.code)
    if daily.empty:
        raise RuntimeError(f"Tushare returned no fund_daily rows for {instrument.code}")
    adj = _fetch_tushare_yearly(pro, "fund_adj", instrument.code)
    frame = daily[["trade_date", "close"]].copy()
    if not adj.empty and "adj_factor" in adj:
        frame = frame.merge(adj[["trade_date", "adj_factor"]], on="trade_date", how="left")
    else:
        frame["adj_factor"] = 1.0
    frame["date"] = pd.to_datetime(frame["trade_date"], format="%Y%m%d", errors="coerce")
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame["adj_factor"] = pd.to_numeric(frame["adj_factor"], errors="coerce").fillna(1.0)
    frame["value"] = frame["close"] * frame["adj_factor"]
    if "amount" in daily:
        frame["amount"] = pd.to_numeric(daily["amount"], errors="coerce")
    if "vol" in daily:
        frame["volume"] = pd.to_numeric(daily["vol"], errors="coerce")
    return _normalize_capital_history(frame)


def _normalize_capital_history(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    output["date"] = pd.to_datetime(output["date"], errors="coerce")
    output["close"] = pd.to_numeric(output["close"], errors="coerce")
    if "value" not in output:
        output["value"] = output["close"]
    output["value"] = pd.to_numeric(output["value"], errors="coerce")
    for column in ["amount", "volume"]:
        output[column] = pd.to_numeric(output[column], errors="coerce") if column in output else pd.NA
    output = output.dropna(subset=["date", "close", "value"])
    output = output[output["close"] > 0]
    output = output.sort_values("date").drop_duplicates("date", keep="last")
    if output.empty:
        raise RuntimeError("history rows could not be normalized")
    return output[["date", "close", "value", "amount", "volume"]].reset_index(drop=True)


def _load_cached_history(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, parse_dates=["date"])
    return _normalize_capital_history(frame)


def _cache_path(settings: Settings, instrument: CapitalInstrument) -> Path:
    safe_code = instrument.code.replace(".", "_")
    return settings.cache_dir / f"capital_migration_{safe_code}.csv"


def _fallback_cache_path(settings: Settings, instrument: CapitalInstrument) -> Path:
    safe_code = instrument.code.replace(".", "_")
    if instrument.provider == "tushare_fund_daily_adj":
        return settings.cache_dir / f"etf_compare_{safe_code}.csv"
    return settings.cache_dir / f"trend_channel_{safe_code}.csv"


def _select_benchmark(histories: dict[str, pd.DataFrame]) -> tuple[str | None, pd.DataFrame | None]:
    if DEFAULT_BENCHMARK in histories:
        return DEFAULT_BENCHMARK, histories[DEFAULT_BENCHMARK]
    for instrument in DEFAULT_CAPITAL_INSTRUMENTS:
        if instrument.bucket == "broad" and instrument.code in histories:
            return instrument.code, histories[instrument.code]
    return None, None


def _window_return(frame: pd.DataFrame, window: int) -> float | None:
    history = _normalize_capital_history(frame)
    if len(history) <= window:
        return None
    latest = float(history["value"].iloc[-1])
    previous = float(history["value"].iloc[-window - 1])
    if previous <= 0:
        return None
    return latest / previous - 1


def _relative_return(frame: pd.DataFrame, benchmark: pd.DataFrame | None, window: int) -> float | None:
    if benchmark is None:
        return None
    left = _normalize_capital_history(frame)[["date", "value"]].rename(columns={"value": "asset"})
    right = _normalize_capital_history(benchmark)[["date", "value"]].rename(columns={"value": "benchmark"})
    merged = left.merge(right, on="date", how="inner").sort_values("date")
    if len(merged) <= window:
        return None
    asset_previous = float(merged["asset"].iloc[-window - 1])
    benchmark_previous = float(merged["benchmark"].iloc[-window - 1])
    if asset_previous <= 0 or benchmark_previous <= 0:
        return None
    asset_return = float(merged["asset"].iloc[-1]) / asset_previous - 1
    benchmark_return = float(merged["benchmark"].iloc[-1]) / benchmark_previous - 1
    return asset_return - benchmark_return


def _recent_drawdown(frame: pd.DataFrame, window: int) -> float | None:
    history = _normalize_capital_history(frame)
    recent = history.tail(window + 1)
    if recent.empty:
        return None
    peak = float(recent["value"].max())
    latest = float(recent["value"].iloc[-1])
    if peak <= 0:
        return None
    return latest / peak - 1


def _amount_ratio(frame: pd.DataFrame) -> float | None:
    history = _normalize_capital_history(frame)
    basis = history["amount"]
    if basis.dropna().empty:
        basis = history["volume"]
    recent = pd.to_numeric(basis, errors="coerce").tail(20).dropna()
    if len(recent) < 5:
        return None
    median = float(recent.median())
    latest = float(recent.iloc[-1])
    if median <= 0:
        return None
    return latest / median


def _acceleration(returns: dict[str, float | None]) -> float | None:
    ret5 = returns.get("return5")
    ret20 = returns.get("return20")
    if ret5 is None or ret20 is None:
        return None
    return ret5 - ret20 * (5 / 20)


def _outflow_pressure(
    active_return: float | None,
    active_relative: float | None,
    drawdown: float | None,
    amount_ratio: float | None,
) -> float:
    weakness = _clamp01((-(active_relative or 0) + 0.005) / 0.045)
    negative_momentum = _clamp01((-(active_return or 0) + 0.003) / 0.04)
    drawdown_pressure = _clamp01((-(drawdown or 0)) / 0.08)
    activity = _clamp01(((amount_ratio or 1.0) - 1.0) / 0.8) if (active_return or 0) < 0 else 0.0
    return 100 * (0.42 * weakness + 0.28 * negative_momentum + 0.20 * drawdown_pressure + 0.10 * activity)


def _absorption_score(
    active_return: float | None,
    active_relative: float | None,
    acceleration: float | None,
    amount_ratio: float | None,
    bucket: str,
) -> float:
    strength = _clamp01(((active_relative or 0) + 0.004) / 0.045)
    positive_momentum = _clamp01(((active_return or 0) + 0.002) / 0.04)
    improvement = _clamp01(((acceleration or 0) + 0.002) / 0.04)
    activity = _clamp01(((amount_ratio or 1.0) - 1.0) / 0.8) if (active_return or 0) > 0 else 0.0
    defensive_bonus = 10 if bucket == "defensive_cash" and (active_relative or 0) > 0 and (active_return or 0) >= 0 else 0
    return min(100, 100 * (0.42 * strength + 0.28 * positive_momentum + 0.20 * improvement + 0.10 * activity) + defensive_bonus)


def _migration_score(source_pressure: float, target_absorption: float) -> float:
    if source_pressure < 25 or target_absorption < 25:
        return 0
    return (source_pressure * target_absorption) / 100


def _signal_status(pressure: float, absorption: float) -> str:
    if pressure >= 65 and absorption >= 55:
        return "分歧放量"
    if pressure >= 62:
        return "流出压力"
    if absorption >= 62:
        return "承接增强"
    if absorption >= 48:
        return "承接观察"
    if pressure >= 48:
        return "流出观察"
    return "中性"


def _migration_label(score: float) -> str:
    if score >= 70:
        return "强迁移"
    if score >= 50:
        return "迁移观察"
    if score >= 30:
        return "弱迁移"
    return "低"


def _style_status(flows: list[dict[str, object]]) -> str:
    if not flows:
        return "未见强承接"
    top = float(flows[0]["score"])
    if top >= 70:
        return "风格迁移增强"
    if top >= 50:
        return "风格迁移观察"
    return "弱迁移观察"


def _latest_date(histories: dict[str, pd.DataFrame]) -> str:
    dates: list[str] = []
    for history in histories.values():
        frame = _normalize_capital_history(history)
        if not frame.empty:
            dates.append(pd.Timestamp(frame["date"].iloc[-1]).strftime("%Y-%m-%d"))
    return max(dates) if dates else ""


def _bucket_name(key: str) -> str:
    for bucket in CAPITAL_BUCKETS:
        if bucket.key == key:
            return bucket.name
    return key


def _median(values: list[object]) -> float | None:
    numeric = [float(value) for value in values if _is_number(value)]
    if not numeric:
        return None
    return float(pd.Series(numeric).median())


def _is_number(value: object) -> bool:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    return math.isfinite(number)


def _clamp01(value: float) -> float:
    return min(1.0, max(0.0, value))


def _round_float(value: object) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return round(number, 6)


def _round_optional(value: object) -> float | None:
    if not _is_number(value):
        return None
    return _round_float(value)
