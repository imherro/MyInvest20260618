"""Copy inventoried report fixtures and consistent DB backups into test sandboxes."""
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

from source_copy import ROOT


def copy_fixtures(system, original, destination):
    snapshot = json.loads((ROOT / "docs/migration/source-snapshot.json").read_text(encoding="utf-8"))
    project = next(p for p in snapshot["projects"] if p["id"] == system["id"])
    records = []
    for entry in project["excluded"]:
        relative = Path(entry["path"])
        if entry["reason"] != "runtime-data-retained-in-original" or relative.parts[0] not in {"data", "research", "reports", "output"}:
            continue
        if "private" in relative.parts or relative.suffix not in {".json", ".jsonl", ".csv", ".md", ".html"}:
            continue
        source = original / relative
        if not source.is_file() or source.is_symlink() or not source.resolve().is_relative_to(original.resolve()):
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        records.append({"path": relative.as_posix(), "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
    databases = {"etf": "data/local/myinvestetf.sqlite", "stock": "data/local/myinveststock.sqlite",
                 "shadow": "data/shadow_account.sqlite"}
    if system["id"] in databases:
        relative = Path(databases[system["id"]])
        source = original / relative
        if source.is_file():
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True) as reader, sqlite3.connect(target) as writer:
                reader.backup(writer)
            records.append({"path": relative.as_posix(), "method": "read-only SQLite backup", "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
    if system["id"] == "ten":
        for source in (original / "reports").glob("task*_summary.json"):
            relative = source.relative_to(original)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            records.append({"path": relative.as_posix(), "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
    return records
