from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from pathlib import Path

from config import DATA_DIR
from strategy_rebase.daily_snapshot_capture import (
    ROOT_DIR,
    find_forbidden_output_keys,
    normalized_manifest_sha256,
)


DEFAULT_JOURNAL_PATH = DATA_DIR / "v15_forward_observation_journal.jsonl"
DEFAULT_STATUS_PATH = DATA_DIR / "v15_forward_observation_journal_status.json"
REQUIRED_CONSTRAINTS = (
    "does_not_run_backtest",
    "does_not_optimize_parameters",
    "does_not_generate_position",
    "does_not_generate_portfolio_weight",
    "does_not_generate_trade_signal",
    "no_order_generation",
    "no_broker_connection",
)


def _repo_path(root_dir: Path, relative_path: str) -> Path:
    target = (root_dir / relative_path).resolve()
    if not target.is_relative_to(root_dir.resolve()):
        raise ValueError(f"path escapes repository root: {relative_path}")
    return target


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def read_forward_observation_journal(path: str | Path = DEFAULT_JOURNAL_PATH) -> list[dict[str, object]]:
    target = Path(path)
    if not target.exists():
        return []
    records: list[dict[str, object]] = []
    for line_number, line in enumerate(target.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"journal line {line_number} must be a JSON object")
        records.append(payload)
    return records


def build_forward_observation_record(
    manifest: Mapping[str, object],
    decision: Mapping[str, object],
) -> dict[str, object]:
    decision_date = str(decision.get("decision_date") or manifest.get("snapshot_date") or "")
    manifest_hash = str(manifest.get("manifest_sha256") or "")
    readouts = decision.get("readouts") if isinstance(decision.get("readouts"), Mapping) else {}
    paper_decision = decision.get("paper_decision") if isinstance(decision.get("paper_decision"), Mapping) else {}
    return {
        "phase": "V15.8",
        "record_id": f"{decision_date}:{manifest_hash}",
        "decision_date": decision_date,
        "captured_at": manifest.get("captured_at"),
        "snapshot_manifest": decision.get("snapshot_manifest"),
        "snapshot_manifest_sha256": manifest_hash,
        "source_count": manifest.get("source_count"),
        "available_source_count": manifest.get("available_source_count"),
        "missing_source_count": manifest.get("missing_source_count"),
        "paper_only": True,
        "not_production_signal": True,
        "readouts": {
            "macro_cycle": readouts.get("macro_cycle"),
            "drawdown_context": readouts.get("drawdown_context"),
            "structural_bull": readouts.get("structural_bull"),
            "late_cycle_risk": readouts.get("late_cycle_risk"),
        },
        "paper_decision": {
            "decision_status": paper_decision.get("decision_status"),
            "allowed_use": paper_decision.get("allowed_use"),
        },
        "outcome_tracking": {
            "status": "pending",
            "windows": [
                {"window": "T_plus_1", "target_date": None, "status": "pending"},
                {"window": "T_plus_5", "target_date": None, "status": "pending"},
                {"window": "T_plus_20", "target_date": None, "status": "pending"},
            ],
        },
        "constraints": {key: True for key in REQUIRED_CONSTRAINTS},
    }


def build_forward_observation_journal_status(
    records: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    decision_dates = [str(record.get("decision_date") or "") for record in records]
    record_ids = [str(record.get("record_id") or "") for record in records]
    pending_count = sum(
        1
        for record in records
        if isinstance(record.get("outcome_tracking"), Mapping)
        and record["outcome_tracking"].get("status") == "pending"
    )
    completed_count = sum(
        1
        for record in records
        if isinstance(record.get("outcome_tracking"), Mapping)
        and record["outcome_tracking"].get("status") == "completed"
    )
    duplicate_count = len(record_ids) - len(set(record_ids))
    latest_index = max(range(len(records)), key=lambda index: decision_dates[index]) if records else None
    latest_date = decision_dates[latest_index] if latest_index is not None else None
    latest_id = record_ids[latest_index] if latest_index is not None else None
    status: dict[str, object] = {
        "phase": "V15.8",
        "journal_status": "journal_ready",
        "record_count": len(records),
        "unique_decision_date_count": len(set(decision_dates)),
        "latest_decision_date": latest_date,
        "latest_record_id": latest_id,
        "pending_outcome_count": pending_count,
        "completed_outcome_count": completed_count,
        "duplicate_record_count": duplicate_count,
        "append_only_mode": True,
        "paper_only": True,
        "backtest_allowed": False,
        "production_trade_enabled": False,
    }
    status["summary"] = {
        "phase": "V15.8",
        "journal_status": status["journal_status"],
        "record_count": status["record_count"],
        "latest_decision_date": status["latest_decision_date"],
        "pending_outcome_count": status["pending_outcome_count"],
        "backtest_allowed": False,
        "production_trade_enabled": False,
    }
    return status


def validate_forward_observation_journal(
    records: Sequence[Mapping[str, object]],
    status: Mapping[str, object],
    *,
    root_dir: str | Path = ROOT_DIR,
) -> None:
    root = Path(root_dir).resolve()
    seen_ids: set[str] = set()
    seen_dates: dict[str, str] = {}
    for record in records:
        if record.get("phase") != "V15.8":
            raise AssertionError("journal record phase must be V15.8")
        record_id = str(record.get("record_id") or "")
        decision_date = str(record.get("decision_date") or "")
        manifest_hash = str(record.get("snapshot_manifest_sha256") or "")
        if record_id != f"{decision_date}:{manifest_hash}":
            raise AssertionError("record_id must bind decision date and manifest hash")
        if record_id in seen_ids:
            raise AssertionError("duplicate record_id is not allowed")
        if decision_date in seen_dates and seen_dates[decision_date] != manifest_hash:
            raise AssertionError("one decision date cannot reference multiple manifest hashes")
        seen_ids.add(record_id)
        seen_dates[decision_date] = manifest_hash

        manifest_relative = str(record.get("snapshot_manifest") or "")
        manifest_path = _repo_path(root, manifest_relative)
        if not manifest_path.is_file():
            raise AssertionError("journal record must reference an existing snapshot manifest")
        manifest = _read_json(manifest_path)
        if manifest.get("manifest_sha256") != normalized_manifest_sha256(manifest):
            raise AssertionError("referenced snapshot manifest hash is invalid")
        if manifest.get("manifest_sha256") != manifest_hash:
            raise AssertionError("journal manifest hash does not match referenced manifest")
        if manifest.get("snapshot_date") != decision_date:
            raise AssertionError("journal decision date must match snapshot date")
        if record.get("captured_at") != manifest.get("captured_at"):
            raise AssertionError("journal capture time must match snapshot manifest")
        for count_key in ("source_count", "available_source_count", "missing_source_count"):
            if record.get(count_key) != manifest.get(count_key):
                raise AssertionError(f"journal {count_key} must match snapshot manifest")
        if record.get("paper_only") is not True or record.get("not_production_signal") is not True:
            raise AssertionError("journal records must remain paper-only")
        if record.get("backtest_allowed") is True:
            raise AssertionError("journal records cannot allow backtesting")
        if record.get("production_trade_enabled") is True:
            raise AssertionError("journal records cannot enable production trading")
        paper_decision = record.get("paper_decision") if isinstance(record.get("paper_decision"), Mapping) else {}
        if paper_decision.get("allowed_use") != "forward_observation_only":
            raise AssertionError("journal record use must remain forward observation only")
        outcome_tracking = record.get("outcome_tracking") if isinstance(record.get("outcome_tracking"), Mapping) else {}
        windows = outcome_tracking.get("windows") if isinstance(outcome_tracking.get("windows"), list) else []
        expected_windows = [
            {"window": "T_plus_1", "target_date": None, "status": "pending"},
            {"window": "T_plus_5", "target_date": None, "status": "pending"},
            {"window": "T_plus_20", "target_date": None, "status": "pending"},
        ]
        if outcome_tracking.get("status") != "pending" or windows != expected_windows:
            raise AssertionError("V15.8 outcome windows must remain pending and unfilled")
        if find_forbidden_output_keys(record):
            raise AssertionError("journal record contains forbidden output keys")
        constraints = record.get("constraints") if isinstance(record.get("constraints"), Mapping) else {}
        for key in REQUIRED_CONSTRAINTS:
            if constraints.get(key) is not True:
                raise AssertionError(f"constraints.{key} must be true")

    expected = build_forward_observation_journal_status(records)
    for key in (
        "phase",
        "journal_status",
        "record_count",
        "unique_decision_date_count",
        "latest_decision_date",
        "latest_record_id",
        "pending_outcome_count",
        "completed_outcome_count",
        "duplicate_record_count",
        "append_only_mode",
        "paper_only",
    ):
        if status.get(key) != expected.get(key):
            raise AssertionError(f"journal status {key} must be recomputed from journal")
    if status.get("backtest_allowed") is not False:
        raise AssertionError("V15.8 cannot allow backtesting")
    if status.get("production_trade_enabled") is not False:
        raise AssertionError("production trading must be disabled")
    if status.get("summary") != expected.get("summary"):
        raise AssertionError("journal status summary must be recomputed")


def append_or_validate_forward_observation_journal(
    manifest: Mapping[str, object],
    decision: Mapping[str, object],
    *,
    journal_path: str | Path = DEFAULT_JOURNAL_PATH,
    root_dir: str | Path = ROOT_DIR,
) -> tuple[list[dict[str, object]], dict[str, object], bool]:
    target = Path(journal_path)
    records = read_forward_observation_journal(target)
    candidate = build_forward_observation_record(manifest, decision)
    candidate_id = str(candidate["record_id"])
    candidate_date = str(candidate["decision_date"])
    candidate_hash = str(candidate["snapshot_manifest_sha256"])

    existing = next((record for record in records if record.get("record_id") == candidate_id), None)
    if existing is not None:
        if existing != candidate:
            raise AssertionError("existing journal record cannot be modified")
        appended = False
    else:
        date_match = next((record for record in records if record.get("decision_date") == candidate_date), None)
        if date_match is not None and date_match.get("snapshot_manifest_sha256") != candidate_hash:
            raise AssertionError("same decision date cannot use a different manifest hash")
        records.append(candidate)
        status = build_forward_observation_journal_status(records)
        validate_forward_observation_journal(records, status, root_dir=root_dir)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
        appended = True

    if not appended:
        status = build_forward_observation_journal_status(records)
        validate_forward_observation_journal(records, status, root_dir=root_dir)
    return records, status, appended


def write_v15_forward_observation_journal_status(
    status: Mapping[str, object],
    *,
    status_path: str | Path = DEFAULT_STATUS_PATH,
) -> Path:
    target = Path(status_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target
