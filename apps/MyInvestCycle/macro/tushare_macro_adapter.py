from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

import pandas as pd

from core.data_loader import get_tushare_pro
from macro.indicator_registry import IndicatorDefinition, get_indicator_definition
from macro.schema import MacroIndicatorRecord, normalize_date


@dataclass(frozen=True)
class MacroAdapterResult:
    indicator: str
    records: list[MacroIndicatorRecord]
    source: str
    status: str
    message: str

    def to_dict(self) -> dict[str, object]:
        return {
            "indicator": self.indicator,
            "records": len(self.records),
            "source": self.source,
            "status": self.status,
            "message": self.message,
        }


def _month_range(start_date: str | int, end_date: str | int) -> tuple[str, str]:
    start = pd.to_datetime(normalize_date(start_date), format="%Y%m%d")
    end = pd.to_datetime(normalize_date(end_date), format="%Y%m%d")
    return start.strftime("%Y%m"), end.strftime("%Y%m")


def _extended_month_range(start_date: str | int, end_date: str | int, months: int = 13) -> tuple[str, str]:
    start = pd.to_datetime(normalize_date(start_date), format="%Y%m%d") - pd.DateOffset(months=months)
    end = pd.to_datetime(normalize_date(end_date), format="%Y%m%d")
    return start.strftime("%Y%m"), end.strftime("%Y%m")


def _month_end(month: str) -> pd.Timestamp:
    return pd.Period(str(month), freq="M").end_time.normalize()


def _release_date_for_month(month: str, lag_days: int) -> str:
    return (_month_end(month) + pd.Timedelta(days=lag_days)).strftime("%Y%m%d")


def _in_requested_range(record: MacroIndicatorRecord, start_date: str | int, end_date: str | int) -> bool:
    start = normalize_date(start_date)
    end = normalize_date(end_date)
    return start <= record.observation_date <= end


def _records_from_monthly_frame(
    *,
    indicator: str,
    definition: IndicatorDefinition,
    frame: pd.DataFrame,
    month_column: str,
    value_column: str,
    source: str,
    quality_status: str = "estimated",
) -> list[MacroIndicatorRecord]:
    records: list[MacroIndicatorRecord] = []
    if frame.empty or month_column not in frame.columns or value_column not in frame.columns:
        return records

    for _, row in frame.iterrows():
        raw_value = row.get(value_column)
        if pd.isna(raw_value):
            continue
        month = str(row[month_column])
        observation_date = _month_end(month).strftime("%Y%m%d")
        release_date = _release_date_for_month(month, definition.release_lag_days)
        records.append(
            MacroIndicatorRecord(
                indicator=indicator,
                value=float(raw_value),
                observation_date=observation_date,
                release_date=release_date,
                effective_date=release_date,
                frequency=definition.frequency,
                source=source,
                quality_status=quality_status,
            )
        )
    return records


def _fetch_cn_m(indicator: str, definition: IndicatorDefinition, start_date: str | int, end_date: str | int) -> list[MacroIndicatorRecord]:
    pro = get_tushare_pro()
    start_m, end_m = _month_range(start_date, end_date)
    frame = pro.cn_m(start_m=start_m, end_m=end_m)
    records = _records_from_monthly_frame(
        indicator=indicator,
        definition=definition,
        frame=frame,
        month_column="month",
        value_column=definition.value_field,
        source=f"tushare:{definition.source_detail}",
    )
    return [record for record in records if _in_requested_range(record, start_date, end_date)]


def _fetch_social_financing_growth(
    indicator: str,
    definition: IndicatorDefinition,
    start_date: str | int,
    end_date: str | int,
) -> list[MacroIndicatorRecord]:
    pro = get_tushare_pro()
    start_m, end_m = _extended_month_range(start_date, end_date)
    frame = pro.query("sf_month", start_m=start_m, end_m=end_m)
    if frame.empty or "month" not in frame.columns or "stk_endval" not in frame.columns:
        return []

    data = frame.copy()
    data["month"] = data["month"].astype(str)
    data["stk_endval"] = pd.to_numeric(data["stk_endval"], errors="coerce")
    value_by_month = dict(zip(data["month"], data["stk_endval"], strict=False))
    records: list[MacroIndicatorRecord] = []
    for _, row in data.iterrows():
        month = str(row["month"])
        value = row["stk_endval"]
        if pd.isna(value):
            continue
        prev_month = (pd.Period(month, freq="M") - 12).strftime("%Y%m")
        prev_value = value_by_month.get(prev_month)
        if prev_value is None or pd.isna(prev_value) or float(prev_value) == 0:
            continue
        yoy = (float(value) / float(prev_value) - 1.0) * 100.0
        observation_date = _month_end(month).strftime("%Y%m%d")
        release_date = _release_date_for_month(month, definition.release_lag_days)
        record = MacroIndicatorRecord(
            indicator=indicator,
            value=round(yoy, 6),
            observation_date=observation_date,
            release_date=release_date,
            effective_date=release_date,
            frequency=definition.frequency,
            source=f"tushare:{definition.source_detail}",
            quality_status="estimated",
        )
        if _in_requested_range(record, start_date, end_date):
            records.append(record)
    return records


def _fetch_cpi(indicator: str, definition: IndicatorDefinition, start_date: str | int, end_date: str | int) -> list[MacroIndicatorRecord]:
    pro = get_tushare_pro()
    start_m, end_m = _month_range(start_date, end_date)
    frame = pro.cn_cpi(start_m=start_m, end_m=end_m)
    records = _records_from_monthly_frame(
        indicator=indicator,
        definition=definition,
        frame=frame,
        month_column="month",
        value_column=definition.value_field,
        source=f"tushare:{definition.source_detail}",
    )
    return [record for record in records if _in_requested_range(record, start_date, end_date)]


def _fetch_ppi(indicator: str, definition: IndicatorDefinition, start_date: str | int, end_date: str | int) -> list[MacroIndicatorRecord]:
    pro = get_tushare_pro()
    start_m, end_m = _month_range(start_date, end_date)
    frame = pro.cn_ppi(start_m=start_m, end_m=end_m)
    records = _records_from_monthly_frame(
        indicator=indicator,
        definition=definition,
        frame=frame,
        month_column="month",
        value_column=definition.value_field,
        source=f"tushare:{definition.source_detail}",
    )
    return [record for record in records if _in_requested_range(record, start_date, end_date)]


def _fetch_pmi(indicator: str, definition: IndicatorDefinition, start_date: str | int, end_date: str | int) -> list[MacroIndicatorRecord]:
    pro = get_tushare_pro()
    start_m, end_m = _month_range(start_date, end_date)
    frame = pro.cn_pmi(start_m=start_m, end_m=end_m)
    records = _records_from_monthly_frame(
        indicator=indicator,
        definition=definition,
        frame=frame,
        month_column="MONTH",
        value_column=definition.value_field,
        source=f"tushare:{definition.source_detail}",
    )
    return [record for record in records if _in_requested_range(record, start_date, end_date)]


def _records_from_daily_frame(
    *,
    indicator: str,
    definition: IndicatorDefinition,
    frame: pd.DataFrame,
    date_column: str,
    value_column: str,
    source: str,
    quality_status: str = "valid",
) -> list[MacroIndicatorRecord]:
    records: list[MacroIndicatorRecord] = []
    if frame.empty or date_column not in frame.columns or value_column not in frame.columns:
        return records

    for _, row in frame.iterrows():
        raw_value = row.get(value_column)
        if pd.isna(raw_value):
            continue
        observation_date = normalize_date(row[date_column])
        records.append(
            MacroIndicatorRecord(
                indicator=indicator,
                value=float(raw_value),
                observation_date=observation_date,
                release_date=observation_date,
                effective_date=observation_date,
                frequency=definition.frequency,
                source=source,
                quality_status=quality_status,
            )
        )
    return records


def _daily_query_ranges(start_date: str | int, end_date: str | int, *, years: int = 2) -> list[tuple[str, str]]:
    start = pd.to_datetime(normalize_date(start_date), format="%Y%m%d")
    end = pd.to_datetime(normalize_date(end_date), format="%Y%m%d")
    ranges: list[tuple[str, str]] = []
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + pd.DateOffset(years=years) - pd.Timedelta(days=1), end)
        ranges.append((cursor.strftime("%Y%m%d"), chunk_end.strftime("%Y%m%d")))
        cursor = chunk_end + pd.Timedelta(days=1)
    return ranges


def _concat_daily_queries(query: Callable[..., pd.DataFrame], start_date: str | int, end_date: str | int, **kwargs: object) -> pd.DataFrame:
    frames = []
    for start, end in _daily_query_ranges(start_date, end_date):
        frame = query(start_date=start, end_date=end, **kwargs)
        if frame is not None and not frame.empty:
            frames.append(frame)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).drop_duplicates()


def _fetch_shibor(indicator: str, definition: IndicatorDefinition, start_date: str | int, end_date: str | int) -> list[MacroIndicatorRecord]:
    pro = get_tushare_pro()
    frame = _concat_daily_queries(pro.shibor, start_date, end_date)
    return _records_from_daily_frame(
        indicator=indicator,
        definition=definition,
        frame=frame,
        date_column="date",
        value_column=definition.value_field,
        source=f"tushare:{definition.source_detail}",
    )


def _fetch_cn10y(indicator: str, definition: IndicatorDefinition, start_date: str | int, end_date: str | int) -> list[MacroIndicatorRecord]:
    pro = get_tushare_pro()
    frame = pro.yc_cb(ts_code="1001.CB", start_date=normalize_date(start_date), end_date=normalize_date(end_date))
    value_column = definition.value_field if definition.value_field in frame.columns else ""
    if not value_column:
        candidates = [column for column in frame.columns if "10" in column.lower()]
        value_column = candidates[0] if candidates else ""
    if not value_column:
        return []
    return _records_from_daily_frame(
        indicator=indicator,
        definition=definition,
        frame=frame,
        date_column="trade_date" if "trade_date" in frame.columns else "date",
        value_column=value_column,
        source=f"tushare:{definition.source_detail}",
    )


def _fetch_us10y(indicator: str, definition: IndicatorDefinition, start_date: str | int, end_date: str | int) -> list[MacroIndicatorRecord]:
    pro = get_tushare_pro()
    frame = _concat_daily_queries(pro.us_tycr, start_date, end_date)
    return _records_from_daily_frame(
        indicator=indicator,
        definition=definition,
        frame=frame,
        date_column="date",
        value_column=definition.value_field,
        source=f"tushare:{definition.source_detail}",
    )


def _fetch_usd_cny_proxy(indicator: str, definition: IndicatorDefinition, start_date: str | int, end_date: str | int) -> list[MacroIndicatorRecord]:
    pro = get_tushare_pro()
    frame = _concat_daily_queries(pro.fx_daily, start_date, end_date, ts_code="USDCNH.FXCM")
    return _records_from_daily_frame(
        indicator=indicator,
        definition=definition,
        frame=frame,
        date_column="trade_date",
        value_column=definition.value_field,
        source=f"tushare:{definition.source_detail}:offshore_proxy",
        quality_status="estimated",
    )


FETCHERS: dict[str, Callable[[str, IndicatorDefinition, str | int, str | int], list[MacroIndicatorRecord]]] = {
    "M1_growth": _fetch_cn_m,
    "M2_growth": _fetch_cn_m,
    "social_financing_growth": _fetch_social_financing_growth,
    "PMI": _fetch_pmi,
    "CPI": _fetch_cpi,
    "PPI": _fetch_ppi,
    "SHIBOR": _fetch_shibor,
    "CN10Y": _fetch_cn10y,
    "US10Y": _fetch_us10y,
    "USD_CNH_offshore": _fetch_usd_cny_proxy,
}


def fetch_macro_indicator_from_tushare(
    indicator: str,
    start_date: str | int,
    end_date: str | int,
) -> MacroAdapterResult:
    start = normalize_date(start_date)
    end = normalize_date(end_date)
    if start > end:
        raise ValueError("start_date must be earlier than or equal to end_date.")

    definition = get_indicator_definition(indicator)
    fetcher = FETCHERS.get(indicator)
    if definition.adapter == "none" or fetcher is None:
        return MacroAdapterResult(
            indicator=indicator,
            records=[],
            source=definition.source_detail or definition.source,
            status="missing_adapter",
            message="No verified adapter for this indicator yet.",
        )

    try:
        records = fetcher(indicator, definition, start, end)
    except Exception as exc:  # pragma: no cover - network/permission dependent
        return MacroAdapterResult(
            indicator=indicator,
            records=[],
            source=definition.source_detail,
            status="source_error",
            message=f"{type(exc).__name__}: {str(exc)[:240]}",
        )

    return MacroAdapterResult(
        indicator=indicator,
        records=records,
        source=definition.source_detail,
        status="ok" if records else "no_records",
        message=f"Fetched {len(records)} records at {datetime.now().isoformat(timespec='seconds')}.",
    )
