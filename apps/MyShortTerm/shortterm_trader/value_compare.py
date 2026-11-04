from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from shortterm_trader.config import Settings, ensure_runtime_dirs
from shortterm_trader.etf_compare import _build_equal_weight_history, _history_records, _load_cached_history, _normalize_history
from shortterm_trader.index_compare import _fetch_tushare_index


@dataclass(frozen=True)
class ValueCompareInstrument:
    code: str
    name: str
    kind: str
    source: str
    color: str


DEFAULT_VALUE_COMPARE_INSTRUMENTS: tuple[ValueCompareInstrument, ...] = (
    ValueCompareInstrument(
        code="h21052.CSI",
        name="国信价值全收益指数",
        kind="index",
        source="Tushare index_daily",
        color="#7C3AED",
    ),
    ValueCompareInstrument(
        code="CN2296.CNI",
        name="创成长R收益指数",
        kind="index",
        source="Tushare index_daily",
        color="#0F766E",
    ),
    ValueCompareInstrument(
        code="h20269.CSI",
        name="红利低波全收益指数",
        kind="index",
        source="Tushare index_daily",
        color="#D97706",
    ),
    ValueCompareInstrument(
        code="480092.CNI",
        name="自由现金流R收益指数",
        kind="index",
        source="Tushare index_daily",
        color="#B23A48",
    ),
    ValueCompareInstrument(
        code="VIRTUAL_EQUAL_WEIGHT_STRATEGY",
        name="策略等权组合",
        kind="synthetic_equal_weight",
        source="国信价值/创成长R/红利低波/自由现金流R 动态等权",
        color="#111827",
    ),
    ValueCompareInstrument(
        code="VIRTUAL_RISK_PARITY_STRATEGY",
        name="风险平价组合",
        kind="synthetic_risk_parity",
        source="国信价值/创成长R/红利低波/自由现金流R 滚动60日波动率倒数加权",
        color="#2563EB",
    ),
)

VALUE_COMPARE_BACKGROUND = ValueCompareInstrument(
    code="000001.SH",
    name="上证指数",
    kind="background",
    source="Tushare index_daily",
    color="#94A3B8",
)


def get_value_compare_payload(settings: Settings, *, refresh: bool = False) -> dict[str, object]:
    ensure_runtime_dirs(settings)
    instruments = [asdict(item) for item in DEFAULT_VALUE_COMPARE_INSTRUMENTS]
    series: dict[str, list[dict[str, object]]] = {}
    histories: dict[str, pd.DataFrame] = {}
    errors: list[dict[str, str]] = []
    updated_at = datetime.now().isoformat(timespec="seconds")

    for instrument in DEFAULT_VALUE_COMPARE_INSTRUMENTS:
        if instrument.kind.startswith("synthetic_"):
            continue
        try:
            history = load_or_fetch_value_history(settings, instrument, refresh=refresh)
            histories[instrument.code] = history
            series[instrument.code] = _history_records(history)
        except Exception as exc:
            errors.append({"code": instrument.code, "name": instrument.name, "error": str(exc)})

    index_histories = [histories[item.code] for item in DEFAULT_VALUE_COMPARE_INSTRUMENTS if item.kind == "index" and item.code in histories]
    for instrument in DEFAULT_VALUE_COMPARE_INSTRUMENTS:
        if not instrument.kind.startswith("synthetic_"):
            continue
        try:
            if instrument.kind == "synthetic_risk_parity":
                history = _build_risk_parity_history(index_histories)
            else:
                history = _build_equal_weight_history(index_histories)
            series[instrument.code] = _history_records(history)
        except Exception as exc:
            errors.append({"code": instrument.code, "name": instrument.name, "error": str(exc)})

    background_series: list[dict[str, object]] = []
    try:
        background = load_or_fetch_value_history(settings, VALUE_COMPARE_BACKGROUND, refresh=refresh)
        background_series = _history_records(background)
    except Exception as exc:
        errors.append(
            {
                "code": VALUE_COMPARE_BACKGROUND.code,
                "name": VALUE_COMPARE_BACKGROUND.name,
                "error": str(exc),
            }
        )

    return {
        "ok": not errors or bool(series),
        "updated_at": updated_at,
        "refresh": refresh,
        "instruments": instruments,
        "series": series,
        "background": asdict(VALUE_COMPARE_BACKGROUND),
        "background_series": background_series,
        "errors": errors,
    }


def load_or_fetch_value_history(
    settings: Settings, instrument: ValueCompareInstrument, *, refresh: bool = False
) -> pd.DataFrame:
    if instrument.kind.startswith("synthetic_"):
        raise RuntimeError("Synthetic strategy history is computed from index histories")
    path = _cache_path(settings, instrument)
    if path.exists() and not refresh:
        return _load_cached_history(path)

    history = _fetch_tushare_index(settings, instrument)
    path.parent.mkdir(parents=True, exist_ok=True)
    history.to_csv(path, index=False, encoding="utf-8")
    return history


def _cache_path(settings: Settings, instrument: ValueCompareInstrument) -> Path:
    safe_code = instrument.code.replace(".", "_")
    return settings.cache_dir / f"value_compare_{safe_code}.csv"


def _build_risk_parity_history(histories: list[pd.DataFrame], *, window: int = 60) -> pd.DataFrame:
    if len(histories) < 2:
        raise RuntimeError("At least two index histories are required for risk parity series")

    returns: list[pd.Series] = []
    all_dates: set[pd.Timestamp] = set()
    for index, history in enumerate(histories):
        frame = history.sort_values("date").drop_duplicates("date", keep="last").copy()
        if frame.empty:
            continue
        value = frame.set_index("date")["value"].astype(float)
        all_dates.update(pd.Timestamp(date) for date in value.index)
        returns.append(value.pct_change().rename(f"asset_{index}"))
    if not returns or not all_dates:
        raise RuntimeError("Index histories have no usable rows")

    value = 1.0
    trailing_returns: list[list[float]] = [[] for _ in returns]
    rows: list[dict[str, object]] = []
    for row_index, date in enumerate(sorted(all_dates)):
        available: list[tuple[int, float, float]] = []
        for asset_index, series in enumerate(returns):
            if date not in series.index or pd.isna(series.loc[date]):
                continue
            daily_return = float(series.loc[date])
            vol = _trailing_volatility(trailing_returns[asset_index], window)
            available.append((asset_index, daily_return, vol))

        if row_index > 0 and available:
            weights = _inverse_volatility_weights([vol for _, _, vol in available])
            portfolio_return = sum(item[1] * weight for item, weight in zip(available, weights))
            value *= 1.0 + portfolio_return

        rows.append({"date": date, "close": value, "value": value})

        for asset_index, series in enumerate(returns):
            if date in series.index and pd.notna(series.loc[date]):
                daily_return = float(series.loc[date])
                if math.isfinite(daily_return):
                    trailing_returns[asset_index].append(daily_return)

    return _normalize_history(pd.DataFrame(rows))


def _trailing_volatility(values: list[float], window: int) -> float:
    recent = [item for item in values[-window:] if math.isfinite(item)]
    if len(recent) < 20:
        return math.nan
    return float(pd.Series(recent).std(ddof=1))


def _inverse_volatility_weights(volatilities: list[float]) -> list[float]:
    valid = [item for item in volatilities if math.isfinite(item) and item > 1e-9]
    fallback = float(pd.Series(valid).median()) if valid else math.nan
    inverse: list[float] = []
    for vol in volatilities:
        usable = vol if math.isfinite(vol) and vol > 1e-9 else fallback
        inverse.append(1.0 / usable if math.isfinite(usable) and usable > 1e-9 else 1.0)
    total = sum(inverse)
    if total <= 0:
        return [1.0 / len(volatilities)] * len(volatilities)
    return [item / total for item in inverse]
