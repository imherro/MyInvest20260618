from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
from typing import Any, Iterable

from config.settings import PROJECT_ROOT


FACTOR_VERSION = "v3"
SNAPSHOT_DIR = PROJECT_ROOT / "data" / "frozen" / "snapshots"


def stable_hash(value: Any, length: int = 16) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def build_universe_hash(codes: Iterable[str]) -> str:
    return stable_hash(sorted(str(code) for code in codes))


def create_snapshot(
    *,
    trading_date: str,
    data_version: str,
    universe_hash: str,
    source: str,
    mock_mode: bool,
    results: Any,
    persist: bool = True,
) -> dict[str, Any]:
    snapshot_body = {
        "trading_date": trading_date,
        "data_version": data_version,
        "factor_version": FACTOR_VERSION,
        "universe_hash": universe_hash,
        "source": source,
        "mock_mode": mock_mode,
        "results": results,
    }
    snapshot_id = stable_hash(snapshot_body, length=20)
    snapshot = {
        "snapshot_id": snapshot_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **snapshot_body,
    }

    if persist:
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        snapshot_path = SNAPSHOT_DIR / f"{snapshot_id}.json"
        if not snapshot_path.exists():
            snapshot_path.write_text(
                json.dumps(snapshot, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    return {
        "snapshot_id": snapshot_id,
        "factor_version": FACTOR_VERSION,
        "universe_hash": universe_hash,
        "snapshot_saved": persist,
    }
