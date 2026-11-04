"""Read-only deployment checks; record statuses and timings, never payload contents."""
import argparse
import json
import sys
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from unified.registry import SYSTEMS, module_url


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", default="http://127.0.0.1:8888")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--curl", action="store_true", help="Use native curl with compression and no Windows registry proxy")
    parser.add_argument("--resolve", help="Diagnostic curl-only HOST:PORT:IP override; does not change system DNS")
    args = parser.parse_args()
    if args.resolve and not args.curl:
        parser.error("--resolve requires --curl")
    opener = build_opener(ProxyHandler({})) if args.origin.startswith("http://127.0.0.1:") else build_opener()
    results = []
    paths = [("home", "/"), ("home", "/api"), ("home", "/api/health")]
    paths += [(system["id"], module_url(system["id"], path)) for system in SYSTEMS for path in ("/", "/api")]
    for name, path in paths:
        started = time.monotonic()
        row = {"module": name, "path": path}
        try:
            if args.curl:
                command = ["curl.exe" if sys.platform == "win32" else "curl", "--compressed", "--silent", "--show-error",
                           "--max-time", str(args.timeout), "--connect-timeout", "8", "--write-out", "\n%{json}\n%header{x-myinvest-module}",
                           args.origin.rstrip("/") + path]
                if args.resolve:
                    command[1:1] = ["--resolve", args.resolve]
                result = subprocess.run(command, capture_output=True, timeout=args.timeout + 3)
                body, metadata, module_header = result.stdout.rsplit(b"\n", 2)
                info = json.loads(metadata)
                row.update(status=info["http_code"] if result.returncode == 0 else 0, bytes=len(body),
                           module_header=module_header.decode().strip() or None, curl_exit=result.returncode,
                           remote_ip=info.get("remote_ip"), tls_seconds=info.get("time_appconnect"), ttfb_seconds=info.get("time_starttransfer"))
                if path == "/api/health" and result.returncode == 0:
                    row["ready_modules"] = sum(m["alive"] and m["ready"] for m in json.loads(body)["modules"].values())
                continue
            request = Request(args.origin.rstrip("/") + path, headers={"User-Agent": "MyInvest-Deployment-Check", "Accept-Encoding": "identity"})
            with opener.open(request, timeout=args.timeout) as response:
                body = response.read()
                row.update(status=response.status, bytes=len(body), module_header=response.headers.get("X-MyInvest-Module"))
                if path == "/api/health":
                    payload = json.loads(body)
                    row["ready_modules"] = sum(m["alive"] and m["ready"] for m in payload["modules"].values())
        except HTTPError as exc:
            row.update(status=exc.code, error=exc.reason)
            exc.close()
        except Exception as exc:
            row.update(status=0, error=type(exc).__name__)
        finally:
            row["seconds"] = round(time.monotonic() - started, 3)
            results.append(row)
            print(json.dumps(row), flush=True)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps({"checked_at": datetime.now(timezone.utc).isoformat(), "origin": args.origin, "transport": "curl" if args.curl else "urllib", "dns_override": args.resolve, "checks": results}, indent=2), encoding="utf-8")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    return int(any(r["status"] != 200 or (r["module"] != "home" and r.get("module_header") != r["module"]) for r in results))


if __name__ == "__main__":
    raise SystemExit(main())
