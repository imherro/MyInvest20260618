"""Read-only check of the existing scheduler definitions against this repository."""
import argparse
import json
import os
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def audit(home):
    jobs = json.loads((ROOT / "research_jobs.json").read_text(encoding="utf-8"))["jobs"]
    records = [tomllib.loads(p.read_text(encoding="utf-8")) for p in home.glob("*/automation.toml")]
    results = []
    for key, job in jobs.items():
        matches = [r for r in records if r.get("id") == job["automation_id"]]
        errors = []
        if len(matches) != 1:
            errors.append("missing or duplicate automation ID")
        else:
            row = matches[0]
            for field in ("rrule", "status", "name"):
                if row.get(field) != job[field]:
                    errors.append(f"{field} differs")
            if [str(Path(p).resolve()) for p in row.get("cwds", [])] != [str(ROOT.resolve())]:
                errors.append("workspace is not the unified repository")
            if job["runbook"] not in row.get("prompt", "") or "research_jobs.py" not in row.get("prompt", ""):
                errors.append("prompt does not use managed runbook/runner")
        results.append({"task": key, "automation_id": job["automation_id"], "errors": errors})
    directories = {"MyInvestMarket", "MyInvestTheme", "MyInvestLeader"}
    managed_ids = {job["automation_id"] for job in jobs.values()}
    for row in records:
        if row.get("id") not in managed_ids and row.get("status") == "ACTIVE" and any(Path(p).name in directories for p in row.get("cwds", [])):
            results.append({"automation_id": row.get("id"), "errors": ["another active original-project automation exists"]})
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--automations", type=Path, default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "automations")
    args = parser.parse_args()
    results = audit(args.automations)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    raise SystemExit(int(any(row["errors"] for row in results)))
