"""Universe data providers."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import pandas as pd

from tenbagger.config import DEFAULT_DATA_DIR, get_setting
from tenbagger.universe.config import DEBUG_FALLBACK_UNIVERSE


class UniverseProvider(Protocol):
    """Provider contract for stock-basic metadata."""

    source: str

    def stock_basic(self) -> pd.DataFrame:
        """Return stock metadata with at least ts_code and name."""


class TushareUniverseProvider:
    """Load current A-share metadata from TuShare with a local cache."""

    source = "tushare_stock_basic"

    def __init__(
        self,
        token: str | None = None,
        cache_dir: Path | str = DEFAULT_DATA_DIR / "universe",
        use_cache: bool = True,
    ) -> None:
        self.token = token or get_setting("TUSHARE_TOKEN")
        self.cache_dir = Path(cache_dir)
        self.use_cache = use_cache

    def stock_basic(self) -> pd.DataFrame:
        cache_path = self.cache_dir / "stock_basic.parquet"
        if self.use_cache and cache_path.exists():
            return pd.read_parquet(cache_path)

        if not self.token:
            raise RuntimeError("TUSHARE_TOKEN is required to build research or production universes.")

        import tushare as ts

        ts.set_token(self.token)
        pro = ts.pro_api()
        fields = "ts_code,symbol,name,area,industry,list_date"
        frame = pro.stock_basic(exchange="", list_status="L", fields=fields)
        if frame.empty:
            raise RuntimeError("TuShare returned an empty stock_basic universe.")

        if self.use_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            frame.to_parquet(cache_path, index=False)
        return frame


class DebugFallbackProvider:
    """Small dev-only provider for machines without TuShare access."""

    source = "debug_fallback_universe"

    def stock_basic(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "ts_code": DEBUG_FALLBACK_UNIVERSE,
                "symbol": [code[:6] for code in DEBUG_FALLBACK_UNIVERSE],
                "name": [f"DEV_{code[:6]}" for code in DEBUG_FALLBACK_UNIVERSE],
                "area": "",
                "industry": "debug",
                "list_date": "20000101",
            }
        )


class StaticUniverseProvider:
    """Test helper provider backed by an in-memory dataframe."""

    source = "static_stock_basic"

    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame

    def stock_basic(self) -> pd.DataFrame:
        return self.frame.copy()
