from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from strategy_rebase import run_forward_outcome_intake


def main() -> None:
    records, status = run_forward_outcome_intake()
    print(
        f"V15.9 journal={status['journal_record_count']} outcomes={len(records)} "
        f"completed={status['completed_outcome_count']} pending={status['pending_outcome_count']}"
    )


if __name__ == "__main__":
    main()
