"""Configuration helpers for the TenBagger project."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = REPO_ROOT / "data"
DEFAULT_REPORT_DIR = REPO_ROOT / "reports"

# Kept as a compatibility marker only. Research universes must be built through
# tenbagger.universe.UniverseManager, not from this config module.
DEFAULT_UNIVERSE = "DEV_ONLY"


def load_env_file(path: Path | None = None) -> dict[str, str]:
    """Load simple KEY=VALUE pairs from a local env file without exporting them."""

    env_path = path or REPO_ROOT / ".env"
    values: dict[str, str] = {}
    if not env_path.exists():
        return values

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def get_setting(name: str, default: str | None = None) -> str | None:
    """Return an environment value, falling back to the repo-local `.env` file."""

    return os.getenv(name) or load_env_file().get(name, default)


def compact_date(value: str | date | datetime | None) -> str:
    """Normalize a date-like value to TuShare's YYYYMMDD format."""

    if value is None:
        return date.today().strftime("%Y%m%d")
    if isinstance(value, datetime):
        return value.strftime("%Y%m%d")
    if isinstance(value, date):
        return value.strftime("%Y%m%d")

    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return text
    return datetime.fromisoformat(text).strftime("%Y%m%d")


def default_start_date(days: int = 900) -> str:
    """Default to a long enough window for recent trading and financial data."""

    return (date.today() - timedelta(days=days)).strftime("%Y%m%d")
