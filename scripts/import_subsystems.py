"""One-time, non-destructive source snapshot importer. Defaults to inventory only."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECTS = {
    "market": "MyInvestMarket", "theme": "MyInvestTheme", "leader": "MyInvestLeader",
    "etf": "MyInvestETF", "stock": "MyInvestStock", "shadow": "MyInvestShadow",
    "intraday": "MyInvestIntraday", "position": "MyInvestPosition", "cycle": "MyInvestCycle",
    "strategyindex": "MyInvestStrategyIndex", "short": "MyShortTerm",
    "picking": "MyInvestPicking", "ten": "MyInvestTenBagger",
    "taa": "MyInvestTAA", "test": "MyInvestTest",
}
RUNTIME_ROOTS = {"data", "reports", "research", "logs", "temp", "tmp", "runtime", "output", "book"}
EXCLUDED_PARTS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".codex", ".agents"}
CODE_SUFFIXES = {".py", ".js", ".css", ".html", ".ps1", ".sh", ".bat"}


def git(path: Path, *args: str) -> str:
    result = subprocess.run(["git", "-c", "core.quotepath=false", "-C", str(path), *args],
                            capture_output=True, encoding="utf-8", check=False)
    return result.stdout.strip() if result.returncode == 0 else ""


def exclusion(relative: str) -> str | None:
    path = Path(relative)
    if any(part in EXCLUDED_PARTS for part in path.parts):
        return "tooling/runtime"
    if path.name.startswith(".env") and path.name != ".env.example":
        return "credentials"
    if path.suffix.lower() in {".pem", ".key", ".pfx", ".db", ".sqlite", ".sqlite3", ".duckdb", ".epub", ".zip", ".7z", ".pyc", ".log"}:
        return "private/binary/runtime"
    if path.parts[0] == "output":
        return "runtime-data-retained-in-original"
    if path.parts[0] in RUNTIME_ROOTS and path.suffix not in CODE_SUFFIXES:
        return "runtime-data-retained-in-original"
    return None


def inventory(source_root: Path, selected=None, tracked_only=False) -> dict:
    projects = []
    for system_id, name in PROJECTS.items():
        if selected and system_id not in selected:
            continue
        source = source_root / name
        if not (source / ".git").exists():
            raise RuntimeError(f"Missing original repository: {source}")
        files = set(git(source, "ls-files", "-z").split("\0"))
        if not tracked_only:
            files.update(git(source, "ls-files", "--others", "--exclude-standard", "-z").split("\0"))
        included, excluded = [], []
        for relative in sorted(files - {""}):
            path = source / relative
            reason = exclusion(relative)
            if reason:
                excluded.append({"path": relative, "reason": reason})
                continue
            if not path.exists():
                excluded.append({"path": relative, "reason": "locally-deleted"})
                continue
            if path.is_symlink() or not path.resolve().is_relative_to(source.resolve()):
                raise RuntimeError(f"Unsafe source path: {path}")
            content = path.read_bytes()
            if len(content) > 5 * 1024 * 1024:
                raise RuntimeError(f"Large source file needs review: {path}")
            included.append({"path": relative, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()})
        projects.append({"id": system_id, "directory": name, "origin": git(source, "remote", "get-url", "origin"),
                         "source_head": git(source, "rev-parse", "--verify", "HEAD") or None,
                         "source_status": git(source, "status", "--porcelain"),
                         "files": included, "excluded": excluded})
    return {"snapshot_at": datetime.now(timezone.utc).isoformat(), "mode": "working-tree-source-snapshot",
            "original_repositories_modified": False, "services_switched": False, "projects": projects}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=ROOT.parent)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--system", choices=PROJECTS, action="append")
    parser.add_argument("--tracked-only", action="store_true")
    args = parser.parse_args()
    manifest = inventory(args.source_root, args.system, args.tracked_only)
    out = ROOT / "docs" / "migration" / "source-snapshot.json"
    previous = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
    if args.apply:
        destinations = [ROOT / "apps" / p["directory"] for p in manifest["projects"]]
        if any(p.exists() for p in destinations):
            raise RuntimeError("Refusing to overwrite an existing imported application")
        if previous and any(p["id"] in {old["id"] for old in previous["projects"]} for p in manifest["projects"]):
            raise RuntimeError("Refusing to replace existing source provenance")
        for project, destination in zip(manifest["projects"], destinations):
            source = args.source_root / project["directory"]
            for entry in project["files"]:
                original = source / entry["path"]
                if hashlib.sha256(original.read_bytes()).hexdigest() != entry["sha256"]:
                    raise RuntimeError(f"Source changed during snapshot: {original}")
                target = destination / entry["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(original, target)
        out.parent.mkdir(parents=True, exist_ok=True)
        combined = previous or {**manifest, "projects": []}
        combined["projects"].extend({**project, "snapshot_at": manifest["snapshot_at"]} for project in manifest["projects"])
        out.write_text(json.dumps(combined, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for project in manifest["projects"]:
        print(project["directory"], "included=", len(project["files"]), "excluded=", len(project["excluded"]))


if __name__ == "__main__":
    main()
