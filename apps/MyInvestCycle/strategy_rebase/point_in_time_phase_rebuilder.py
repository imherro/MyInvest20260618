from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from config import DATA_DIR


DEFAULT_PHASE_PATH = DATA_DIR / "market_phase_snapshot.json"
DEFAULT_MACRO_PATH = DATA_DIR / "macro_context_history.json"
DEFAULT_STYLE_PATH = DATA_DIR / "historical_style_context.json"
DEFAULT_OUTPUT_PATH = DATA_DIR / "v15_point_in_time_phase_rebuild_status.json"


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


def _macro_time_safe(row: Mapping[str, object]) -> bool:
    quality = _mapping(row.get("data_quality"))
    return (
        quality.get("release_date_lte_signal_date") is True
        and quality.get("effective_date_lte_signal_date") is True
    )


def _row_has_strict_lineage(row: Mapping[str, object]) -> bool:
    lineage = _mapping(row.get("point_in_time_lineage"))
    required = (
        "captured_at",
        "source_release_date",
        "source_effective_date",
        "source_version",
        "source_sha256",
    )
    return all(lineage.get(field) not in (None, "") for field in required)


def _latest_on_or_before(
    rows: Sequence[Mapping[str, object]], decision_date: str
) -> Mapping[str, object]:
    selected: Mapping[str, object] = {}
    for row in rows:
        row_date = str(row.get("date") or "")
        if row_date > decision_date:
            break
        selected = row
    return selected


def validate_v15_point_in_time_phase_rebuild_status(payload: Mapping[str, object]) -> dict[str, object]:
    constraints = _mapping(payload.get("constraints"))
    if payload.get("phase") != "V15.5":
        raise AssertionError("phase must be V15.5")
    status = payload.get("strict_point_in_time_phase_status")
    if status not in {"rebuilt", "gap_report_ready"}:
        raise AssertionError("strict_point_in_time_phase_status is invalid")
    verified = payload.get("publication_time_lineage_verified") is True
    gaps = payload.get("gaps")
    if not isinstance(gaps, list):
        raise AssertionError("gaps must be a list")
    if status == "rebuilt" and (not verified or payload.get("gap_count") != 0):
        raise AssertionError("rebuilt status requires verified lineage and zero gaps")
    if status == "gap_report_ready":
        if verified or not isinstance(payload.get("gap_count"), int) or int(payload["gap_count"]) <= 0:
            raise AssertionError("gap report must keep lineage unverified and report gaps")
        if not payload.get("unverified_dates"):
            raise AssertionError("gap report must list unverified dates")
    if payload.get("uses_future_returns") is not False:
        raise AssertionError("phase reconstruction must not use future returns")
    if payload.get("promotion_ready") is not False:
        raise AssertionError("V15.5 is not a promotion decision")
    for key in (
        "does_not_run_backtest",
        "does_not_generate_position",
        "does_not_generate_trade_signal",
        "no_order_generation",
        "no_broker_connection",
    ):
        if constraints.get(key) is not True:
            raise AssertionError(f"constraints.{key} must be true")
    return {
        "audit_status": "passed",
        "checked_phase": "V15.5",
        "checked_status": status,
        "checked_gap_count": payload.get("gap_count"),
        "checked_unverified_date_count": len(payload.get("unverified_dates") or []),
        "checked_publication_time_lineage_verified": verified,
    }


def build_v15_point_in_time_phase_rebuild_status(
    *,
    phase_path: str | Path = DEFAULT_PHASE_PATH,
    macro_path: str | Path = DEFAULT_MACRO_PATH,
    style_path: str | Path = DEFAULT_STYLE_PATH,
) -> dict[str, object]:
    phase_payload = _read_json(phase_path)
    macro_payload = _read_json(macro_path)
    style_payload = _read_json(style_path)
    phase_rows = _rows(phase_payload, "historical_replay")
    macro_rows = _rows(macro_payload, "rows")
    style_rows = _rows(style_payload, "rows")
    if not phase_rows:
        raise RuntimeError("market phase history is missing")

    phase_dates = [str(row.get("date") or "") for row in phase_rows if row.get("date")]
    macro_by_date = {str(row.get("date") or ""): row for row in macro_rows}
    ordered_style_rows = sorted(style_rows, key=lambda row: str(row.get("date") or ""))
    style_by_phase_date = {
        date: _latest_on_or_before(ordered_style_rows, date)
        for date in phase_dates
    }
    macro_safe_dates = [date for date in phase_dates if _macro_time_safe(macro_by_date.get(date, {}))]
    strict_lineage_dates = [date for date, row in zip(phase_dates, phase_rows, strict=False) if _row_has_strict_lineage(row)]
    reconstructed_dates = [
        date
        for date in phase_dates
        if str(_mapping(style_by_phase_date.get(date, {})).get("source") or "").startswith("historical_reconstruction")
    ]
    structural_complete_dates = [
        date
        for date in phase_dates
        if _mapping(_mapping(style_by_phase_date.get(date, {})).get("data_quality")).get("structural_features_available") is True
    ]
    valuation_available_dates = [
        date
        for date in phase_dates
        if any(
            _mapping(_mapping(macro_by_date.get(date, {})).get("macro_context")).get(field) is not None
            for field in ("PE_percentile", "PB_percentile", "ERP")
        )
    ]

    gaps: list[dict[str, object]] = []
    if len(strict_lineage_dates) != len(phase_dates):
        gaps.append(
            {
                "gap_id": "phase_row_publication_lineage",
                "severity": "blocking",
                "affected_dates": len(phase_dates) - len(strict_lineage_dates),
                "finding": "Phase rows do not retain captured_at, source release/effective dates, source version, and source hash together.",
                "required_remediation": "Persist immutable as-of snapshots and row-level lineage before rebuilding labels.",
            }
        )
    if reconstructed_dates:
        gaps.append(
            {
                "gap_id": "historically_reconstructed_style_context",
                "severity": "blocking",
                "affected_dates": len(reconstructed_dates),
                "finding": "Style, breadth, crowding, and price-extension inputs were reconstructed later from current local caches.",
                "required_remediation": "Archive the exact source universe and price files available at each decision date.",
            }
        )
    if len(structural_complete_dates) != len(phase_dates):
        gaps.append(
            {
                "gap_id": "incomplete_structural_context",
                "severity": "material",
                "affected_dates": len(phase_dates) - len(structural_complete_dates),
                "finding": "Trend, breadth, liquidity, volatility, or pressure fields are missing for part of the replay.",
                "required_remediation": "Build time-stamped structural inputs for the missing dates without filling nulls with zero.",
            }
        )
    if len(valuation_available_dates) != len(phase_dates):
        gaps.append(
            {
                "gap_id": "historical_valuation_unavailable",
                "severity": "blocking_for_late_cycle_overlay",
                "affected_dates": len(phase_dates) - len(valuation_available_dates),
                "finding": "PE percentile, PB percentile, and ERP history are unavailable on replay dates.",
                "required_remediation": "Add release-safe historical valuation observations with source lineage.",
            }
        )
    if len(macro_safe_dates) != len(phase_dates):
        gaps.append(
            {
                "gap_id": "macro_release_effective_alignment",
                "severity": "blocking",
                "affected_dates": len(phase_dates) - len(macro_safe_dates),
                "finding": "Not every phase date has a macro row proven release-date and effective-date safe.",
                "required_remediation": "Materialize a macro row for every phase date using only records available then.",
            }
        )

    verified = not gaps and len(strict_lineage_dates) == len(phase_dates)
    unverified_dates = [] if verified else phase_dates
    status = "rebuilt" if verified else "gap_report_ready"
    payload: dict[str, object] = {
        "metadata": {
            "engine": "V15.5 Strict Point-in-Time Phase Reconstruction Audit",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": phase_dates[-1],
            "purpose": "Determine whether historical market phases can be reproduced from immutable information available at each decision date.",
        },
        "phase": "V15.5",
        "strict_point_in_time_phase_status": status,
        "release_date_alignment": len(macro_safe_dates) == len(phase_dates) and verified,
        "effective_date_alignment": len(macro_safe_dates) == len(phase_dates) and verified,
        "uses_future_returns": False,
        "uses_reconstructed_labels": bool(reconstructed_dates),
        "publication_time_lineage_verified": verified,
        "unverified_dates": unverified_dates,
        "gap_count": len(gaps),
        "promotion_ready": False,
        "summary": {
            "phase": "V15.5",
            "status": status,
            "phase_row_count": len(phase_dates),
            "verified_date_count": 0 if not verified else len(phase_dates),
            "unverified_date_count": len(unverified_dates),
            "macro_release_effective_safe_count": len(macro_safe_dates),
            "strict_lineage_count": len(strict_lineage_dates),
            "reconstructed_style_date_count": len(reconstructed_dates),
            "structural_context_complete_count": len(structural_complete_dates),
            "valuation_available_count": len(valuation_available_dates),
            "gap_count": len(gaps),
            "publication_time_lineage_verified": verified,
            "promotion_ready": False,
            "conclusion": (
                "Current phase history is future-return-free but reconstructed from present local caches; it is not strict point-in-time evidence. "
                "V15.3/V15.4 must remain research-only until immutable source snapshots and valuation history exist."
            ),
            "next_task": "Close lineage and valuation gaps before any V15.6 overlay backtest.",
        },
        "source_audit": {
            "phase_snapshot": {"path": "data/market_phase_snapshot.json", "sha256_now": _sha256(phase_path), "row_count": len(phase_rows)},
            "macro_context": {"path": "data/macro_context_history.json", "sha256_now": _sha256(macro_path), "row_count": len(macro_rows)},
            "style_context": {"path": "data/historical_style_context.json", "sha256_now": _sha256(style_path), "row_count": len(style_rows)},
            "current_file_hashes_are_not_historical_snapshot_hashes": True,
        },
        "gaps": gaps,
        "lineage_contract": {
            "required_row_fields": [
                "decision_date",
                "captured_at",
                "source_observation_date",
                "source_release_date",
                "source_effective_date",
                "source_version",
                "source_sha256",
                "transformation_version",
            ],
            "execution_timing": "Inputs observed by close on t may only affect returns from t+1.",
            "missing_values": "Remain null; never fill unavailable history with zero or a current value.",
        },
        "constraints": {
            "audit_only": True,
            "does_not_run_backtest": True,
            "does_not_generate_position": True,
            "does_not_generate_trade_signal": True,
            "no_parameter_optimization": True,
            "no_order_generation": True,
            "no_broker_connection": True,
        },
    }
    payload["audit"] = validate_v15_point_in_time_phase_rebuild_status(payload)
    return payload


def write_v15_point_in_time_phase_rebuild_status(
    payload: Mapping[str, object], output_path: str | Path = DEFAULT_OUTPUT_PATH
) -> Path:
    validate_v15_point_in_time_phase_rebuild_status(payload)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target
