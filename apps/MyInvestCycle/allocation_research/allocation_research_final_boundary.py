from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from config import DATA_DIR


DEFAULT_RESULT_REVIEW_PATH = DATA_DIR / "allocation_research_result_review.json"
DEFAULT_EVIDENCE_FREEZE_PATH = DATA_DIR / "allocation_research_evidence_freeze.json"
DEFAULT_OUTPUT_PATH = DATA_DIR / "allocation_research_final_boundary.json"

ALLOWED_DIRECTION_STATUS = {
    "continue_external_validation",
    "research_governance_only",
    "frozen_no_external_validation",
}
FORBIDDEN_OUTPUT_KEYS = {
    "asset_selection",
    "broker_order",
    "buy_signal",
    "etf_mapping",
    "exposure_percent",
    "optimization",
    "portfolio_weight",
    "rebalance_instruction",
    "sell_signal",
    "top_n",
    "trade_signal",
}


def _read_json(path: str | Path) -> dict[str, object]:
    target = Path(path)
    if not target.exists():
        return {}
    payload = json.loads(target.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else []


def _project_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _file_hash(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _walk_keys(value: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            keys.append(str(key))
            keys.extend(_walk_keys(item))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            keys.extend(_walk_keys(item))
    return keys


def _direction_from_review(hypothesis_id: str, review_row: Mapping[str, Any], freeze_row: Mapping[str, Any]) -> dict[str, object]:
    if hypothesis_id == "H2":
        status = "continue_external_validation"
        decision_reason = "risk evidence is visible but stability is incomplete, so only external validation may continue"
        allowed_next_step = "external_validation_protocol_only"
    elif hypothesis_id == "H4":
        status = "research_governance_only"
        decision_reason = "contradiction-first gate is useful as research governance, not as an investable rule"
        allowed_next_step = "governance_checklist_only"
    else:
        status = "frozen_no_external_validation"
        decision_reason = "prior evidence remains frozen and not eligible for external validation"
        allowed_next_step = "archive_until_new_frozen_evidence"
    return {
        "hypothesis_id": hypothesis_id,
        "status": status,
        "source_review_status": review_row.get("status") if review_row else None,
        "source_freeze_status": freeze_row.get("status"),
        "decision_reason": decision_reason,
        "allowed_next_step": allowed_next_step,
        "promotion_allowed": False,
        "strategy_promotion": False,
        "allocation_ready": False,
        "investable_output": False,
    }


def validate_allocation_research_final_boundary(payload: Mapping[str, object]) -> dict[str, object]:
    summary = _mapping(payload.get("summary"))
    directions = _mapping(payload.get("directions"))
    constraints = _mapping(payload.get("constraints"))
    if summary.get("research_phase_status") != "completed":
        raise AssertionError("research_phase_status must be completed")
    if set(directions.keys()) != {"H1", "H2", "H3", "H4"}:
        raise AssertionError("directions must contain H1-H4")
    for key in (
        "promotion_allowed",
        "strategy_promotion",
        "allocation_ready",
        "investable_output",
        "investable_output_generated",
        "ready_for_asset_selection",
        "ready_for_etf_mapping",
        "ready_for_weight_generation",
        "ready_for_optimization",
        "ready_for_trade",
    ):
        if summary.get(key) is not False:
            raise AssertionError(f"summary.{key} must be false")
    for hypothesis_id, row in directions.items():
        item = _mapping(row)
        if item.get("status") not in ALLOWED_DIRECTION_STATUS:
            raise AssertionError(f"{hypothesis_id} invalid direction status")
        for key in ("promotion_allowed", "strategy_promotion", "allocation_ready", "investable_output"):
            if item.get(key) is not False:
                raise AssertionError(f"{hypothesis_id}.{key} must be false")

    required_constraints = [
        "research_only",
        "final_boundary_only",
        "uses_v10_2_result_review_only",
        "uses_v9_9_evidence_freeze_only",
        "does_not_select_assets",
        "does_not_map_etf",
        "does_not_generate_portfolio_weight",
        "does_not_generate_allocation",
        "does_not_optimize_parameters",
        "does_not_generate_trade_signal",
        "no_order_generation",
        "no_broker_connection",
    ]
    for key in required_constraints:
        if constraints.get(key) is not True:
            raise AssertionError(f"constraints.{key} must be true")

    disallowed_payload_keys = FORBIDDEN_OUTPUT_KEYS.intersection(set(_walk_keys(payload)) - {"forbidden_outputs"})
    if disallowed_payload_keys:
        raise AssertionError(f"forbidden output keys found outside forbidden_outputs: {sorted(disallowed_payload_keys)}")

    return {
        "audit_status": "passed",
        "checked_direction_count": len(directions),
        "checked_constraints": required_constraints,
        "checked_forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }


def build_allocation_research_final_boundary(
    *,
    result_review_path: str | Path = DEFAULT_RESULT_REVIEW_PATH,
    evidence_freeze_path: str | Path = DEFAULT_EVIDENCE_FREEZE_PATH,
) -> dict[str, object]:
    result_review = _read_json(result_review_path)
    evidence_freeze = _read_json(evidence_freeze_path)
    if not all((result_review, evidence_freeze)):
        raise RuntimeError("V10.3 inputs missing; rebuild V10.2 and V9.9 artifacts first.")
    reviews = _mapping(result_review.get("hypothesis_review"))
    freeze_status = _mapping(evidence_freeze.get("hypothesis_status"))
    directions = {
        hypothesis_id: _direction_from_review(hypothesis_id, _mapping(reviews.get(hypothesis_id)), _mapping(freeze_status.get(hypothesis_id)))
        for hypothesis_id in ("H1", "H2", "H3", "H4")
    }
    payload: dict[str, object] = {
        "metadata": {
            "engine": "V10.3 Allocation Research Final Boundary Decision",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": _mapping(result_review.get("metadata")).get("as_of"),
            "input_files": {
                "v10_2_result_review": _project_path(result_review_path),
                "v9_9_evidence_freeze": _project_path(evidence_freeze_path),
            },
            "input_hashes": {
                "v10_2_result_review": _file_hash(result_review_path),
                "v9_9_evidence_freeze": _file_hash(evidence_freeze_path),
            },
            "purpose": "Freeze final V9-V10 allocation research boundaries without producing strategy, allocation, asset, ETF, weight, optimization, or trade outputs.",
        },
        "summary": {
            "research_phase_status": "completed",
            "direction_count": len(directions),
            "continue_external_validation_count": sum(1 for row in directions.values() if row["status"] == "continue_external_validation"),
            "research_governance_only_count": sum(1 for row in directions.values() if row["status"] == "research_governance_only"),
            "frozen_no_external_validation_count": sum(1 for row in directions.values() if row["status"] == "frozen_no_external_validation"),
            "promotion_allowed": False,
            "strategy_promotion": False,
            "allocation_ready": False,
            "investable_output": False,
            "investable_output_generated": False,
            "ready_for_asset_selection": False,
            "ready_for_etf_mapping": False,
            "ready_for_weight_generation": False,
            "ready_for_optimization": False,
            "ready_for_trade": False,
            "conclusion": "allocation_research_final_boundary_completed_no_strategy_no_allocation",
            "key_read": "Final V9-V10 boundary: H2 may continue external validation only; H4 remains research governance only; H1/H3 stay frozen. No allocation output is ready.",
        },
        "directions": directions,
        "source_layer_evidence": {
            "v10_2_summary": result_review.get("summary") or {},
            "v9_9_summary": evidence_freeze.get("summary") or {},
        },
        "time_safety": {
            "uses_v10_2_result_review_only": True,
            "uses_v9_9_evidence_freeze_only": True,
            "input_hashes_recorded": True,
            "does_not_recompute_features": True,
            "does_not_recompute_forward_returns": True,
            "does_not_run_market_backtest": True,
            "no_result_based_parameter_change": True,
        },
        "constraints": {
            "research_only": True,
            "final_boundary_only": True,
            "uses_v10_2_result_review_only": True,
            "uses_v9_9_evidence_freeze_only": True,
            "does_not_select_assets": True,
            "does_not_map_etf": True,
            "does_not_generate_portfolio_weight": True,
            "does_not_generate_allocation": True,
            "does_not_optimize_parameters": True,
            "does_not_generate_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
        },
        "forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }
    payload["audit"] = validate_allocation_research_final_boundary(payload)
    return payload


def write_allocation_research_final_boundary(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
