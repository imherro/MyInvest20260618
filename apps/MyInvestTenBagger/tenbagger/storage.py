"""Parquet storage helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class StorageResult:
    by_stock_files: list[str]
    by_date_root: str
    row_count: int


class ParquetStorage:
    """Write standard dataframes as both per-stock and date-partitioned parquet."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.by_stock_dir = self.root / "parquet" / "by_stock"
        self.by_date_dir = self.root / "parquet" / "by_date"

    def write(self, df: pd.DataFrame) -> StorageResult:
        if df.empty:
            raise ValueError("Cannot write an empty dataframe to parquet storage.")

        self.by_stock_dir.mkdir(parents=True, exist_ok=True)
        self.by_date_dir.mkdir(parents=True, exist_ok=True)

        by_stock_files: list[str] = []
        normalized = df.copy()
        normalized["date"] = normalized["date"].astype(str)

        for ts_code, stock_df in normalized.groupby("ts_code", sort=True):
            file_name = f"{str(ts_code).replace('.', '_')}.parquet"
            path = self.by_stock_dir / file_name
            stock_df.sort_values("date").to_parquet(path, index=False)
            by_stock_files.append(str(path))

        normalized.to_parquet(
            self.by_date_dir,
            index=False,
            partition_cols=["date"],
            engine="pyarrow",
        )

        return StorageResult(
            by_stock_files=by_stock_files,
            by_date_root=str(self.by_date_dir),
            row_count=len(normalized),
        )
