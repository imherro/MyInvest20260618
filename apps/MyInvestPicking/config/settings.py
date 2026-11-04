from pathlib import Path
import os


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env"


def _load_env_file() -> None:
    if not ENV_FILE.exists():
        return

    for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


_load_env_file()

APP_NAME = "MyInvestPicking"
APP_VERSION = "0.2.0"
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8019
TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN", "")
FORCE_MOCK_DATA = _env_bool("MYINVESTPICKING_FORCE_MOCK", False)
DEFAULT_TOP_N = 20
MOCK_STOCK_COUNT = 36
