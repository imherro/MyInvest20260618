from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional convenience dependency
    load_dotenv = None


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"

if load_dotenv is not None:
    load_dotenv(BASE_DIR / ".env")

TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN") or os.getenv("TS_TOKEN")
DEFAULT_INDEX_CODE = os.getenv("DEFAULT_INDEX_CODE", "000001.SH")

# Reserved for the Web phase. The current Task 1 intentionally has no Web UI.
WEB_PORT = int(os.getenv("MYINVEST_WEB_PORT", "8021"))
BREADTH_HISTORY_SAMPLE_SIZE = int(os.getenv("BREADTH_HISTORY_SAMPLE_SIZE", "30"))
