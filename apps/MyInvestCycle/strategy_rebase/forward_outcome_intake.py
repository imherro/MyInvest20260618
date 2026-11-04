from __future__ import annotations

from collections.abc import Mapping, Sequence
import csv
import hashlib
import json
import os
from pathlib import Path
import tempfile

from config import DATA_DIR
from strategy_rebase.daily_snapshot_capture import ROOT_DIR, find_forbidden_output_keys
from strategy_rebase.forward_observation_journal import (
    read_forward_observation_journal,
    validate_forward_observation_journal,
)


DEFAULT_JOURNAL_PATH = DATA_DIR / "v15_forward_observation_journal.jsonl"
DEFAULT_JOURNAL_STATUS_PATH = DATA_DIR / "v15_forward_observation_journal_status.json"
DEFAULT_OUTCOME_PATH = DATA_DIR / "v15_forward_outcome_records.jsonl"
DEFAULT_STATUS_PATH = DATA_DIR / "v15_forward_outcome_status.json"
DEFAULT_INDEX_PATH = DATA_DIR / "cache" / "index_daily_000300_SH.csv"
BENCHMARK = "CSI300"
SOURCE_RELATIVE_PATH = "data/cache/index_daily_000300_SH.csv"
WINDOWS = (("T_plus_1", 1), ("T_plus_5", 5), ("T_plus_20", 20))
OUTCOME_FORBIDDEN_KEYS = {
    "alpha",
    "strategy_return",
    "portfolio_return",
    "position_return",
    "win_rate",
}


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


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    records: list[dict[str, object]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"outcome line {line_number} must be a JSON object")
        records.append(payload)
    return records


def _load_index_rows(path: Path) -> list[dict[str, object]]:
    if not path.is_file():
        return []
    rows: dict[str, dict[str, object]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "trade_date" not in reader.fieldnames or "close" not in reader.fieldnames:
            raise ValueError("index source must contain trade_date and close columns")
        for raw in reader:
            trade_date = str(raw.get("trade_date") or "").strip()
            if not trade_date:
                continue
            if trade_date in rows:
                raise ValueError(f"duplicate index trade date: {trade_date}")
            rows[trade_date] = {"trade_date": trade_date, "close": float(raw["close"])}
    return [rows[date] for date in sorted(rows)]


def _evidence_sha256(start: Mapping[str, object], end: Mapping[str, object]) -> str:
    payload = {
        "benchmark": BENCHMARK,
        "source_path": SOURCE_RELATIVE_PATH,
        "start": {"trade_date": start["trade_date"], "close": start["close"]},
        "end": {"trade_date": end["trade_date"], "close": end["close"]},
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def find_outcome_forbidden_keys(value: object) -> set[str]:
    found = find_forbidden_output_keys(value)
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if str(key) in OUTCOME_FORBIDDEN_KEYS:
                found.add(str(key))
            found.update(find_outcome_forbidden_keys(nested))
    elif isinstance(value, list):
        for nested in value:
            found.update(find_outcome_forbidden_keys(nested))
    return found


def _pending_outcome(record: Mapping[str, object], window: str, reason: str) -> dict[str, object]:
    return {
        "phase": "V15.9",
        "outcome_id": f"{record['record_id']}:{window}",
        "record_id": record["record_id"],
        "decision_date": record["decision_date"],
        "window": window,
        "status": "pending",
        "target_trade_date": None,
        "benchmark": BENCHMARK,
        "start_trade_date": None,
        "end_trade_date": None,
        "start_close": None,
        "end_close": None,
        "benchmark_return_pct": None,
        "source_path": SOURCE_RELATIVE_PATH,
        "source_sha256": None,
        "missing_reason": reason,
        "paper_only": True,
        "not_strategy_return": True,
        "not_production_signal": True,
    }


def build_forward_outcome_records(
    journal_records: Sequence[Mapping[str, object]],
    *,
    index_path: str | Path = DEFAULT_INDEX_PATH,
) -> list[dict[str, object]]:
    index_target = Path(index_path)
    index_rows = _load_index_rows(index_target)
    results: list[dict[str, object]] = []
    for record in journal_records:
        decision_date = str(record.get("decision_date") or "")
        eligible = [index for index, row in enumerate(index_rows) if str(row["trade_date"]) <= decision_date]
        start_index = eligible[-1] if eligible else None
        for window, offset in WINDOWS:
            if not index_target.is_file():
                results.append(_pending_outcome(record, window, "index_source_missing"))
                continue
            if start_index is None:
                results.append(_pending_outcome(record, window, "start_trade_date_unavailable"))
                continue
            target_index = start_index + offset
            if target_index >= len(index_rows):
                results.append(_pending_outcome(record, window, "target_trade_date_unavailable"))
                continue
            start = index_rows[start_index]
            end = index_rows[target_index]
            start_close = float(start["close"])
            end_close = float(end["close"])
            results.append(
                {
                    "phase": "V15.9",
                    "outcome_id": f"{record['record_id']}:{window}",
                    "record_id": record["record_id"],
                    "decision_date": decision_date,
                    "window": window,
                    "status": "completed",
                    "target_trade_date": end["trade_date"],
                    "benchmark": BENCHMARK,
                    "start_trade_date": start["trade_date"],
                    "end_trade_date": end["trade_date"],
                    "start_close": start_close,
                    "end_close": end_close,
                    "benchmark_return_pct": round(end_close / start_close - 1.0, 10),
                    "source_path": SOURCE_RELATIVE_PATH,
                    "source_sha256": _evidence_sha256(start, end),
                    "missing_reason": None,
                    "paper_only": True,
                    "not_strategy_return": True,
                    "not_production_signal": True,
                }
            )
    return results


def merge_forward_outcome_records(
    existing: Sequence[Mapping[str, object]],
    candidates: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    existing_by_id: dict[str, Mapping[str, object]] = {}
    for record in existing:
        outcome_id = str(record.get("outcome_id") or "")
        if outcome_id in existing_by_id:
            raise AssertionError("duplicate outcome_id in existing sidecar")
        existing_by_id[outcome_id] = record
    candidate_ids = [str(record.get("outcome_id") or "") for record in candidates]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise AssertionError("duplicate outcome_id in candidate outcomes")
    if set(existing_by_id) - set(candidate_ids):
        raise AssertionError("existing outcome cannot become orphaned from journal")

    merged: list[dict[str, object]] = []
    for candidate in candidates:
        outcome_id = str(candidate.get("outcome_id") or "")
        previous = existing_by_id.get(outcome_id)
        if previous is None or previous == candidate:
            merged.append(dict(candidate))
            continue
        previous_status = previous.get("status")
        candidate_status = candidate.get("status")
        if previous_status == "pending" and candidate_status == "completed":
            merged.append(dict(candidate))
            continue
        if previous_status == "completed":
            raise AssertionError("completed outcome is immutable and conflicts with current result")
        raise AssertionError("outcome can only transition from pending to completed")
    return merged


def build_forward_outcome_status(
    journal_records: Sequence[Mapping[str, object]],
    outcome_records: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    completed = sum(1 for record in outcome_records if record.get("status") == "completed")
    pending = sum(1 for record in outcome_records if record.get("status") == "pending")
    dates = [str(record.get("decision_date") or "") for record in journal_records]
    status: dict[str, object] = {
        "phase": "V15.9",
        "outcome_status": "outcome_intake_ready",
        "journal_record_count": len(journal_records),
        "outcome_record_count": len(outcome_records),
        "completed_outcome_count": completed,
        "pending_outcome_count": pending,
        "benchmark": BENCHMARK,
        "paper_only": True,
        "backtest_allowed": False,
        "production_trade_enabled": False,
    }
    status["summary"] = {
        "phase": "V15.9",
        "outcome_status": status["outcome_status"],
        "completed_outcome_count": completed,
        "pending_outcome_count": pending,
        "latest_decision_date": max(dates) if dates else None,
    }
    return status


def validate_forward_outcome_records(
    journal_records: Sequence[Mapping[str, object]],
    outcome_records: Sequence[Mapping[str, object]],
    status: Mapping[str, object],
    *,
    root_dir: str | Path = ROOT_DIR,
    index_path: str | Path = DEFAULT_INDEX_PATH,
) -> None:
    root = Path(root_dir).resolve()
    journal_status = _read_json(_repo_path(root, "data/v15_forward_observation_journal_status.json"))
    validate_forward_observation_journal(journal_records, journal_status, root_dir=root)
    journal_by_id = {str(record["record_id"]): record for record in journal_records}
    outcome_ids: set[str] = set()
    index_rows = _load_index_rows(Path(index_path))
    row_by_date = {str(row["trade_date"]): row for row in index_rows}
    for outcome in outcome_records:
        if outcome.get("phase") != "V15.9":
            raise AssertionError("outcome phase must be V15.9")
        outcome_id = str(outcome.get("outcome_id") or "")
        if outcome_id in outcome_ids:
            raise AssertionError("duplicate outcome_id is not allowed")
        outcome_ids.add(outcome_id)
        record_id = str(outcome.get("record_id") or "")
        journal = journal_by_id.get(record_id)
        if journal is None:
            raise AssertionError("outcome must reference an existing journal record")
        window = str(outcome.get("window") or "")
        if window not in dict(WINDOWS) or outcome_id != f"{record_id}:{window}":
            raise AssertionError("outcome_id must bind journal record and supported window")
        if outcome.get("decision_date") != journal.get("decision_date"):
            raise AssertionError("outcome decision date must match journal")
        if outcome.get("benchmark") != BENCHMARK or outcome.get("source_path") != SOURCE_RELATIVE_PATH:
            raise AssertionError("V15.9 outcome benchmark contract is invalid")
        if outcome.get("paper_only") is not True or outcome.get("not_strategy_return") is not True or outcome.get("not_production_signal") is not True:
            raise AssertionError("outcomes must remain paper-only market results")
        if find_outcome_forbidden_keys(outcome):
            raise AssertionError("outcome contains forbidden strategy or trade keys")
        if outcome.get("status") == "pending":
            for key in (
                "target_trade_date",
                "start_trade_date",
                "end_trade_date",
                "start_close",
                "end_close",
                "benchmark_return_pct",
                "source_sha256",
            ):
                if outcome.get(key) is not None:
                    raise AssertionError("pending outcome cannot claim completed market evidence")
            if not outcome.get("missing_reason"):
                raise AssertionError("pending outcome must explain missing evidence")
        elif outcome.get("status") == "completed":
            start = row_by_date.get(str(outcome.get("start_trade_date") or ""))
            end = row_by_date.get(str(outcome.get("end_trade_date") or ""))
            if start is None or end is None:
                raise AssertionError("completed outcome dates must exist in benchmark source")
            if outcome.get("target_trade_date") != end["trade_date"]:
                raise AssertionError("completed target date must equal end trade date")
            if float(outcome.get("start_close")) != float(start["close"]) or float(outcome.get("end_close")) != float(end["close"]):
                raise AssertionError("completed closes must match benchmark source")
            expected_return = round(float(end["close"]) / float(start["close"]) - 1.0, 10)
            if outcome.get("benchmark_return_pct") != expected_return:
                raise AssertionError("completed benchmark return is invalid")
            if outcome.get("source_sha256") != _evidence_sha256(start, end):
                raise AssertionError("completed evidence hash is invalid")
            if outcome.get("missing_reason") is not None:
                raise AssertionError("completed outcome cannot have a missing reason")
        else:
            raise AssertionError("outcome status must be pending or completed")

    expected_ids = {
        f"{record['record_id']}:{window}"
        for record in journal_records
        for window, _ in WINDOWS
    }
    if outcome_ids != expected_ids:
        raise AssertionError("outcomes must contain exactly three windows per journal record")
    expected_records = {
        str(record["outcome_id"]): record
        for record in build_forward_outcome_records(journal_records, index_path=index_path)
    }
    for outcome in outcome_records:
        if outcome != expected_records.get(str(outcome["outcome_id"])):
            raise AssertionError("outcome must match the deterministic benchmark window result")
    expected_status = build_forward_outcome_status(journal_records, outcome_records)
    if status != expected_status:
        raise AssertionError("outcome status must be recomputed from records")
    if status.get("backtest_allowed") is not False or status.get("production_trade_enabled") is not False:
        raise AssertionError("V15.9 cannot enable backtest or production trading")


def _atomic_write_jsonl(path: Path, records: Sequence[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        Path(temporary_name).replace(path)
    finally:
        temporary = Path(temporary_name)
        if temporary.exists():
            temporary.unlink()


def run_forward_outcome_intake(
    *,
    root_dir: str | Path = ROOT_DIR,
    journal_path: str | Path = DEFAULT_JOURNAL_PATH,
    outcome_path: str | Path = DEFAULT_OUTCOME_PATH,
    status_path: str | Path = DEFAULT_STATUS_PATH,
    index_path: str | Path = DEFAULT_INDEX_PATH,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    root = Path(root_dir).resolve()
    journal_target = Path(journal_path)
    if not journal_target.is_file():
        raise FileNotFoundError(f"forward observation journal missing: {journal_target}")
    journal_bytes = journal_target.read_bytes()
    journal_records = read_forward_observation_journal(journal_target)
    journal_status = _read_json(_repo_path(root, "data/v15_forward_observation_journal_status.json"))
    validate_forward_observation_journal(journal_records, journal_status, root_dir=root)

    candidates = build_forward_outcome_records(journal_records, index_path=index_path)
    existing = _read_jsonl(Path(outcome_path))
    merged = merge_forward_outcome_records(existing, candidates)
    status = build_forward_outcome_status(journal_records, merged)
    validate_forward_outcome_records(journal_records, merged, status, root_dir=root, index_path=index_path)
    if journal_target.read_bytes() != journal_bytes:
        raise AssertionError("outcome intake must not modify the original journal")

    _atomic_write_jsonl(Path(outcome_path), merged)
    status_target = Path(status_path)
    status_target.parent.mkdir(parents=True, exist_ok=True)
    status_target.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return merged, status
