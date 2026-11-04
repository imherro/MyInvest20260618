from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - dependency guard
    load_dotenv = None  # type: ignore[assignment]


@dataclass(frozen=True)
class Settings:
    root: Path
    env_file: Path
    data_dir: Path
    cache_dir: Path
    db_path: Path
    reports_dir: Path
    qmt_realtime_path: Path
    qmt_position_snapshot_path: Path
    qmt_position_snapshot_csv_path: Path
    intraday_alert_log_path: Path
    intraday_status_path: Path
    tushare_token: str | None
    fred_api_key: str | None
    qmt_position_export: Path | None
    qmt_sdk_path: Path | None
    qmt_userdata_path: Path | None
    qmt_account_id: str | None
    qmt_realtime_symbols: tuple[str, ...]

    @property
    def has_tushare_token(self) -> bool:
        return bool(self.tushare_token)

    @property
    def has_fred_key(self) -> bool:
        return bool(self.fred_api_key)


def load_settings(root: Path | None = None, env_file: Path | None = None) -> Settings:
    base = (root or Path.cwd()).resolve()
    env_path = (env_file or base / ".env").resolve()
    if env_path.exists():
        if load_dotenv is not None:
            load_dotenv(env_path)
        else:
            _load_simple_env(env_path)

    qmt_export = os.getenv("QMT_POSITION_EXPORT")
    qmt_export_path = Path(qmt_export).expanduser().resolve() if qmt_export else None
    qmt_sdk = os.getenv("QMT_SDK_PATH")
    qmt_sdk_path = Path(qmt_sdk).expanduser().resolve() if qmt_sdk else None
    qmt_userdata = os.getenv("QMT_USERDATA_PATH")
    qmt_userdata_path = Path(qmt_userdata).expanduser().resolve() if qmt_userdata else None
    qmt_account_id = _clean_env("QMT_ACCOUNT_ID")
    qmt_symbols = tuple(
        item.strip().upper()
        for item in (os.getenv("QMT_REALTIME_SYMBOLS") or "").split(",")
        if item.strip()
    )

    data_dir = base / "data"
    cache_dir = data_dir / "cache"
    db_path = data_dir / "shortterm.sqlite"
    qmt_realtime_path = data_dir / "qmt_realtime.json"
    qmt_position_snapshot_path = data_dir / "qmt_positions_latest.json"
    qmt_position_snapshot_csv_path = data_dir / "qmt_positions_latest.csv"
    intraday_alert_log_path = data_dir / "intraday_alerts.jsonl"
    intraday_status_path = data_dir / "intraday_status.json"
    reports_dir = base / "reports"
    return Settings(
        root=base,
        env_file=env_path,
        data_dir=data_dir,
        cache_dir=cache_dir,
        db_path=db_path,
        reports_dir=reports_dir,
        qmt_realtime_path=qmt_realtime_path,
        qmt_position_snapshot_path=qmt_position_snapshot_path,
        qmt_position_snapshot_csv_path=qmt_position_snapshot_csv_path,
        intraday_alert_log_path=intraday_alert_log_path,
        intraday_status_path=intraday_status_path,
        tushare_token=_clean_env("TUSHARE_TOKEN"),
        fred_api_key=_clean_env("FRED_API_KEY"),
        qmt_position_export=qmt_export_path,
        qmt_sdk_path=qmt_sdk_path,
        qmt_userdata_path=qmt_userdata_path,
        qmt_account_id=qmt_account_id,
        qmt_realtime_symbols=qmt_symbols,
    )


def ensure_runtime_dirs(settings: Settings) -> None:
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    settings.reports_dir.mkdir(parents=True, exist_ok=True)


def _clean_env(key: str) -> str | None:
    value = os.getenv(key)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _load_simple_env(path: Path) -> None:
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def redacted_source_status(settings: Settings) -> dict[str, object]:
    return {
        "env_file_exists": settings.env_file.exists(),
        "tushare_token": bool(settings.tushare_token),
        "fred_api_key": bool(settings.fred_api_key),
        "qmt_position_export": str(settings.qmt_position_export)
        if settings.qmt_position_export
        else None,
        "qmt_sdk_path": str(settings.qmt_sdk_path) if settings.qmt_sdk_path else None,
        "qmt_userdata_path": str(settings.qmt_userdata_path) if settings.qmt_userdata_path else None,
        "qmt_account_id": _mask_account_id(settings.qmt_account_id),
        "qmt_realtime_symbols": list(settings.qmt_realtime_symbols),
        "qmt_realtime_path": str(settings.qmt_realtime_path),
        "qmt_position_snapshot_path": str(settings.qmt_position_snapshot_path),
        "intraday_alert_log_path": str(settings.intraday_alert_log_path),
        "intraday_status_path": str(settings.intraday_status_path),
        "db_path": str(settings.db_path),
    }


def _mask_account_id(account_id: str | None) -> str | None:
    if not account_id:
        return None
    if len(account_id) <= 4:
        return "*" * len(account_id)
    return "*" * (len(account_id) - 4) + account_id[-4:]
