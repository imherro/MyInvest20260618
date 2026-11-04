from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Iterable

from config import DATA_DIR
from macro.schema import MacroIndicatorRecord


DEFAULT_MACRO_DATA_DIR = DATA_DIR / "macro"


def safe_indicator_name(indicator: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", indicator.strip())


def macro_cache_path(indicator: str, data_dir: str | Path = DEFAULT_MACRO_DATA_DIR) -> Path:
    return Path(data_dir) / f"{safe_indicator_name(indicator)}.json"


def _read_existing_records(path: Path) -> list[MacroIndicatorRecord]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("records", []) if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        return []
    return [MacroIndicatorRecord.from_mapping(item) for item in records if isinstance(item, dict)]


def write_macro_records(
    indicator: str,
    records: Iterable[MacroIndicatorRecord],
    *,
    data_dir: str | Path = DEFAULT_MACRO_DATA_DIR,
    merge: bool = True,
) -> Path:
    path = macro_cache_path(indicator, data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    combined = _read_existing_records(path) if merge else []
    combined.extend(records)

    deduped = {
        (item.indicator, item.observation_date, item.release_date, item.effective_date, item.source): item
        for item in combined
    }
    ordered = sorted(deduped.values(), key=lambda item: (item.observation_date, item.release_date, item.source))
    records_payload = [item.to_dict() for item in ordered]
    if path.exists():
        try:
            existing_payload = json.loads(path.read_text(encoding="utf-8"))
            existing_records = existing_payload.get("records", []) if isinstance(existing_payload, dict) else existing_payload
            if existing_records == records_payload:
                return path
        except (json.JSONDecodeError, OSError):
            pass

    payload = {
        "metadata": {
            "indicator": indicator,
            "records": len(ordered),
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "schema": "MacroIndicatorRecord.v1",
        },
        "records": records_payload,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
