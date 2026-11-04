from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from shortterm_trader.config import Settings, ensure_runtime_dirs


@dataclass(frozen=True)
class TrendInstrument:
    code: str
    name: str
    group: str
    source: str
    color: str
    provider: str = "tushare_index_daily"
    start_year: int = 2005


BROAD_TREND_INSTRUMENTS: tuple[TrendInstrument, ...] = (
    TrendInstrument("000001.SH", "上证指数", "宽基", "Tushare index_daily", "#2563EB", start_year=1990),
    TrendInstrument("000985.CSI", "中证全指", "宽基", "Tushare index_daily", "#0F766E", start_year=2005),
    TrendInstrument("000016.SH", "上证50", "宽基", "Tushare index_daily", "#7C3AED", start_year=2004),
    TrendInstrument("000300.SH", "沪深300", "宽基", "Tushare index_daily", "#DC2626", start_year=2005),
    TrendInstrument("000905.SH", "中证500", "宽基", "Tushare index_daily", "#EA580C", start_year=2005),
    TrendInstrument("399006.SZ", "创业板指", "宽基", "Tushare index_daily", "#DB2777", start_year=2010),
    TrendInstrument("980092.CNI", "国证自由现金流", "策略", "CNIndex getIndexDailyData", "#B23A48", "cnindex_daily", 2012),
    TrendInstrument("h30269.CSI", "红利低波", "策略", "Tushare index_daily", "#15803D", start_year=2005),
)


THEME_TREND_INSTRUMENTS: tuple[TrendInstrument, ...] = (
    TrendInstrument("000941.CSI", "新能源", "新能源/电力设备", "Tushare index_daily", "#16A34A", start_year=2009),
    TrendInstrument("930683.CSI", "中证500电力设备", "新能源/电力设备", "Tushare index_daily", "#65A30D", start_year=2015),
    TrendInstrument("399363.SZ", "国证算力", "AI算力/通信", "Tushare index_daily", "#2563EB", start_year=2009),
    TrendInstrument("000994.CSI", "全指通信", "AI算力/通信", "Tushare index_daily", "#0891B2", start_year=2011),
    TrendInstrument("399811.CSI", "CSSW电子", "硬科技电子/半导体", "Tushare index_daily", "#4F46E5", start_year=2015),
    TrendInstrument("h30184.CSI", "中证全指半导体", "硬科技电子/半导体", "Tushare index_daily", "#9333EA", start_year=2013),
    TrendInstrument("000805.CSI", "A股资源", "资源周期", "Tushare index_daily", "#B45309", start_year=2012),
    TrendInstrument("h30531.CSI", "精工制造", "高端制造/机器人/军工", "Tushare index_daily", "#334155", start_year=2014),
    TrendInstrument("h30590.CSI", "机器人", "高端制造/机器人/军工", "Tushare index_daily", "#475569", start_year=2015),
    TrendInstrument("399967.SZ", "中证军工", "高端制造/机器人/军工", "Tushare index_daily", "#64748B", start_year=2013),
    TrendInstrument("980048.CNI", "国证建材", "建材/稳增长修复", "CNIndex getIndexDailyData", "#A16207", "cnindex_daily", 2002),
    TrendInstrument("000990.CSI", "全指消费", "消费/传媒", "Tushare index_daily", "#E11D48", start_year=2011),
    TrendInstrument("399971.CSI", "中证传媒", "消费/传媒", "Tushare index_daily", "#F97316", start_year=2014),
    TrendInstrument("931152.CSI", "CS创新药", "创新药/医药", "Tushare index_daily", "#BE185D", start_year=2019),
    TrendInstrument("000808.CSI", "医药生物", "创新药/医药", "Tushare index_daily", "#0D9488", start_year=2012),
)


TREND_CHANNELS: dict[str, tuple[TrendInstrument, ...]] = {
    "broad": BROAD_TREND_INSTRUMENTS,
    "theme": THEME_TREND_INSTRUMENTS,
}

FIT_STARTS = {
    "since2016": pd.Timestamp("2016-01-01"),
    "all": None,
}


def get_trend_channel_payload(
    settings: Settings,
    channel: str,
    *,
    refresh: bool = False,
    fit: str = "since2016",
) -> dict[str, object]:
    if channel not in TREND_CHANNELS:
        raise ValueError(f"Unknown trend channel: {channel}")
    fit_key = fit if fit in FIT_STARTS else "since2016"
    ensure_runtime_dirs(settings)
    instruments = TREND_CHANNELS[channel]
    series: dict[str, list[dict[str, object]]] = {}
    summaries: dict[str, dict[str, object]] = {}
    errors: list[dict[str, str]] = []
    updated_at = datetime.now().isoformat(timespec="seconds")

    for instrument in instruments:
        try:
            history = load_or_fetch_trend_history(settings, instrument, refresh=refresh)
            analysis = _analysis_window(history, fit_key)
            channel_frame, summary = build_trend_channel(analysis)
            series[instrument.code] = _trend_records(channel_frame)
            summaries[instrument.code] = _summary_record(instrument, summary, channel_frame)
        except Exception as exc:
            errors.append({"code": instrument.code, "name": instrument.name, "error": str(exc)})

    return {
        "ok": not errors or bool(series),
        "channel": channel,
        "fit": fit_key,
        "fit_label": "2016年以来" if fit_key == "since2016" else "全历史",
        "updated_at": updated_at,
        "refresh": refresh,
        "instruments": [asdict(item) for item in instruments],
        "series": series,
        "summaries": summaries,
        "errors": errors,
    }


def load_or_fetch_trend_history(settings: Settings, instrument: TrendInstrument, *, refresh: bool = False) -> pd.DataFrame:
    path = _cache_path(settings, instrument)
    if path.exists() and not refresh:
        return _load_cached_history(path)

    if instrument.provider == "cnindex_daily":
        history = _fetch_cnindex_history(instrument)
    elif instrument.provider == "tushare_index_daily":
        history = _fetch_tushare_index(settings, instrument)
    else:
        raise RuntimeError(f"Unsupported provider: {instrument.provider}")
    path.parent.mkdir(parents=True, exist_ok=True)
    history.to_csv(path, index=False, encoding="utf-8")
    return history


def build_trend_channel(history: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float | str | int]]:
    frame = _normalize_history(history)
    if len(frame) < 20:
        raise RuntimeError("At least 20 daily rows are required for trend channel")
    frame = frame[frame["close"] > 0].copy()
    if len(frame) < 20:
        raise RuntimeError("Trend channel requires positive close values")

    first_date = pd.Timestamp(frame["date"].iloc[0])
    x = (frame["date"] - first_date).dt.days.astype(float).to_numpy() / 365.25
    y = np.log(frame["close"].astype(float).to_numpy())
    slope, intercept = np.polyfit(x, y, 1)
    fitted = intercept + slope * x
    residuals = y - fitted
    lower_resid = float(np.nanquantile(residuals, 0.05))
    upper_resid = float(np.nanquantile(residuals, 0.95))
    if not math.isfinite(lower_resid) or not math.isfinite(upper_resid) or upper_resid <= lower_resid:
        center = float(np.nanmedian(residuals))
        width = float(np.nanstd(residuals)) or 0.02
        lower_resid = center - width
        upper_resid = center + width

    frame["trend"] = np.exp(fitted)
    frame["lower"] = np.exp(fitted + lower_resid)
    frame["upper"] = np.exp(fitted + upper_resid)
    channel_width = max(upper_resid - lower_resid, 1e-9)
    frame["channel_position"] = (y - (fitted + lower_resid)) / channel_width
    frame["drawdown"] = frame["close"] / frame["close"].cummax() - 1

    latest = frame.iloc[-1]
    summary: dict[str, float | str | int] = {
        "rows": int(len(frame)),
        "startDate": pd.Timestamp(frame["date"].iloc[0]).strftime("%Y-%m-%d"),
        "endDate": pd.Timestamp(latest["date"]).strftime("%Y-%m-%d"),
        "close": _round_float(latest["close"]),
        "trend": _round_float(latest["trend"]),
        "lower": _round_float(latest["lower"]),
        "upper": _round_float(latest["upper"]),
        "drawdown": _round_float(latest["drawdown"]),
        "maxDrawdown": _round_float(float(frame["drawdown"].min())),
        "channelPosition": _round_float(latest["channel_position"]),
        "distanceToLower": _round_float(latest["close"] / latest["lower"] - 1),
        "distanceToTrend": _round_float(latest["close"] / latest["trend"] - 1),
        "distanceToUpper": _round_float(latest["close"] / latest["upper"] - 1),
        "annualizedTrend": _round_float(math.exp(float(slope)) - 1),
        "status": _position_status(float(latest["channel_position"])),
    }
    return frame.reset_index(drop=True), summary


def _analysis_window(history: pd.DataFrame, fit: str) -> pd.DataFrame:
    frame = _normalize_history(history)
    start = FIT_STARTS.get(fit)
    if start is not None:
        filtered = frame[frame["date"] >= start].copy()
        if len(filtered) >= 20:
            return filtered.reset_index(drop=True)
    return frame.reset_index(drop=True)


def _summary_record(
    instrument: TrendInstrument,
    summary: dict[str, float | str | int],
    channel_frame: pd.DataFrame,
) -> dict[str, object]:
    payload: dict[str, object] = dict(summary)
    payload.update(
        {
            "code": instrument.code,
            "name": instrument.name,
            "group": instrument.group,
            "source": instrument.source,
            "latestDate": pd.Timestamp(channel_frame["date"].iloc[-1]).strftime("%Y-%m-%d"),
        }
    )
    return payload


def _trend_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for row in frame.sort_values("date").to_dict("records"):
        output.append(
            {
                "date": pd.Timestamp(row["date"]).strftime("%Y-%m-%d"),
                "close": _round_float(row["close"]),
                "trend": _round_float(row["trend"]),
                "lower": _round_float(row["lower"]),
                "upper": _round_float(row["upper"]),
                "drawdown": _round_float(row["drawdown"]),
                "channelPosition": _round_float(row["channel_position"]),
            }
        )
    return output


def _fetch_tushare_index(settings: Settings, instrument: TrendInstrument) -> pd.DataFrame:
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
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame["value"] = frame["close"]
    return _normalize_history(frame[["date", "close", "value"]])


def _fetch_cnindex_history(instrument: TrendInstrument) -> pd.DataFrame:
    url = "https://hq.cnindex.com.cn/market/market/getIndexDailyData"
    index_code = instrument.code.split(".", 1)[0]
    response = requests.get(
        url,
        params={
            "indexCode": index_code,
            "startDate": f"{instrument.start_year}-01-01",
            "endDate": datetime.now().strftime("%Y-%m-%d"),
        },
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.cnindex.com.cn/",
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    block = payload.get("data", {})
    item = block.get("item", [])
    rows = block.get("data", [])
    if not rows or "timestamp" not in item or "close" not in item:
        raise RuntimeError(f"CNIndex returned no usable rows for {instrument.code}")

    timestamp_index = item.index("timestamp")
    close_index = item.index("close")
    frame = pd.DataFrame(rows)
    dates = pd.to_datetime(pd.to_numeric(frame[timestamp_index], errors="coerce"), unit="ms", utc=True)
    dates = dates.dt.tz_convert("Asia/Shanghai").dt.tz_localize(None).dt.normalize()
    close = pd.to_numeric(frame[close_index], errors="coerce")
    return _normalize_history(pd.DataFrame({"date": dates, "close": close, "value": close}))


def _load_cached_history(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, parse_dates=["date"])
    return _normalize_history(frame)


def _normalize_history(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    output["date"] = pd.to_datetime(output["date"], errors="coerce")
    output["close"] = pd.to_numeric(output["close"], errors="coerce")
    if "value" not in output:
        output["value"] = output["close"]
    output["value"] = pd.to_numeric(output["value"], errors="coerce")
    output = output.dropna(subset=["date", "close", "value"])
    output = output[output["close"] > 0]
    output = output.sort_values("date").drop_duplicates("date", keep="last")
    if output.empty:
        raise RuntimeError("history rows could not be normalized")
    return output[["date", "close", "value"]].reset_index(drop=True)


def _cache_path(settings: Settings, instrument: TrendInstrument) -> Path:
    safe_code = instrument.code.replace(".", "_")
    return settings.cache_dir / f"trend_channel_{safe_code}.csv"


def _round_float(value: object) -> float:
    number = float(value)
    if not math.isfinite(number):
        return 0.0
    return round(number, 6)


def _position_status(position: float) -> str:
    if position < 0:
        return "跌破下轨"
    if position <= 0.25:
        return "下轨附近"
    if position <= 0.75:
        return "轨道中部"
    if position <= 1:
        return "上轨附近"
    return "突破上轨"
