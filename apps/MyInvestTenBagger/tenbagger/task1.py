"""TASK 1 orchestration."""

from __future__ import annotations

from pathlib import Path

from tenbagger.config import DEFAULT_DATA_DIR, DEFAULT_REPORT_DIR
from tenbagger.data_loader import TenBaggerDataLoader
from tenbagger.reporting import build_task1_report
from tenbagger.storage import ParquetStorage
from tenbagger.universe import UniverseManager


def run_task1(
    universe_level: str = "dev",
    start_date: str | None = None,
    end_date: str | None = None,
    request_interval: float | None = None,
    data_dir: Path | str = DEFAULT_DATA_DIR,
    report_dir: Path | str = DEFAULT_REPORT_DIR,
) -> dict:
    universe = UniverseManager().resolve(universe_level)
    loader = TenBaggerDataLoader(
        start_date=start_date,
        end_date=end_date,
        request_interval=request_interval,
    )
    load_result = loader.load_all(universe=universe.codes)

    storage_result = ParquetStorage(data_dir).write(load_result.frame)
    storage = {
        "source": load_result.source,
        "universe": universe.to_api(),
        "universe_level": universe.level,
        "universe_count": len(universe.codes),
        "universe_sample": universe.codes[:20],
        "request_interval_seconds": loader.request_interval,
        "requested_codes": load_result.requested_codes,
        "loaded_codes": load_result.loaded_codes,
        "by_stock_files": storage_result.by_stock_files,
        "by_date_root": storage_result.by_date_root,
        "row_count": storage_result.row_count,
        "load_errors": load_result.frame.attrs.get("load_errors", {}),
    }
    return build_task1_report(load_result.frame, storage, report_dir)
