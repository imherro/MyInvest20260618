"""Publish compact acceptance evidence only when every selected result passes."""
import argparse
import hashlib
import json
import platform
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from import_subsystems import PROJECTS, ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite-run", type=Path, action="append", required=True, help="Later runs override earlier results for the same system")
    parser.add_argument("--smoke-run", type=Path, required=True)
    args = parser.parse_args()
    suites = {}
    for run in args.suite_run:
        run = run.resolve()
        for row in json.loads((run / "summary.json").read_text(encoding="utf-8")):
            suite = ET.parse(run / (row["system"] + ".xml")).getroot().find("testsuite")
            suites[row["system"]] = {
                "exit_code": row["exit_code"], "seconds": row["seconds"],
                "junit_cases_including_subtests": int(suite.attrib["tests"]),
                "failures": int(suite.attrib["failures"]), "errors": int(suite.attrib["errors"]),
                "skipped": int(suite.attrib["skipped"]), "fixture_files_copied": row["fixture_files_copied"],
                "log_directory": run.relative_to(ROOT).as_posix(),
            }
    smoke = json.loads((args.smoke_run / "summary.json").read_text(encoding="utf-8"))
    if set(suites) != set(PROJECTS) or any(s["exit_code"] or s["failures"] or s["errors"] for s in suites.values()):
        raise RuntimeError("Every subsystem needs a successful suite result")
    if {s["system"] for s in smoke} != set(PROJECTS) or not all(s["ok"] for s in smoke):
        raise RuntimeError("Every subsystem needs a successful smoke result")
    root_tests = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"], cwd=ROOT,
                                capture_output=True, encoding="utf-8", timeout=120)
    if root_tests.returncode:
        raise RuntimeError(root_tests.stderr)
    audit = subprocess.run([sys.executable, "scripts/audit_subsystems.py"], cwd=ROOT,
                           capture_output=True, encoding="utf-8", timeout=120)
    if audit.returncode:
        raise RuntimeError(audit.stdout)
    result = {"verified_at": datetime.now(timezone.utc).isoformat(), "python": platform.python_version(),
              "scope": "local isolated source migration acceptance; not production cutover or hosted CI",
              "snapshot_sha256": hashlib.sha256((ROOT / "docs/migration/source-snapshot.json").read_bytes()).hexdigest(),
              "suites": suites, "smoke": smoke, "root_unittest": root_tests.stderr.strip(),
              "source_audit": json.loads(audit.stdout), "production_cutover_performed": False}
    path = ROOT / "docs/migration/validation.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
