from __future__ import annotations

from collections.abc import Mapping, Sequence
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from config import DATA_DIR


DEFAULT_PHASE_PATH = DATA_DIR / "market_phase_snapshot.json"
DEFAULT_MACRO_PATH = DATA_DIR / "macro_context_history.json"
DEFAULT_INDEX_PATH = DATA_DIR / "cache" / "index_daily_000300_SH.csv"
DEFAULT_STYLE_PATH = DATA_DIR / "historical_style_context.json"
DEFAULT_STRUCTURAL_PATH = DATA_DIR / "structural_hazard_dataset.json"
DEFAULT_LEDGER_PATH = DATA_DIR / "v15_point_in_time_snapshot_ledger.json"
DEFAULT_STATUS_PATH = DATA_DIR / "v15_point_in_time_snapshot_ledger_status.json"

SOURCE_GROUPS = ("macro", "broad_index", "style_context", "structural_context", "valuation")
REQUIRED_LINEAGE_FIELDS = (
    "observation_date",
    "release_date",
    "effective_date",
    "captured_at",
    "source_version",
    "source_path",
    "source_sha256",
)
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


def _read_json(path: str | Path) -> object:
    target = Path(path)
    if not target.exists():
        return {}
    return json.loads(target.read_text(encoding="utf-8"))


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _rows(payload: object, key: str) -> list[Mapping[str, object]]:
    value = _mapping(payload).get(key)
    return [row for row in value if isinstance(row, Mapping)] if isinstance(value, list) else []


def _sha256(path: str | Path) -> str | None:
    target = Path(path)
    if not target.exists():
        return None
    digest = hashlib.sha256()
    with target.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _latest_on_or_before(rows: Sequence[Mapping[str, object]], decision_date: str) -> Mapping[str, object]:
    selected: Mapping[str, object] = {}
    for row in rows:
        row_date = str(row.get("date") or row.get("trade_date") or "")
        if row_date > decision_date:
            break
        selected = row
    return selected


def _read_index_dates(path: str | Path) -> list[dict[str, object]]:
    target = Path(path)
    if not target.exists():
        return []
    with target.open("r", encoding="utf-8-sig", newline="") as handle:
        return sorted(
            (
                {"trade_date": str(row.get("trade_date") or ""), "ts_code": row.get("ts_code")}
                for row in csv.DictReader(handle)
                if row.get("trade_date")
            ),
            key=lambda row: str(row["trade_date"]),
        )


def _latest_trace_dates(row: Mapping[str, object]) -> tuple[str | None, str | None, str | None]:
    trace = _mapping(row.get("source_trace"))
    available = [item for item in trace.values() if isinstance(item, Mapping) and item.get("available") is True]
    observation_dates = [str(item["observation_date"]) for item in available if item.get("observation_date")]
    release_dates = [str(item["release_date"]) for item in available if item.get("release_date")]
    effective_dates = [str(item["effective_date"]) for item in available if item.get("effective_date")]
    return (
        max(observation_dates) if observation_dates else None,
        max(release_dates) if release_dates else None,
        max(effective_dates) if effective_dates else None,
    )


def source_group_lineage_complete(group: Mapping[str, object]) -> bool:
    if group.get("snapshot_available") is not True or group.get("hash_verified") is not True:
        return False
    if group.get("source_sha256_origin") != "historical_snapshot_file":
        return False
    if group.get("current_hash_is_historical_snapshot") is not True:
        return False
    source_sha256 = group.get("source_sha256")
    if not isinstance(source_sha256, str) or SHA256_PATTERN.fullmatch(source_sha256) is None:
        return False
    return all(group.get(field) not in (None, "") for field in REQUIRED_LINEAGE_FIELDS)


def _source_group_hash_verified(group: Mapping[str, object]) -> bool:
    source_sha256 = group.get("source_sha256")
    return (
        isinstance(source_sha256, str)
        and SHA256_PATTERN.fullmatch(source_sha256) is not None
        and group.get("source_sha256_origin") == "historical_snapshot_file"
        and group.get("hash_verified") is True
        and group.get("current_hash_is_historical_snapshot") is True
    )


def _group(
    group_id: str,
    *,
    observation_date: str | None,
    release_date: str | None,
    effective_date: str | None,
    source_path: str | None,
    current_file_sha256: str | None,
    transformation_version: str | None = None,
    reconstructed: bool = False,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "source_group": group_id,
        "snapshot_available": False,
        "observation_date": observation_date,
        "release_date": release_date,
        "effective_date": effective_date,
        "captured_at": None,
        "source_version": None,
        "source_path": source_path,
        "source_sha256": None,
        "source_sha256_origin": None,
        "current_file_sha256": current_file_sha256,
        "current_hash_is_historical_snapshot": False,
        "hash_verified": False,
        "transformation_version": transformation_version,
        "historically_reconstructed": reconstructed,
    }
    payload["lineage_complete"] = source_group_lineage_complete(payload)
    payload["strict_point_in_time_eligible"] = payload["lineage_complete"]
    payload["gaps"] = [
        field
        for field in REQUIRED_LINEAGE_FIELDS
        if payload.get(field) in (None, "")
    ] + [
        key
        for key, condition in (
            ("historical_snapshot_hash_origin", payload["source_sha256_origin"] != "historical_snapshot_file"),
            ("historical_snapshot_hash_verification", payload["hash_verified"] is not True),
        )
        if condition
    ]
    return payload


def _ledger_row(
    decision_date: str,
    *,
    macro_row: Mapping[str, object],
    index_row: Mapping[str, object],
    style_row: Mapping[str, object],
    structural_row: Mapping[str, object],
    hashes: Mapping[str, str | None],
    versions: Mapping[str, str | None],
) -> dict[str, object]:
    macro_observation, macro_release, macro_effective = _latest_trace_dates(macro_row)
    source_groups = {
        "macro": _group(
            "macro",
            observation_date=macro_observation,
            release_date=macro_release,
            effective_date=macro_effective,
            source_path="data/macro_context_history.json",
            current_file_sha256=hashes.get("macro"),
            transformation_version=versions.get("macro"),
        ),
        "broad_index": _group(
            "broad_index",
            observation_date=str(index_row.get("trade_date") or "") or None,
            release_date=None,
            effective_date=None,
            source_path="data/cache/index_daily_000300_SH.csv",
            current_file_sha256=hashes.get("broad_index"),
        ),
        "style_context": _group(
            "style_context",
            observation_date=str(style_row.get("date") or "") or None,
            release_date=None,
            effective_date=None,
            source_path="data/historical_style_context.json",
            current_file_sha256=hashes.get("style_context"),
            transformation_version=versions.get("style_context"),
            reconstructed=str(style_row.get("source") or "").startswith("historical_reconstruction"),
        ),
        "structural_context": _group(
            "structural_context",
            observation_date=str(structural_row.get("date") or "") or None,
            release_date=None,
            effective_date=None,
            source_path="data/structural_hazard_dataset.json",
            current_file_sha256=hashes.get("structural_context"),
        ),
        "valuation": _group(
            "valuation",
            observation_date=None,
            release_date=None,
            effective_date=None,
            source_path=None,
            current_file_sha256=None,
        ),
    }
    complete = all(bool(group["lineage_complete"]) for group in source_groups.values())
    return {
        "decision_date": decision_date,
        "snapshot_available": complete,
        "source_groups": source_groups,
        "row_lineage_complete": complete,
        "strict_point_in_time_eligible": complete,
        "missing_source_groups": [group_id for group_id, group in source_groups.items() if not group["lineage_complete"]],
    }


def validate_v15_point_in_time_snapshot_ledger(
    ledger: Mapping[str, object], status: Mapping[str, object]
) -> dict[str, object]:
    rows = ledger.get("rows")
    constraints = _mapping(status.get("constraints"))
    if ledger.get("phase") != "V15.6" or status.get("phase") != "V15.6":
        raise AssertionError("phase must be V15.6")
    if not isinstance(rows, list) or len(rows) != status.get("decision_date_count"):
        raise AssertionError("ledger row count must match decision_date_count")
    if status.get("ledger_status") not in {"ledger_gap_report_ready", "ledger_rebuilt"}:
        raise AssertionError("ledger_status is invalid")
    complete_count = 0
    eligible_count = 0
    hash_verified_count = 0
    valuation_snapshot_available_count = 0
    for row_index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise AssertionError(f"row {row_index} must be a mapping")
        source_groups = row.get("source_groups")
        if not isinstance(source_groups, Mapping) or set(source_groups) != set(SOURCE_GROUPS):
            raise AssertionError(f"row {row_index} must contain exactly the required source groups")

        computed_group_complete: dict[str, bool] = {}
        for group_id in SOURCE_GROUPS:
            group = source_groups.get(group_id)
            if not isinstance(group, Mapping):
                raise AssertionError(f"row {row_index} source group {group_id} must be a mapping")
            computed_complete = source_group_lineage_complete(group)
            computed_group_complete[group_id] = computed_complete
            if group.get("lineage_complete") is not computed_complete:
                raise AssertionError(f"row {row_index} source group {group_id} lineage_complete is forged")
            if group.get("strict_point_in_time_eligible") is not computed_complete:
                raise AssertionError(f"row {row_index} source group {group_id} eligibility is forged")
            if _source_group_hash_verified(group):
                hash_verified_count += 1

        computed_row_complete = all(computed_group_complete.values())
        computed_missing_groups = [
            group_id for group_id in SOURCE_GROUPS if not computed_group_complete[group_id]
        ]
        if row.get("row_lineage_complete") is not computed_row_complete:
            raise AssertionError(f"row {row_index} row_lineage_complete is forged")
        if row.get("strict_point_in_time_eligible") is not computed_row_complete:
            raise AssertionError(f"row {row_index} eligibility is forged")
        if row.get("snapshot_available") is not computed_row_complete:
            raise AssertionError(f"row {row_index} snapshot_available is forged")
        if row.get("missing_source_groups") != computed_missing_groups:
            raise AssertionError(f"row {row_index} missing_source_groups does not match computed gaps")

        complete_count += int(computed_row_complete)
        eligible_count += int(computed_row_complete)
        valuation_snapshot_available_count += int(computed_group_complete["valuation"])

    if complete_count != status.get("snapshot_complete_count") or eligible_count != status.get("strict_point_in_time_eligible_count"):
        raise AssertionError("status counts must match ledger rows")
    if hash_verified_count != status.get("hash_verified_count"):
        raise AssertionError("hash_verified_count must match computed verified source groups")
    if valuation_snapshot_available_count != status.get("valuation_snapshot_available_count"):
        raise AssertionError("valuation_snapshot_available_count must match computed valuation snapshots")
    if eligible_count > complete_count:
        raise AssertionError("eligible count cannot exceed complete count")
    if status.get("ledger_status") == "ledger_gap_report_ready" and complete_count == len(rows):
        raise AssertionError("gap report cannot claim every row complete")
    if status.get("ledger_status") == "ledger_rebuilt" and complete_count != len(rows):
        raise AssertionError("rebuilt status requires every row complete")
    if status.get("backtest_allowed") is not False:
        raise AssertionError("V15.6 is ledger-only and cannot allow backtesting")
    if status.get("promotion_ready") is not False:
        raise AssertionError("V15.6 cannot promote a strategy")
    for key in (
        "ledger_only",
        "does_not_run_backtest",
        "does_not_optimize_parameters",
        "does_not_generate_position",
        "does_not_generate_trade_signal",
        "no_order_generation",
        "no_broker_connection",
    ):
        if constraints.get(key) is not True:
            raise AssertionError(f"constraints.{key} must be true")
    return {
        "audit_status": "passed",
        "checked_phase": "V15.6",
        "checked_rows": len(rows),
        "checked_complete_count": complete_count,
        "checked_eligible_count": eligible_count,
        "checked_backtest_allowed": status.get("backtest_allowed"),
    }


def build_v15_point_in_time_snapshot_ledger(
    *,
    phase_path: str | Path = DEFAULT_PHASE_PATH,
    macro_path: str | Path = DEFAULT_MACRO_PATH,
    index_path: str | Path = DEFAULT_INDEX_PATH,
    style_path: str | Path = DEFAULT_STYLE_PATH,
    structural_path: str | Path = DEFAULT_STRUCTURAL_PATH,
) -> tuple[dict[str, object], dict[str, object]]:
    phase_payload = _read_json(phase_path)
    macro_payload = _read_json(macro_path)
    style_payload = _read_json(style_path)
    structural_payload = _read_json(structural_path)
    phase_rows = _rows(phase_payload, "historical_replay")
    macro_rows = _rows(macro_payload, "rows")
    style_rows = _rows(style_payload, "rows")
    structural_rows = [row for row in structural_payload if isinstance(row, Mapping)] if isinstance(structural_payload, list) else []
    index_rows = _read_index_dates(index_path)
    if not phase_rows:
        raise RuntimeError("market phase history is missing")

    decision_dates = [str(row.get("date") or "") for row in phase_rows if row.get("date")]
    macro_by_date = {str(row.get("date") or ""): row for row in macro_rows}
    ordered_style = sorted(style_rows, key=lambda row: str(row.get("date") or ""))
    ordered_structural = sorted(structural_rows, key=lambda row: str(row.get("date") or ""))
    hashes = {
        "macro": _sha256(macro_path),
        "broad_index": _sha256(index_path),
        "style_context": _sha256(style_path),
        "structural_context": _sha256(structural_path),
    }
    versions = {
        "macro": str(_mapping(macro_payload).get("metadata", {}).get("engine") or "") or None,
        "style_context": str(_mapping(style_payload).get("metadata", {}).get("engine") or "") or None,
    }
    ledger_rows = [
        _ledger_row(
            date,
            macro_row=macro_by_date.get(date, {}),
            index_row=_latest_on_or_before(index_rows, date),
            style_row=_latest_on_or_before(ordered_style, date),
            structural_row=_latest_on_or_before(ordered_structural, date),
            hashes=hashes,
            versions=versions,
        )
        for date in decision_dates
    ]
    complete_count = sum(1 for row in ledger_rows if row["row_lineage_complete"])
    eligible_count = sum(1 for row in ledger_rows if row["strict_point_in_time_eligible"])
    hash_verified_count = sum(
        1
        for row in ledger_rows
        for group in row["source_groups"].values()
        if group["hash_verified"] is True
    )
    valuation_available_count = sum(
        1 for row in ledger_rows if row["source_groups"]["valuation"]["snapshot_available"] is True
    )
    observations_by_group = {
        group_id: sum(
            1 for row in ledger_rows if row["source_groups"][group_id].get("observation_date")
        )
        for group_id in SOURCE_GROUPS
    }
    ledger: dict[str, object] = {
        "metadata": {
            "engine": "V15.6 Immutable Point-in-Time Source Snapshot Ledger",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": decision_dates[-1],
            "purpose": "Record per-decision-date source lineage availability without mistaking current caches for historical immutable snapshots.",
        },
        "phase": "V15.6",
        "source_group_schema": list(SOURCE_GROUPS),
        "required_lineage_fields": list(REQUIRED_LINEAGE_FIELDS),
        "rows": ledger_rows,
        "data_quality": {
            "current_file_hashes_are_not_historical_snapshot_hashes": True,
            "missing_values_are_null": True,
            "no_current_or_future_fill": True,
        },
    }
    ledger_status = "ledger_rebuilt" if complete_count == len(ledger_rows) else "ledger_gap_report_ready"
    status: dict[str, object] = {
        "metadata": {
            "engine": "V15.6 Immutable Point-in-Time Snapshot Ledger Status",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": decision_dates[-1],
            "source_ledger": "data/v15_point_in_time_snapshot_ledger.json",
        },
        "phase": "V15.6",
        "ledger_status": ledger_status,
        "decision_date_count": len(ledger_rows),
        "snapshot_complete_count": complete_count,
        "strict_point_in_time_eligible_count": eligible_count,
        "hash_verified_count": hash_verified_count,
        "valuation_snapshot_available_count": valuation_available_count,
        "backtest_allowed": False,
        "promotion_ready": False,
        "summary": {
            "phase": "V15.6",
            "ledger_status": ledger_status,
            "decision_date_count": len(ledger_rows),
            "snapshot_complete_count": complete_count,
            "strict_point_in_time_eligible_count": eligible_count,
            "hash_verified_count": hash_verified_count,
            "valuation_snapshot_available_count": valuation_available_count,
            "observations_available_by_group": observations_by_group,
            "backtest_allowed": False,
            "promotion_ready": False,
            "conclusion": "The per-date ledger is complete as a gap inventory, but no date has immutable historical snapshot lineage; overlay backtesting remains blocked.",
            "next_task": "Acquire or archive immutable historical source snapshots before strict phase reconstruction.",
        },
        "hash_semantics": {
            "historical_snapshot_sha256_field": "source_sha256",
            "current_local_file_sha256_field": "current_file_sha256",
            "equality_does_not_prove_historical_origin": True,
            "required_verified_origin": "historical_snapshot_file",
        },
        "constraints": {
            "ledger_only": True,
            "does_not_run_backtest": True,
            "does_not_optimize_parameters": True,
            "does_not_generate_position": True,
            "does_not_generate_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
        },
    }
    status["audit"] = validate_v15_point_in_time_snapshot_ledger(ledger, status)
    return ledger, status


def write_v15_point_in_time_snapshot_ledger(
    ledger: Mapping[str, object],
    status: Mapping[str, object],
    *,
    ledger_path: str | Path = DEFAULT_LEDGER_PATH,
    status_path: str | Path = DEFAULT_STATUS_PATH,
) -> tuple[Path, Path]:
    validate_v15_point_in_time_snapshot_ledger(ledger, status)
    ledger_target = Path(ledger_path)
    status_target = Path(status_path)
    ledger_target.parent.mkdir(parents=True, exist_ok=True)
    status_target.parent.mkdir(parents=True, exist_ok=True)
    ledger_target.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    status_target.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return ledger_target, status_target
