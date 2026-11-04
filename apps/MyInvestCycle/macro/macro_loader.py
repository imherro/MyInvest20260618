from __future__ import annotations

import csv
import json
from pathlib import Path
import re
from typing import Iterable

from config import DATA_DIR
from macro.indicator_registry import get_all_indicators
from macro.schema import MacroIndicatorRecord, normalize_date


DEFAULT_MACRO_INDICATORS = get_all_indicators()

DEFAULT_MACRO_DATA_DIR = DATA_DIR / "macro"


def _safe_indicator_name(indicator: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", indicator.strip())


def _records_from_json(path: Path) -> list[dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        records = payload.get("records", [])
        if isinstance(records, list):
            return [item for item in records if isinstance(item, dict)]
    raise ValueError(f"Unsupported macro JSON structure: {path}")


def _records_from_csv(path: Path) -> list[dict[str, object]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_record_payloads(path: Path) -> list[dict[str, object]]:
    if path.suffix.lower() == ".json":
        return _records_from_json(path)
    if path.suffix.lower() == ".csv":
        return _records_from_csv(path)
    return []


def _candidate_paths(indicator: str, data_dir: Path) -> list[Path]:
    safe = _safe_indicator_name(indicator)
    return [
        data_dir / f"{safe}.json",
        data_dir / f"{safe}.csv",
        data_dir / "macro_indicators.json",
        data_dir / "macro_indicators.csv",
    ]


def _load_local_payloads(indicator: str, data_dir: Path) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    for path in _candidate_paths(indicator, data_dir):
        if not path.exists():
            continue
        records = _read_record_payloads(path)
        payloads.extend(item for item in records if str(item.get("indicator", "")).strip() == indicator)
    return payloads


def _coerce_records(payloads: Iterable[dict[str, object]]) -> list[MacroIndicatorRecord]:
    records: list[MacroIndicatorRecord] = []
    for payload in payloads:
        records.append(MacroIndicatorRecord.from_mapping(payload))
    return records


def load_macro_indicator(
    indicator: str,
    start_date: str | int,
    end_date: str | int,
    *,
    data_dir: str | Path = DEFAULT_MACRO_DATA_DIR,
) -> list[MacroIndicatorRecord]:
    """Load one macro indicator from local cache.

    The loader is intentionally local-cache first. Tushare/FRED adapters can add
    records into the same schema later without changing callers.
    """
    start = normalize_date(start_date)
    end = normalize_date(end_date)
    if start > end:
        raise ValueError("start_date must be earlier than or equal to end_date.")

    records = _coerce_records(_load_local_payloads(indicator, Path(data_dir)))
    selected = [
        record
        for record in records
        if record.indicator == indicator and start <= record.observation_date <= end
    ]
    return sorted(selected, key=lambda item: (item.observation_date, item.release_date, item.effective_date))


def load_macro_indicators(
    indicators: Iterable[str],
    start_date: str | int,
    end_date: str | int,
    *,
    data_dir: str | Path = DEFAULT_MACRO_DATA_DIR,
) -> dict[str, list[MacroIndicatorRecord]]:
    return {
        indicator: load_macro_indicator(indicator, start_date, end_date, data_dir=data_dir)
        for indicator in indicators
    }
