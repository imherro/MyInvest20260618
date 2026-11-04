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
    build_forward_observation_journal_status,
    build_v15_daily_snapshot_capture,
    normalized_manifest_sha256,
    read_forward_observation_journal,
    validate_forward_observation_journal,
)
from strategy_rebase.daily_snapshot_capture import FORBIDDEN_OUTPUT_KEYS


CAPTURED_AT = "2026-07-20T20:00:00+08:00"


def _write(root: Path, relative_path: str, content: str) -> None:
    target = root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _fixture() -> tempfile.TemporaryDirectory[str]:
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
    _write(root, "data/cache/index_daily_000300_SH.csv", "trade_date,close\n20260717,4000\n")
    return temporary


def _capture(root: Path) -> tuple[dict[str, object], dict[str, object]]:
    manifest, _, decision = build_v15_daily_snapshot_capture(
        snapshot_date="20260720", captured_at=CAPTURED_AT, root_dir=root
    )
    return manifest, decision


def test_first_run_creates_first_journal_record() -> None:
    with _fixture() as tmp:
        root = Path(tmp)
        journal = root / "data/v15_forward_observation_journal.jsonl"
        manifest, decision = _capture(root)
        records, status, appended = append_or_validate_forward_observation_journal(
            manifest, decision, journal_path=journal, root_dir=root
        )
        assert appended is True
        assert len(records) == 1
        assert status["record_count"] == 1
        assert status["unique_decision_date_count"] == 1
        assert status["pending_outcome_count"] == 1
        assert read_forward_observation_journal(journal) == records


def test_same_record_id_is_idempotent_and_does_not_rewrite() -> None:
    with _fixture() as tmp:
        root = Path(tmp)
        journal = root / "data/v15_forward_observation_journal.jsonl"
        manifest, decision = _capture(root)
        append_or_validate_forward_observation_journal(manifest, decision, journal_path=journal, root_dir=root)
        original = journal.read_bytes()
        records, status, appended = append_or_validate_forward_observation_journal(
            manifest, decision, journal_path=journal, root_dir=root
        )
        assert appended is False
        assert journal.read_bytes() == original
        assert len(records) == 1
        assert status["duplicate_record_count"] == 0


def test_same_decision_date_with_different_manifest_hash_fails() -> None:
    with _fixture() as tmp:
        root = Path(tmp)
        journal = root / "data/v15_forward_observation_journal.jsonl"
        manifest, decision = _capture(root)
        append_or_validate_forward_observation_journal(manifest, decision, journal_path=journal, root_dir=root)
        forged_manifest = deepcopy(manifest)
        forged_manifest["captured_at"] = "2026-07-20T21:00:00+08:00"
        forged_manifest["manifest_sha256"] = normalized_manifest_sha256(forged_manifest)
        forged_decision = deepcopy(decision)
        forged_decision["snapshot_manifest_sha256"] = forged_manifest["manifest_sha256"]
        try:
            append_or_validate_forward_observation_journal(
                forged_manifest, forged_decision, journal_path=journal, root_dir=root
            )
        except AssertionError:
            pass
        else:
            raise AssertionError("same decision date with different manifest hash must fail")


def test_record_requires_existing_matching_manifest() -> None:
    with _fixture() as tmp:
        root = Path(tmp)
        journal = root / "data/v15_forward_observation_journal.jsonl"
        manifest, decision = _capture(root)
        records, status, _ = append_or_validate_forward_observation_journal(
            manifest, decision, journal_path=journal, root_dir=root
        )
        (root / records[0]["snapshot_manifest"]).unlink()
        try:
            validate_forward_observation_journal(records, status, root_dir=root)
        except AssertionError:
            pass
        else:
            raise AssertionError("missing referenced manifest must fail")


def test_manifest_hash_mismatch_fails() -> None:
    with _fixture() as tmp:
        root = Path(tmp)
        manifest, decision = _capture(root)
        records, _, _ = append_or_validate_forward_observation_journal(
            manifest,
            decision,
            journal_path=root / "data/v15_forward_observation_journal.jsonl",
            root_dir=root,
        )
        forged = deepcopy(records)
        forged[0]["snapshot_manifest_sha256"] = "0" * 64
        forged[0]["record_id"] = f"20260720:{'0' * 64}"
        status = build_forward_observation_journal_status(forged)
        try:
            validate_forward_observation_journal(forged, status, root_dir=root)
        except AssertionError:
            pass
        else:
            raise AssertionError("manifest hash mismatch must fail")


def test_each_forbidden_key_is_rejected_when_nested() -> None:
    with _fixture() as tmp:
        root = Path(tmp)
        manifest, decision = _capture(root)
        records, _, _ = append_or_validate_forward_observation_journal(
            manifest,
            decision,
            journal_path=root / "data/v15_forward_observation_journal.jsonl",
            root_dir=root,
        )
        for key in FORBIDDEN_OUTPUT_KEYS:
            forged = deepcopy(records)
            forged[0]["readouts"]["nested"] = {key: "forged"}
            status = build_forward_observation_journal_status(forged)
            try:
                validate_forward_observation_journal(forged, status, root_dir=root)
            except AssertionError:
                pass
            else:
                raise AssertionError(f"forbidden key must fail: {key}")


def test_status_gates_and_counts_are_recomputed() -> None:
    with _fixture() as tmp:
        root = Path(tmp)
        manifest, decision = _capture(root)
        records, status, _ = append_or_validate_forward_observation_journal(
            manifest,
            decision,
            journal_path=root / "data/v15_forward_observation_journal.jsonl",
            root_dir=root,
        )
        for key, value in (
            ("backtest_allowed", True),
            ("production_trade_enabled", True),
            ("record_count", 99),
            ("unique_decision_date_count", 99),
            ("pending_outcome_count", 99),
        ):
            forged = deepcopy(status)
            forged[key] = value
            try:
                validate_forward_observation_journal(records, forged, root_dir=root)
            except AssertionError:
                pass
            else:
                raise AssertionError(f"forged status must fail: {key}")

        for key in ("backtest_allowed", "production_trade_enabled"):
            forged_records = deepcopy(records)
            forged_records[0][key] = True
            forged_status = build_forward_observation_journal_status(forged_records)
            try:
                validate_forward_observation_journal(forged_records, forged_status, root_dir=root)
            except AssertionError:
                pass
            else:
                raise AssertionError(f"forged record gate must fail: {key}")


def test_record_has_no_position_weight_signal_or_order_fields() -> None:
    with _fixture() as tmp:
        root = Path(tmp)
        manifest, decision = _capture(root)
        records, _, _ = append_or_validate_forward_observation_journal(
            manifest,
            decision,
            journal_path=root / "data/v15_forward_observation_journal.jsonl",
            root_dir=root,
        )
        serialized = json.dumps(records[0], ensure_ascii=False)
        for forbidden in FORBIDDEN_OUTPUT_KEYS:
            assert f'"{forbidden}"' not in serialized


def test_manifest_fields_and_outcome_windows_cannot_be_forged() -> None:
    with _fixture() as tmp:
        root = Path(tmp)
        manifest, decision = _capture(root)
        records, _, _ = append_or_validate_forward_observation_journal(
            manifest,
            decision,
            journal_path=root / "data/v15_forward_observation_journal.jsonl",
            root_dir=root,
        )
        for key, value in (
            ("source_count", 99),
            ("available_source_count", 99),
            ("missing_source_count", 99),
            ("captured_at", "2026-07-20T23:00:00+08:00"),
        ):
            forged = deepcopy(records)
            forged[0][key] = value
            try:
                validate_forward_observation_journal(
                    forged, build_forward_observation_journal_status(forged), root_dir=root
                )
            except AssertionError:
                pass
            else:
                raise AssertionError(f"forged manifest field must fail: {key}")

        forged_windows = deepcopy(records)
        forged_windows[0]["outcome_tracking"]["windows"][0]["status"] = "completed"
        try:
            validate_forward_observation_journal(
                forged_windows, build_forward_observation_journal_status(forged_windows), root_dir=root
            )
        except AssertionError:
            pass
        else:
            raise AssertionError("V15.8 cannot forge completed outcome windows")


def main() -> None:
    test_first_run_creates_first_journal_record()
    test_same_record_id_is_idempotent_and_does_not_rewrite()
    test_same_decision_date_with_different_manifest_hash_fails()
    test_record_requires_existing_matching_manifest()
    test_manifest_hash_mismatch_fails()
    test_each_forbidden_key_is_rejected_when_nested()
    test_status_gates_and_counts_are_recomputed()
    test_record_has_no_position_weight_signal_or_order_fields()
    test_manifest_fields_and_outcome_windows_cannot_be_forged()
    print("test_v15_forward_observation_journal ok")


if __name__ == "__main__":
    main()
