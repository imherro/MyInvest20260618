from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from strategy_rebase import (
    append_or_validate_forward_observation_journal,
    build_forward_outcome_status,
    build_v15_daily_snapshot_capture,
    merge_forward_outcome_records,
    run_forward_outcome_intake,
    validate_forward_outcome_records,
    write_v15_forward_observation_journal_status,
)
from strategy_rebase.daily_snapshot_capture import FORBIDDEN_OUTPUT_KEYS
from strategy_rebase.forward_outcome_intake import OUTCOME_FORBIDDEN_KEYS


CAPTURED_AT = "2026-07-20T20:00:00+08:00"


def _write(root: Path, relative_path: str, content: str) -> Path:
    target = root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def _index_csv(rows: list[tuple[str, float]]) -> str:
    return "trade_date,close\n" + "".join(f"{date},{close}\n" for date, close in rows)


def _fixture(*, index_rows: list[tuple[str, float]] | None = None) -> tempfile.TemporaryDirectory[str]:
    temporary = tempfile.TemporaryDirectory()
    root = Path(temporary.name)
    _write(root, "data/macro_context_history.json", "{}\n")
    _write(
        root,
        "data/market_phase_snapshot.json",
        json.dumps(
            {
                "current": {
                    "phase": "LATE_CYCLE",
                    "metrics": {
                        "macro_state": "RECOVERY",
                        "structural_state": "STRUCTURAL_BULL_ROTATION",
                    },
                }
            }
        ),
    )
    _write(root, "data/historical_style_context.json", "{}\n")
    _write(root, "data/structural_hazard_dataset.json", "[]\n")
    _write(root, "data/cache/index_daily_000300_SH.csv", _index_csv(index_rows or [("20260717", 100.0)]))
    manifest, _, decision = build_v15_daily_snapshot_capture(
        snapshot_date="20260720", captured_at=CAPTURED_AT, root_dir=root
    )
    journal_path = root / "data/v15_forward_observation_journal.jsonl"
    _, journal_status, _ = append_or_validate_forward_observation_journal(
        manifest, decision, journal_path=journal_path, root_dir=root
    )
    write_v15_forward_observation_journal_status(
        journal_status, status_path=root / "data/v15_forward_observation_journal_status.json"
    )
    return temporary


def _run(root: Path, *, index_path: Path | None = None):
    return run_forward_outcome_intake(
        root_dir=root,
        journal_path=root / "data/v15_forward_observation_journal.jsonl",
        outcome_path=root / "data/v15_forward_outcome_records.jsonl",
        status_path=root / "data/v15_forward_outcome_status.json",
        index_path=index_path or root / "data/cache/index_daily_000300_SH.csv",
    )


def test_missing_journal_fails() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        try:
            _run(root)
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("missing journal must fail")


def test_manifest_hash_mismatch_fails() -> None:
    with _fixture() as tmp:
        root = Path(tmp)
        manifest_path = root / "data/point_in_time_snapshots/20260720/manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["manifest_sha256"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        try:
            _run(root)
        except AssertionError:
            pass
        else:
            raise AssertionError("manifest hash mismatch must fail")


def test_missing_index_keeps_all_windows_pending() -> None:
    with _fixture() as tmp:
        root = Path(tmp)
        missing = root / "data/cache/missing.csv"
        records, status = _run(root, index_path=missing)
        assert len(records) == 3
        assert all(record["status"] == "pending" for record in records)
        assert all(record["missing_reason"] == "index_source_missing" for record in records)
        assert status["pending_outcome_count"] == 3
        assert status["completed_outcome_count"] == 0


def test_unavailable_target_trade_dates_remain_pending() -> None:
    with _fixture(index_rows=[("20260717", 100.0), ("20260720", 101.0)]) as tmp:
        root = Path(tmp)
        records, status = _run(root)
        assert all(record["status"] == "pending" for record in records)
        assert all(record["missing_reason"] == "target_trade_date_unavailable" for record in records)
        assert status["pending_outcome_count"] == 3


def test_available_targets_complete_with_correct_returns() -> None:
    rows = [("20260720", 100.0)] + [(f"202608{day:02d}", 100.0 + day) for day in range(1, 21)]
    with _fixture(index_rows=rows) as tmp:
        root = Path(tmp)
        records, status = _run(root)
        by_window = {record["window"]: record for record in records}
        assert status["completed_outcome_count"] == 3
        assert status["pending_outcome_count"] == 0
        assert by_window["T_plus_1"]["target_trade_date"] == "20260801"
        assert by_window["T_plus_5"]["target_trade_date"] == "20260805"
        assert by_window["T_plus_20"]["target_trade_date"] == "20260820"
        assert by_window["T_plus_1"]["benchmark_return_pct"] == 0.01
        assert by_window["T_plus_20"]["benchmark_return_pct"] == 0.2
        assert all(len(record["source_sha256"]) == 64 for record in records)


def test_pending_to_completed_is_the_only_allowed_update() -> None:
    with _fixture(index_rows=[("20260720", 100.0)]) as tmp:
        root = Path(tmp)
        pending, _ = _run(root)
        completed_rows = [("20260720", 100.0)] + [(f"202608{day:02d}", 100.0 + day) for day in range(1, 21)]
        _write(root, "data/cache/index_daily_000300_SH.csv", _index_csv(completed_rows))
        completed, status = _run(root)
        assert status["completed_outcome_count"] == 3
        assert all(record["status"] == "completed" for record in completed)

        conflict = deepcopy(completed)
        conflict[0]["end_close"] = 999.0
        try:
            merge_forward_outcome_records(conflict, completed)
        except AssertionError:
            pass
        else:
            raise AssertionError("changed completed outcome must fail")

        try:
            merge_forward_outcome_records(completed, pending)
        except AssertionError:
            pass
        else:
            raise AssertionError("completed outcome cannot regress to pending")


def test_duplicate_outcome_id_is_rejected() -> None:
    with _fixture() as tmp:
        root = Path(tmp)
        records, _ = _run(root)
        duplicate = [*records, deepcopy(records[0])]
        try:
            merge_forward_outcome_records(duplicate, records)
        except AssertionError:
            pass
        else:
            raise AssertionError("duplicate outcome_id must fail")


def test_status_counts_and_forbidden_keys_are_recomputed() -> None:
    with _fixture() as tmp:
        root = Path(tmp)
        records, status = _run(root)
        journal = [json.loads(line) for line in (root / "data/v15_forward_observation_journal.jsonl").read_text(encoding="utf-8").splitlines()]
        for key, value in (
            ("outcome_record_count", 99),
            ("completed_outcome_count", 99),
            ("pending_outcome_count", 99),
            ("backtest_allowed", True),
            ("production_trade_enabled", True),
        ):
            forged_status = deepcopy(status)
            forged_status[key] = value
            try:
                validate_forward_outcome_records(
                    journal,
                    records,
                    forged_status,
                    root_dir=root,
                    index_path=root / "data/cache/index_daily_000300_SH.csv",
                )
            except AssertionError:
                pass
            else:
                raise AssertionError(f"forged status must fail: {key}")

        for key in FORBIDDEN_OUTPUT_KEYS | OUTCOME_FORBIDDEN_KEYS:
            forged_records = deepcopy(records)
            forged_records[0]["nested"] = {key: "forged"}
            forged_status = build_forward_outcome_status(journal, forged_records)
            try:
                validate_forward_outcome_records(
                    journal,
                    forged_records,
                    forged_status,
                    root_dir=root,
                    index_path=root / "data/cache/index_daily_000300_SH.csv",
                )
            except AssertionError:
                pass
            else:
                raise AssertionError(f"forbidden outcome key must fail: {key}")


def test_original_journal_bytes_remain_unchanged() -> None:
    with _fixture() as tmp:
        root = Path(tmp)
        journal_path = root / "data/v15_forward_observation_journal.jsonl"
        original = journal_path.read_bytes()
        _run(root)
        assert journal_path.read_bytes() == original


def main() -> None:
    test_missing_journal_fails()
    test_manifest_hash_mismatch_fails()
    test_missing_index_keeps_all_windows_pending()
    test_unavailable_target_trade_dates_remain_pending()
    test_available_targets_complete_with_correct_returns()
    test_pending_to_completed_is_the_only_allowed_update()
    test_duplicate_outcome_id_is_rejected()
    test_status_counts_and_forbidden_keys_are_recomputed()
    test_original_journal_bytes_remain_unchanged()
    print("test_v15_forward_outcome_intake ok")


if __name__ == "__main__":
    main()
