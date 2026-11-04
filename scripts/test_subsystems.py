"""Run each subsystem suite in a disposable copy without production data/keys."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from import_subsystems import PROJECTS

ROOT = Path(__file__).resolve().parents[1]


def isolated_environment(destination):
    env = {k: v for k, v in os.environ.items()
           if not any(word in k.upper() for word in ("TOKEN", "SECRET", "API_KEY", "PASSWORD", "MYINVEST", "TUSHARE", "PYTHONPATH"))}
    env.update(PYTHONPATH=os.pathsep.join([str(ROOT / "scripts"), str(destination)]),
               PYTHONIOENCODING="utf-8", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", MYINVESTPICKING_FORCE_MOCK="1")
    return env


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", choices=list(PROJECTS), action="append")
    parser.add_argument("--timeout", type=int, default=1200)
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--data-root", type=Path, help="Optional parent of original repositories; copy inventoried report fixtures into the disposable sandbox")
    args = parser.parse_args()
    base = ROOT / "temp" / "monorepo-tests"
    base.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix="run-", dir=base))
    shutil.copy2(ROOT / "subsystems.json", run / "subsystems.json")
    snapshot = json.loads((ROOT / "docs/migration/source-snapshot.json").read_text(encoding="utf-8"))
    results = []
    for key in args.system or PROJECTS:
        name = PROJECTS[key]
        destination = run / "apps" / name
        shutil.copytree(ROOT / "apps" / name, destination,
                        ignore=shutil.ignore_patterns(".env", ".env.*", "__pycache__", ".pytest_cache", ".venv", "temp", "runtime"))
        fixture_count = 0
        fixture_index = []
        if args.data_root:
            original = (args.data_root / name).resolve()
            project = next(p for p in snapshot["projects"] if p["id"] == key)
            for entry in project["excluded"]:
                relative = Path(entry["path"])
                if entry["reason"] != "runtime-data-retained-in-original" or relative.parts[0] not in {"data", "research", "reports"}:
                    continue
                source = original / relative
                if source.is_file() and not source.is_symlink() and source.resolve().is_relative_to(original):
                    target = destination / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                    fixture_count += 1
                    fixture_index.append({"path": relative.as_posix(), "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
            if key == "cycle":
                # Cache-only regression tests need public index/ETF price series.
                # Do not copy market-wide, position, account or database caches.
                for pattern in ("fund_daily_*.csv", "index_daily_*.csv"):
                    for source in (original / "data/cache").glob(pattern):
                        if source.is_symlink() or not source.resolve().is_relative_to(original):
                            raise RuntimeError("Unsafe fixture cache path")
                        relative = source.relative_to(original)
                        target = destination / relative
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, target)
                        fixture_count += 1
                        fixture_index.append({"path": relative.as_posix(), "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
        (run / f"{key}-fixtures.json").write_text(json.dumps(fixture_index, indent=2), encoding="utf-8")
        env = isolated_environment(destination)
        paths = ["web/tests"] if key == "theme" else ["scripts", "engine_test.py"] if key == "cycle" else ["tests"]
        command = [sys.executable, "-m", "pytest", "-p", "offline_tests", "-o", "addopts=", "-q", "--tb=short",
                   f"--junitxml={run / (key + '.xml')}", *(["-x"] if args.fail_fast else []), *paths]
        start = time.monotonic()
        log_path = run / f"{key}.log"
        with log_path.open("w", encoding="utf-8") as log:
            try:
                result = subprocess.run(command, cwd=destination, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=args.timeout)
                code = result.returncode
            except subprocess.TimeoutExpired:
                code = 124
        tail = log_path.read_text(encoding="utf-8")[-3000:]
        results.append({"system": key, "exit_code": code, "fixture_files_copied": fixture_count,
                        "seconds": round(time.monotonic() - start, 2), "tail": tail})
        print(f"{key}: exit={code} log={log_path}", flush=True)
        (run / "summary.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Summary: {run / 'summary.json'}", flush=True)
    return int(any(item["exit_code"] != 0 for item in results))


if __name__ == "__main__":
    raise SystemExit(main())
