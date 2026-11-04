"""End-to-end single-port acceptance in source-only disposable copies."""
import argparse
import json
import concurrent.futures
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import ProxyHandler, build_opener

from source_copy import ROOT, copy_source
sys.path.insert(0, str(ROOT))
from unified.registry import SYSTEMS, module_url


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep-running", action="store_true")
    parser.add_argument("--data-root", type=Path, help="Copy approved read-only fixtures from legacy directories")
    args = parser.parse_args()
    base = ROOT / "temp/unified-tests"
    base.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix="run-", dir=base))
    for system in SYSTEMS:
        copy_source(system["directory"], run / "apps" / system["directory"])
        if args.data_root:
            from integration_fixtures import copy_fixtures
            records = copy_fixtures(system, args.data_root / system["directory"], run / "apps" / system["directory"])
            (run / (system["id"] + "-fixtures.json")).write_text(json.dumps(records, indent=2), encoding="utf-8")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    command = [sys.executable, "-u", str(ROOT / "server.py"), "--port", str(port), "--isolated-apps", str(run / "apps")]
    opener = build_opener(ProxyHandler({}))
    results = []
    with (run / "server.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        print(f"Isolated server PID {process.pid} at http://127.0.0.1:{port}; logs {run}", flush=True)
        try:
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                try:
                    opener.open(f"http://127.0.0.1:{port}/healthz", timeout=1).close()
                    break
                except OSError:
                    time.sleep(.2)
            for system in SYSTEMS:
                probe = {"cycle": "/api/style/rotation-backtest", "strategyindex": "/api/strategy-backtests/index.json",
                         "short": "/health.json", "picking": "/api/picks", "ten": "/api/task1"}.get(system["id"], "/api/index")
                for path in dict.fromkeys(["/", system["health"], "/api", probe]):
                    url = module_url(system["id"], path)
                    started = time.monotonic()
                    row = {"module": system["id"], "path": url}
                    try:
                        response = opener.open(f"http://127.0.0.1:{port}{url}", timeout=65)
                        body = response.read()
                        row.update(status=response.status, bytes=len(body), module_header=response.headers.get("X-MyInvest-Module"))
                    except HTTPError as exc:
                        row.update(status=exc.code, error=exc.read(300).decode(errors="replace"))
                    except Exception as exc:
                        row.update(status=0, error=str(exc))
                    row["seconds"] = round(time.monotonic() - started, 3)
                    results.append(row)
                    print(json.dumps(row), flush=True)
            with opener.open(f"http://127.0.0.1:{port}/api/health") as response:
                health = json.load(response)
            if not health["ok"] or len(health["modules"]) != 13:
                raise RuntimeError("Not all 13 workers are ready")
            def concurrent_probe(system):
                with opener.open(f"http://127.0.0.1:{port}{module_url(system['id'], '/api')}", timeout=30) as response:
                    response.read()
                    return response.headers.get("X-MyInvest-Module") == system["id"]
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                concurrency_ok = all(executor.map(concurrent_probe, SYSTEMS * 2))
            results.append({"test": "26_concurrent_catalog_requests", "status": 200 if concurrency_ok else 500})
            # This PID belongs to the disposable server created above, not production.
            previous_pid = health["modules"]["intraday"]["pid"]
            os.kill(previous_pid, signal.SIGTERM)
            time.sleep(.5)
            recovered = False
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                try:
                    with opener.open(f"http://127.0.0.1:{port}/api/intraday", timeout=10) as response:
                        recovered = response.status == 200
                    if recovered:
                        break
                except OSError:
                    time.sleep(1)
            with opener.open(f"http://127.0.0.1:{port}/api/health") as response:
                after = json.load(response)
            recovered = recovered and after["modules"]["intraday"]["pid"] != previous_pid
            results.append({"test": "isolated_worker_crash_recovery", "status": 200 if recovered else 500})
            if sys.platform == "win32":
                pids = ",".join(str(row["pid"]) for row in after["modules"].values())
                script = f"@(Get-NetTCPConnection -State Listen | Where-Object {{ $_.OwningProcess -in @({pids}) }}).Count"
                count = subprocess.check_output(["powershell", "-NoProfile", "-Command", script], text=True).strip()
                results.append({"test": "workers_have_no_tcp_listeners", "status": 200 if count == "0" else 500, "listeners": int(count)})
            if args.keep_running:
                print("Press Ctrl+C to stop the isolated server", flush=True)
                process.wait()
        finally:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=15)
            (run / "summary.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Summary: {run / 'summary.json'}")
    return int(any(row["status"] != 200 for row in results))


if __name__ == "__main__":
    raise SystemExit(main())
