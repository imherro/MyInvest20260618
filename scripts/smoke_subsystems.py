"""Check all imported web entry points on temporary ports in disposable copies."""
import json
import argparse
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

from subsystems import ROOT, systems
from test_subsystems import isolated_environment
from offline_tests import PRODUCTION_PORTS
from source_copy import copy_source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, help="Original repositories containing read-only TAA/Test fixtures")
    args = parser.parse_args()
    base = ROOT / "temp/monorepo-smoke"
    base.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix="run-", dir=base))
    results = []
    opener = build_opener(ProxyHandler({}))
    for system in systems():
        app = run / "apps" / system["directory"]
        copy_source(system["directory"], app)
        if args.data_root and system["id"] in {"taa", "test"}:
            from integration_fixtures import copy_fixtures
            copy_fixtures(system, args.data_root / system["directory"], app)
        while True:
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            if port not in PRODUCTION_PORTS:
                break
        command = [sys.executable, str(ROOT / "scripts/isolated_service.py"), *system["command"], "--host", "127.0.0.1", "--port", str(port)]
        row = {"system": system["id"], "port": port, "ok": False}
        with (run / (system["id"] + ".log")).open("w", encoding="utf-8") as log:
            process = subprocess.Popen(command, cwd=app, env=isolated_environment(app), stdout=log, stderr=subprocess.STDOUT,
                                       creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            try:
                deadline = time.monotonic() + 25
                while time.monotonic() < deadline and process.poll() is None:
                    try:
                        with opener.open(f"http://127.0.0.1:{port}{system.get('standalone_health', system['health'])}", timeout=2) as response:
                            body = response.read()
                            row.update(ok=response.status == 200 and bool(body), status=response.status, bytes=len(body))
                            break
                    except Exception as exc:
                        row["last_error"] = str(exc)
                        time.sleep(0.2)
            finally:
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        if row["ok"]:
            row.pop("last_error", None)
        results.append(row)
        print(json.dumps(row), flush=True)
        (run / "summary.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Summary: {run / 'summary.json'}")
    return int(any(not row["ok"] for row in results))


if __name__ == "__main__":
    raise SystemExit(main())
