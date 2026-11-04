from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

from shortterm_trader.config import Settings, ensure_runtime_dirs


CNINDEX_START = "2012-12-31"


@dataclass(frozen=True)
class EtfCompareInstrument:
    code: str
    name: str
    kind: str
    source: str
    color: str


DEFAULT_INSTRUMENTS: tuple[EtfCompareInstrument, ...] = (
    EtfCompareInstrument(
        code="512890.SH",
        name="512890 红利低波ETF",
        kind="etf",
        source="Tushare fund_daily + fund_adj",
        color="#0B6E4F",
    ),
    EtfCompareInstrument(
        code="510500.SH",
        name="510500 中证500ETF",
        kind="etf",
        source="Tushare fund_daily + fund_adj",
        color="#2D6CDF",
    ),
    EtfCompareInstrument(
        code="510300.SH",
        name="510300 沪深300ETF",
        kind="etf",
        source="Tushare fund_daily + fund_adj",
        color="#6B4EFF",
    ),
    EtfCompareInstrument(
        code="159915.SZ",
        name="159915 创业板ETF",
        kind="etf",
        source="Tushare fund_daily + fund_adj",
        color="#DB2777",
    ),
    EtfCompareInstrument(
        code="VIRTUAL_EQUAL_WEIGHT",
        name="虚拟等权ETF",
        kind="synthetic_equal_weight",
        source="512890/510500/510300/159915 等权复权组合",
        color="#111827",
    ),
    EtfCompareInstrument(
        code="480092.CNI",
        name="480092 自由现金流R收益指数",
        kind="index",
        source="CNIndex getIndexDailyData return index close",
        color="#B23A48",
    ),
)


def get_etf_compare_payload(settings: Settings, *, refresh: bool = False) -> dict[str, object]:
    ensure_runtime_dirs(settings)
    instruments = [asdict(item) for item in DEFAULT_INSTRUMENTS]
    series: dict[str, list[dict[str, object]]] = {}
    histories: dict[str, pd.DataFrame] = {}
    errors: list[dict[str, str]] = []
    updated_at = datetime.now().isoformat(timespec="seconds")

    for instrument in DEFAULT_INSTRUMENTS:
        if instrument.kind == "synthetic_equal_weight":
            continue
        try:
            history = load_or_fetch_history(settings, instrument, refresh=refresh)
            histories[instrument.code] = history
            series[instrument.code] = _history_records(history)
        except Exception as exc:
            errors.append({"code": instrument.code, "name": instrument.name, "error": str(exc)})

    synthetic = next(item for item in DEFAULT_INSTRUMENTS if item.kind == "synthetic_equal_weight")
    etf_histories = [histories[item.code] for item in DEFAULT_INSTRUMENTS if item.kind == "etf" and item.code in histories]
    try:
        synthetic_history = _build_equal_weight_history(etf_histories)
        series[synthetic.code] = _history_records(synthetic_history)
    except Exception as exc:
        errors.append({"code": synthetic.code, "name": synthetic.name, "error": str(exc)})

    return {
        "ok": not errors or bool(series),
        "updated_at": updated_at,
        "refresh": refresh,
        "instruments": instruments,
        "series": series,
        "errors": errors,
    }


def load_or_fetch_history(settings: Settings, instrument: EtfCompareInstrument, *, refresh: bool = False) -> pd.DataFrame:
    if instrument.kind == "synthetic_equal_weight":
        raise RuntimeError("Synthetic equal-weight history is computed from ETF histories")
    path = _cache_path(settings, instrument)
    if path.exists() and not refresh:
        return _load_cached_history(path)

    if instrument.kind == "index":
        history = _fetch_cnindex_history(instrument)
    else:
        history = _fetch_tushare_fund(settings, instrument)
    path.parent.mkdir(parents=True, exist_ok=True)
    history.to_csv(path, index=False, encoding="utf-8")
    return history


def _history_records(history: pd.DataFrame) -> list[dict[str, object]]:
    frame = history.sort_values("date").copy()
    output: list[dict[str, object]] = []
    for row in frame.to_dict("records"):
        output.append(
            {
                "date": pd.Timestamp(row["date"]).strftime("%Y-%m-%d"),
                "close": _round_float(row["close"]),
                "value": _round_float(row["value"]),
            }
        )
    return output


def _build_equal_weight_history(histories: list[pd.DataFrame]) -> pd.DataFrame:
    if len(histories) < 2:
        raise RuntimeError("At least two ETF histories are required for equal-weight series")
    returns: list[pd.Series] = []
    all_dates: set[pd.Timestamp] = set()
    for index, history in enumerate(histories):
        window = history.sort_values("date").drop_duplicates("date", keep="last").copy()
        if window.empty:
            continue
        series = window.set_index("date")["value"].astype(float)
        all_dates.update(pd.Timestamp(date) for date in series.index)
        returns.append(series.pct_change().rename(f"asset_{index}"))
    if not returns or not all_dates:
        raise RuntimeError("ETF histories have no usable rows")

    dates = sorted(all_dates)
    value = 1.0
    rows: list[dict[str, object]] = []
    for index, date in enumerate(dates):
        if index > 0:
            available_returns = [float(item.loc[date]) for item in returns if date in item.index and pd.notna(item.loc[date])]
            if available_returns:
                value *= 1.0 + sum(available_returns) / len(available_returns)
        rows.append({"date": date, "close": value, "value": value})
    return _normalize_history(pd.DataFrame(rows))


def _load_cached_history(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, parse_dates=["date"])
    return _normalize_history(frame)


def _fetch_tushare_fund(settings: Settings, instrument: EtfCompareInstrument) -> pd.DataFrame:
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
    return _normalize_history(frame[["date", "close", "value"]])


def _fetch_tushare_yearly(pro: object, method_name: str, ts_code: str) -> pd.DataFrame:
    method = getattr(pro, method_name)
    frames: list[pd.DataFrame] = []
    history_end = datetime.now().strftime("%Y%m%d")
    end_year = int(history_end[:4])
    for year in range(2012, end_year + 1):
        start = f"{year}0101"
        end = history_end if year == end_year else f"{year}1231"
        part = method(ts_code=ts_code, start_date=start, end_date=end)
        if part is not None and not part.empty:
            frames.append(part)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).drop_duplicates(["trade_date"]).sort_values("trade_date")


def _fetch_cnindex_history(instrument: EtfCompareInstrument) -> pd.DataFrame:
    url = "https://hq.cnindex.com.cn/market/market/getIndexDailyData"
    index_code = instrument.code.split(".", 1)[0]
    response = requests.get(
        url,
        params={"indexCode": index_code, "startDate": CNINDEX_START, "endDate": datetime.now().strftime("%Y-%m-%d")},
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


def _normalize_history(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    output["date"] = pd.to_datetime(output["date"], errors="coerce")
    output["close"] = pd.to_numeric(output["close"], errors="coerce")
    output["value"] = pd.to_numeric(output["value"], errors="coerce")
    output = output.dropna(subset=["date", "close", "value"])
    output = output.sort_values("date").drop_duplicates("date", keep="last")
    if output.empty:
        raise RuntimeError("history rows could not be normalized")
    return output.reset_index(drop=True)


def _cache_path(settings: Settings, instrument: EtfCompareInstrument) -> Path:
    safe_code = instrument.code.replace(".", "_")
    return settings.cache_dir / f"etf_compare_{safe_code}.csv"


def _round_float(value: object) -> float:
    number = float(value)
    if not math.isfinite(number):
        return 0.0
    return round(number, 6)
