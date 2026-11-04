from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import re

import pandas as pd

from config.settings import PROJECT_ROOT


class CacheManager:
    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or PROJECT_ROOT / "data" / "cache"

    def get_dataframe(
        self,
        namespace: str,
        key: str,
        max_age_seconds: int | None = None,
    ) -> pd.DataFrame | None:
        path = self._data_path(namespace, key)
        meta_path = self._meta_path(namespace, key)
        if not path.exists():
            return None

        if max_age_seconds is not None and meta_path.exists():
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            created_at = datetime.fromisoformat(metadata["created_at"])
            age = datetime.now(timezone.utc) - created_at
            if age.total_seconds() > max_age_seconds:
                return None

        return pd.read_csv(path, dtype=str)

    def set_dataframe(self, namespace: str, key: str, frame: pd.DataFrame) -> None:
        path = self._data_path(namespace, key)
        meta_path = self._meta_path(namespace, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=False)
        meta_path.write_text(
            json.dumps(
                {
                    "namespace": namespace,
                    "key": key,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "rows": int(len(frame)),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def _data_path(self, namespace: str, key: str) -> Path:
        return self._namespace_dir(namespace) / f"{self._safe_key(key)}.csv"

    def _meta_path(self, namespace: str, key: str) -> Path:
        return self._namespace_dir(namespace) / f"{self._safe_key(key)}.json"

    def _namespace_dir(self, namespace: str) -> Path:
        return self.base_dir / self._safe_name(namespace)

    def _safe_key(self, key: str) -> str:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
        safe = self._safe_name(key)[:80]
        return f"{safe}-{digest}"

    @staticmethod
    def _safe_name(value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_.-]+", "_", value).strip("_") or "default"
