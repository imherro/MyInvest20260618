from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import DATA_DIR
from strategy_rebase import (
    append_or_validate_forward_observation_journal,
    write_v15_forward_observation_journal_status,
)


def main() -> None:
    manifest_path = DATA_DIR / "point_in_time_snapshots" / json.loads(
        (DATA_DIR / "v15_daily_snapshot_capture_status.json").read_text(encoding="utf-8")
    )["snapshot_date"] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    decision = json.loads((DATA_DIR / "v15_forward_paper_decision_latest.json").read_text(encoding="utf-8"))
    records, status, appended = append_or_validate_forward_observation_journal(manifest, decision)
    status_path = write_v15_forward_observation_journal_status(status)
    print(
        f"V15.8 records={len(records)} latest={status['latest_decision_date']} "
        f"pending={status['pending_outcome_count']} appended={appended} status={status_path}"
    )


if __name__ == "__main__":
    main()
