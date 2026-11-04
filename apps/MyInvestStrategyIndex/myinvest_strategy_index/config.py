from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional dependency guard
    load_dotenv = None  # type: ignore[assignment]


@dataclass(frozen=True)
class Settings:
    root: Path
    env_file: Path
    data_dir: Path
    cache_dir: Path
    tushare_token: str | None

    @property
    def has_tushare_token(self) -> bool:
        return bool(self.tushare_token)


def load_settings(root: Path | None = None, env_file: Path | None = None) -> Settings:
    base = (root or Path.cwd()).resolve()
    env_path = (env_file or base / ".env").resolve()
    if env_path.exists():
        if load_dotenv is not None:
            load_dotenv(env_path)
        else:
            _load_simple_env(env_path)

    data_dir = base / "data"
    return Settings(
        root=base,
        env_file=env_path,
        data_dir=data_dir,
        cache_dir=data_dir / "cache",
        tushare_token=_clean_env("TUSHARE_TOKEN"),
    )


def ensure_runtime_dirs(settings: Settings) -> None:
    settings.cache_dir.mkdir(parents=True, exist_ok=True)


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
