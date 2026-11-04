"""List/check production services or launch an isolated source-only development copy."""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.request import urlopen
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unified.registry import module_url

ROOT = Path(__file__).resolve().parents[1]


def systems():
    return json.loads((ROOT / "subsystems.json").read_text(encoding="utf-8"))["systems"]


def development_command(system, port):
    if not 1024 <= port <= 65535 or port in {8888, 8009, *range(8011, 8026)}:
        raise ValueError("Choose a non-production port between 1024 and 65535")
    return [sys.executable, *system["command"], "--host", "127.0.0.1", "--port", str(port)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["list", "check", "dev"])
    parser.add_argument("--system", choices=[s["id"] for s in systems()])
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    selected = [s for s in systems() if not args.system or s["id"] == args.system]
    if args.action == "dev":
        if not args.system or not args.port:
            parser.error("dev requires --system and an explicit --port; production is never replaced")
        system = selected[0]
        command = development_command(system, args.port)
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", args.port)) == 0:
                parser.error("Port is occupied; no process will be stopped")
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        from source_copy import copy_source
        from test_subsystems import isolated_environment
        base = ROOT / "temp/monorepo-dev"
        base.mkdir(parents=True, exist_ok=True)
        destination = Path(tempfile.mkdtemp(prefix=system["id"] + "-", dir=base))
        copy_source(system["directory"], destination)
        print(f"Development copy: {destination}; http://127.0.0.1:{args.port}/", flush=True)
        return subprocess.call(command, cwd=destination, env=isolated_environment(destination))
    failed = False
    for system in selected:
        row = {**system, "source": f"apps/{system['directory']}", "production": "unified IPC; original runtime data", "url": module_url(system["id"])}
        row["legacy_port"] = row.pop("port")
        if args.action == "check":
            try:
                with urlopen(f"http://127.0.0.1:8888{module_url(system['id'], system['health'])}", timeout=60) as response:
                    row["http_status"] = response.status
            except Exception as exc:
                row["error"] = str(exc)
                failed = True
        print(json.dumps(row, ensure_ascii=False))
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
