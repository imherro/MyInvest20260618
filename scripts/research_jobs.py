"""Managed research sessions. Inspect is read-only; writes require a claimed token."""
from __future__ import annotations

import argparse
import hashlib
from contextlib import contextmanager
from datetime import datetime
import json
import os
from pathlib import Path
import runpy
import secrets
import subprocess
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from unified.registry import BY_ID

JOBS = json.loads((ROOT / "research_jobs.json").read_text(encoding="utf-8"))["jobs"]
STATE = ROOT / "runtime" / "research-jobs"
TZ = ZoneInfo("Asia/Shanghai")


@contextmanager
def exclusive(path):
    """OS locks survive parent interruption until the writer exits, not a timeout."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        handle.seek(0, 2)
        if not handle.tell():
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("Research session is busy; do not retry concurrently") from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def save(path, record):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def transition(folder, action, token=None, outcome=None, operation=None, day=None, policy=None):
    day = day or datetime.now(TZ).date().isoformat()
    with exclusive(folder / "session.lock"):
        path = folder / "session.json"
        record = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if action == "claim":
            if record and (record["day"] >= day or record["status"] not in {"success", "failed"}):
                return {"claimed": False, "status": record["status"], "day": record["day"]}
            if record:
                save(folder / f"{record['day']}.json", record)
            record = {"day": day, "token": secrets.token_hex(24), "status": "claimed",
                      "policy_before": policy or {}, "last_generated_policy": record.get("last_generated_policy")}
            save(path, record)
            return {"claimed": True, **{k: record[k] for k in ("day", "token", "status")}}
        if not token or not secrets.compare_digest(token, record.get("token", "")):
            raise RuntimeError("A matching session token is required")
        if action in {"generate", "qa"}:
            expected = "claimed" if action == "generate" else "generated"
            if record["status"] != expected:
                raise RuntimeError(f"Cannot {action} from {record['status']}")
            record["status"] = "running" if action == "generate" else "writing_qa"
            save(path, record)
            try:
                operation()
            except BaseException:
                record["status"] = "failed"
                save(path, record)
                raise
            record["status"] = "generated" if action == "generate" else "qa_written"
            if action == "generate" and policy is not None:
                record["last_generated_policy"] = policy
        elif action == "finish":
            if record["status"] in {"success", "failed"}:
                raise RuntimeError("Session already closed")
            if outcome == "success" and record["status"] not in {"generated", "qa_written"}:
                raise RuntimeError("Cannot mark unfinished generation successful")
            record["status"] = outcome
        else:
            raise ValueError(action)
        save(path, record)
        return {k: v for k, v in record.items() if k != "token"}


def paths(task, root=ROOT, originals=None):
    system = BY_ID[task]
    app = root / "apps" / system["directory"]
    original = (originals or root.parent) / system["directory"]
    bindings = []
    for relative in system["runtime_paths"]:
        source, target = app / relative, original / relative
        if not source.is_dir() or not target.is_dir() or source.resolve() != target.resolve():
            raise RuntimeError(f"Invalid runtime binding: {task}/{relative}")
        bindings.append({"path": relative, "resolved": str(target.resolve())})
    if not (original / ".env").is_file():
        raise RuntimeError(f"Missing original environment file: {task}")
    return app, original, bindings


def policy_signature(app):
    candidates = [app / "data" / name for name in
                  ("policy_signals.json", "policy_candidates.jsonl", "policy_scan_status.json")]
    candidates.extend(p for p in (app / "research/policy").rglob("*") if p.is_file())
    return {p.relative_to(app).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in candidates if p.is_file()}


def legacy_writers():
    if os.name != "nt":
        return []
    command = "Get-CimInstance Win32_Process -Filter \"name='python.exe' OR name='pythonw.exe'\" | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
    result = subprocess.run(["powershell", "-NoProfile", "-Command", command], check=True,
                            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    rows = json.loads(result.stdout or "[]")
    if isinstance(rows, dict):
        rows = [rows]
    names = {Path(step[0]).name for job in JOBS.values() for step in job["steps"]}
    names.add("chatgpt_qa_report.py")
    return [r["ProcessId"] for r in rows if r.get("ProcessId") != os.getpid()
            and any(name in (r.get("CommandLine") or "") for name in names)]


def prepare(task):
    app, original, _ = paths(task)
    for key in list(os.environ):
        if any(word in key.upper() for word in ("TOKEN", "SECRET", "API_KEY", "PASSWORD", "MYINVEST", "TUSHARE", "PYTHONPATH")):
            os.environ.pop(key, None)
    from dotenv import load_dotenv
    load_dotenv(original / ".env", encoding="utf-8-sig", override=True)
    os.environ.update(MYINVEST_ENV_FILE=str(original / ".env"),
                      MYINVEST_RESEARCH_ROOT=str(ROOT),
                      MYINVEST_MARKET_WEB_DATA=str(original / "web/data"),
                      MYINVEST_RESEARCH_ORIGINAL=str(original),
                      MYINVEST_UNIFIED_ORIGIN="http://127.0.0.1:8888")
    os.chdir(app)
    sys.path[:0] = [str(app), str(app / "scripts")]
    from unified.urls import install_internal_http
    install_internal_http("http://127.0.0.1:8888")
    return app


def run_step(app, step):
    sys.argv = [str(app / step[0]), *step[1:]]
    try:
        runpy.run_path(sys.argv[0], run_name="__main__")
    except SystemExit as exc:
        if exc.code not in {None, 0}:
            raise RuntimeError(f"Research stage failed: {step[0]} (exit {exc.code})") from exc


def check_leader_basis(payload, previous_basis, today):
    data = payload.get("result", payload)
    basis = data.get("basis_date", "")
    completeness = data.get("completeness") or {}
    if data.get("nominal_today") != today:
        raise RuntimeError("Upstream report was not evaluated today; historical fallback only")
    if not basis or basis > today or basis <= previous_basis:
        raise RuntimeError("No new upstream basis; do not generate downstream reports")
    if not data.get("theme_ranking") or not all(completeness.get(k, 0) > 0 for k in ("daily_rows", "daily_basic_rows")):
        raise RuntimeError("Incomplete upstream mainline report")
    return basis


def leader_gate(app):
    import urllib.request
    with urllib.request.urlopen("http://127.0.0.1:8888/api/theme/latest", timeout=30) as response:
        payload = json.load(response)
    previous = ""
    for path in (app / "research/leaders").glob("*.json"):
        report = json.loads(path.read_text(encoding="utf-8"))
        previous = max(previous, report.get("basis_date", ""))
    return check_leader_basis(payload, previous, datetime.now(TZ).date().isoformat())


def generate(task):
    if legacy_writers():
        raise RuntimeError("An existing research writer is running; migration runner stopped")
    app = prepare(task)
    if task == "theme":
        record = json.loads((STATE / task / "session.json").read_text(encoding="utf-8"))
        current = policy_signature(app)
        baseline = record.get("last_generated_policy") or record.get("policy_before", {})
        changed = sorted(p for p in current.keys() | baseline.keys() if current.get(p) != baseline.get(p))
        os.environ["MYINVEST_RESEARCH_POLICY_CHANGED"] = json.dumps(changed)
    basis = leader_gate(app) if task == "leader" else None
    for index, step in enumerate(JOBS[task]["steps"]):
        run_step(app, step)
        if task == "leader" and index == 0:
            from leader_app.service import latest_report
            _, report, _ = latest_report()
            if report.get("basis_date") != basis or report.get("data_gaps"):
                raise RuntimeError("Leader first stage incomplete; downstream writers stopped")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["inspect", "claim", "generate", "qa", "finish"])
    parser.add_argument("task", choices=list(JOBS))
    parser.add_argument("--token")
    parser.add_argument("--outcome", choices=["success", "failed"], default="success")
    parser.add_argument("--input", type=Path)
    args = parser.parse_args()
    app, original, bindings = paths(args.task)
    if args.action == "inspect":
        print(json.dumps({"task": args.task, "code": str(app), "data": bindings,
                          "env_exists": True, "legacy_writer_pids": legacy_writers()}, indent=2))
        return
    if args.action == "claim" and legacy_writers():
        raise RuntimeError("Existing research writer detected; do not start a second job")
    operation = lambda: generate(args.task)
    if args.action == "qa":
        if args.task != "theme" or not args.input or not args.input.is_file():
            parser.error("qa requires theme and an existing --input JSON file")
        input_path = args.input.resolve()
        operation = lambda: run_step(prepare("theme"), ["scripts/chatgpt_qa_report.py", "--input", str(input_path)])
    policy = policy_signature(app) if args.task == "theme" else None
    result = transition(STATE / args.task, args.action, args.token, args.outcome, operation, policy=policy)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
