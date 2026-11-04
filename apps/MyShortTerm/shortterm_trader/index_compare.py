from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from shortterm_trader.config import Settings, ensure_runtime_dirs
from shortterm_trader.etf_compare import _build_equal_weight_history, _history_records, _load_cached_history, _normalize_history


@dataclass(frozen=True)
class IndexCompareInstrument:
    code: str
    name: str
    kind: str
    source: str
    color: str


DEFAULT_INDEX_INSTRUMENTS: tuple[IndexCompareInstrument, ...] = (
    IndexCompareInstrument(
        code="h20269.CSI",
        name="红利低波全收益指数",
        kind="index",
        source="Tushare index_daily",
        color="#0B6E4F",
    ),
    IndexCompareInstrument(
        code="h00905.CSI",
        name="中证500全收益指数",
        kind="index",
        source="Tushare index_daily",
        color="#2D6CDF",
    ),
    IndexCompareInstrument(
        code="h00300.CSI",
        name="沪深300全收益指数",
        kind="index",
        source="Tushare index_daily",
        color="#6B4EFF",
    ),
    IndexCompareInstrument(
        code="399606.SZ",
        name="创业板R收益指数",
        kind="index",
        source="Tushare index_daily",
        color="#DB2777",
    ),
    IndexCompareInstrument(
        code="480092.CNI",
        name="自由现金流R收益指数",
        kind="index",
        source="Tushare index_daily",
        color="#B23A48",
    ),
    IndexCompareInstrument(
        code="VIRTUAL_EQUAL_WEIGHT_INDEX",
        name="虚拟等权指数",
        kind="synthetic_equal_weight",
        source="红利低波/中证500/沪深300/创业板R/自由现金流R 动态等权",
        color="#111827",
    ),
)


def get_index_compare_payload(settings: Settings, *, refresh: bool = False) -> dict[str, object]:
    ensure_runtime_dirs(settings)
    instruments = [asdict(item) for item in DEFAULT_INDEX_INSTRUMENTS]
    series: dict[str, list[dict[str, object]]] = {}
    histories: dict[str, pd.DataFrame] = {}
    errors: list[dict[str, str]] = []
    updated_at = datetime.now().isoformat(timespec="seconds")

    for instrument in DEFAULT_INDEX_INSTRUMENTS:
        if instrument.kind == "synthetic_equal_weight":
            continue
        try:
            history = load_or_fetch_index_history(settings, instrument, refresh=refresh)
            histories[instrument.code] = history
            series[instrument.code] = _history_records(history)
        except Exception as exc:
            errors.append({"code": instrument.code, "name": instrument.name, "error": str(exc)})

    synthetic = next(item for item in DEFAULT_INDEX_INSTRUMENTS if item.kind == "synthetic_equal_weight")
    index_histories = [histories[item.code] for item in DEFAULT_INDEX_INSTRUMENTS if item.kind == "index" and item.code in histories]
    try:
        synthetic_history = _build_equal_weight_history(index_histories)
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


def load_or_fetch_index_history(
    settings: Settings, instrument: IndexCompareInstrument, *, refresh: bool = False
) -> pd.DataFrame:
    if instrument.kind == "synthetic_equal_weight":
        raise RuntimeError("Synthetic equal-weight index is computed from index histories")
    path = _cache_path(settings, instrument)
    if path.exists() and not refresh:
        return _load_cached_history(path)

    history = _fetch_tushare_index(settings, instrument)
    path.parent.mkdir(parents=True, exist_ok=True)
    history.to_csv(path, index=False, encoding="utf-8")
    return history


def _fetch_tushare_index(settings: Settings, instrument: IndexCompareInstrument) -> pd.DataFrame:
    if not settings.tushare_token:
        raise RuntimeError("TUSHARE_TOKEN is not configured")
    try:
        import tushare as ts
    except Exception as exc:  # pragma: no cover - import guard
        raise RuntimeError(f"tushare import failed: {exc}") from exc

    pro = ts.pro_api(settings.tushare_token)
    daily = _fetch_tushare_index_yearly(pro, instrument.code)
    if daily.empty:
        raise RuntimeError(f"Tushare returned no index_daily rows for {instrument.code}")

    frame = daily[["trade_date", "close"]].copy()
    frame["date"] = pd.to_datetime(frame["trade_date"], format="%Y%m%d", errors="coerce")
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame["value"] = frame["close"]
    return _normalize_history(frame[["date", "close", "value"]])


def _fetch_tushare_index_yearly(pro: object, ts_code: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    history_end = datetime.now().strftime("%Y%m%d")
    end_year = int(history_end[:4])
    for year in range(2005, end_year + 1):
        start = f"{year}0101"
        end = history_end if year == end_year else f"{year}1231"
        part = pro.index_daily(ts_code=ts_code, start_date=start, end_date=end)
        if part is not None and not part.empty:
            frames.append(part)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).drop_duplicates(["trade_date"]).sort_values("trade_date")


def _cache_path(settings: Settings, instrument: IndexCompareInstrument) -> Path:
    safe_code = instrument.code.replace(".", "_")
    return settings.cache_dir / f"index_compare_{safe_code}.csv"
