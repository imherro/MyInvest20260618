from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from strategy_rebase import (
    append_or_validate_forward_observation_journal,
    build_v15_daily_snapshot_capture,
    run_forward_outcome_intake,
    write_v15_daily_snapshot_capture,
    write_v15_forward_observation_journal_status,
)


def run_daily_forward_update(
    *,
    root_dir: str | Path = ROOT_DIR,
    snapshot_date: str | None = None,
    captured_at: str | None = None,
) -> dict[str, object]:
    root = Path(root_dir).resolve()
    data_dir = root / "data"
    journal_path = data_dir / "v15_forward_observation_journal.jsonl"
    manifest, capture_status, decision = build_v15_daily_snapshot_capture(
        root_dir=root,
        snapshot_date=snapshot_date,
        captured_at=captured_at,
    )
    write_v15_daily_snapshot_capture(
        capture_status,
        decision,
        status_path=data_dir / "v15_daily_snapshot_capture_status.json",
        decision_path=data_dir / "v15_forward_paper_decision_latest.json",
    )
    records, journal_status, appended = append_or_validate_forward_observation_journal(
        manifest,
        decision,
        journal_path=journal_path,
        root_dir=root,
    )
    write_v15_forward_observation_journal_status(
        journal_status,
        status_path=data_dir / "v15_forward_observation_journal_status.json",
    )
    outcomes, outcome_status = run_forward_outcome_intake(
        root_dir=root,
        journal_path=journal_path,
        outcome_path=data_dir / "v15_forward_outcome_records.jsonl",
        status_path=data_dir / "v15_forward_outcome_status.json",
        index_path=data_dir / "cache" / "index_daily_000300_SH.csv",
    )
    return {
        "snapshot_date": capture_status["snapshot_date"],
        "journal_record_count": len(records),
        "outcome_record_count": len(outcomes),
        "completed_outcome_count": outcome_status["completed_outcome_count"],
        "pending_outcome_count": outcome_status["pending_outcome_count"],
        "appended": appended,
        "backtest_allowed": outcome_status["backtest_allowed"],
        "production_trade_enabled": outcome_status["production_trade_enabled"],
    }


def main() -> None:
    result = run_daily_forward_update()
    print(
        f"V15.10 snapshot={result['snapshot_date']} journal={result['journal_record_count']} "
        f"outcomes={result['outcome_record_count']} completed={result['completed_outcome_count']} "
        f"pending={result['pending_outcome_count']} appended={result['appended']}"
    )


if __name__ == "__main__":
    main()
