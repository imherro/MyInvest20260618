from __future__ import annotations

from pathlib import Path

import pandas as pd

from tenbagger.reporting import build_task1_report
from tenbagger.schema import STANDARD_COLUMNS, ensure_standard_schema
from tenbagger.storage import ParquetStorage


def test_standard_schema_adds_required_columns() -> None:
    frame = ensure_standard_schema(pd.DataFrame({"ts_code": ["000001.SZ"], "date": ["2026-01-01"]}))

    assert list(frame.columns[: len(STANDARD_COLUMNS)]) == STANDARD_COLUMNS
    assert set(STANDARD_COLUMNS).issubset(frame.columns)


def test_storage_and_report(tmp_path: Path) -> None:
    frame = ensure_standard_schema(
        pd.DataFrame(
            {
                "ts_code": ["000001.SZ", "000001.SZ", "600519.SH"],
                "date": ["2026-01-01", "2026-01-02", "2026-01-02"],
                "open": [1, 2, 3],
                "high": [1, 2, 3],
                "low": [1, 2, 3],
                "close": [1, 2, 3],
                "revenue": [10, 10, 20],
                "net_profit": [1, 1, 2],
                "roe": [5, 5, 10],
                "pe": [8, 8, 18],
                "pb": [1, 1, 4],
                "market_cap": [100, 100, 200],
            }
        )
    )

    storage_result = ParquetStorage(tmp_path / "data").write(frame)
    report = build_task1_report(
        frame,
        {
            "source": "test",
            "requested_codes": ["000001.SZ", "600519.SH"],
            "loaded_codes": ["000001.SZ", "600519.SH"],
            "by_stock_files": storage_result.by_stock_files,
            "by_date_root": storage_result.by_date_root,
            "row_count": storage_result.row_count,
        },
        tmp_path / "reports",
    )

    assert report["stock_count"] == 2
    assert report["row_count"] == 3
    assert (tmp_path / "reports" / "task1_summary.json").exists()
    assert len(list((tmp_path / "data" / "parquet" / "by_stock").glob("*.parquet"))) == 2
