from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from config import DATA_DIR


DEFAULT_EXECUTION_PATH = DATA_DIR / "allocation_research_execution_runs.json"
DEFAULT_EVIDENCE_FREEZE_PATH = DATA_DIR / "allocation_research_evidence_freeze.json"
DEFAULT_OUTPUT_PATH = DATA_DIR / "allocation_research_result_review.json"

ALLOWED_REVIEW_STATUS = {"continue_research", "retain_research_only", "pause_research", "reject_for_now"}
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


def _by_id(rows: object, key: str) -> dict[str, Mapping[str, Any]]:
    return {str(_mapping(row).get(key)): _mapping(row) for row in _sequence(rows)}


def _hypothesis_review_row(run: Mapping[str, Any], freeze_row: Mapping[str, Any]) -> dict[str, object]:
    experiment_id = str(run.get("experiment_id"))
    result = run.get("result")
    if experiment_id == "H2":
        review_status = "continue_research"
        reason = "risk evidence is visible, but cross-scenario stability remains incomplete"
        decision = "continue only as non-investable risk-protection research"
    elif experiment_id == "H4" and result == "supported":
        review_status = "retain_research_only"
        reason = "contradiction-first gate has process value, but it is not an investable rule"
        decision = "retain as research governance gate only"
    else:
        review_status = "pause_research"
        reason = "execution result does not support continued research review"
        decision = "pause until new frozen evidence exists"
    return {
        "hypothesis_id": experiment_id,
        "status": review_status,
        "execution_result": result,
        "source_hypothesis_status": freeze_row.get("status"),
        "reason": reason,
        "review_decision": decision,
        "allowed_next_step": "manual_research_review_only",
        "promotion_allowed": False,
        "strategy_promotion": False,
        "allocation_ready": False,
        "investable_output": False,
    }


def validate_allocation_research_result_review(payload: Mapping[str, object]) -> dict[str, object]:
    summary = _mapping(payload.get("summary"))
    reviews = _mapping(payload.get("hypothesis_review"))
    constraints = _mapping(payload.get("constraints"))
    if summary.get("research_review_status") != "completed":
        raise AssertionError("research_review_status must be completed")
    if set(reviews.keys()) != {"H2", "H4"}:
        raise AssertionError("hypothesis_review must contain H2 and H4 only")
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
    for hypothesis_id, row in reviews.items():
        item = _mapping(row)
        if item.get("status") not in ALLOWED_REVIEW_STATUS:
            raise AssertionError(f"{hypothesis_id} invalid review status")
        for key in ("promotion_allowed", "strategy_promotion", "allocation_ready", "investable_output"):
            if item.get(key) is not False:
                raise AssertionError(f"{hypothesis_id}.{key} must be false")

    required_constraints = [
        "research_only",
        "result_review_only",
        "uses_v10_1_execution_only",
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
        "checked_review_count": len(reviews),
        "checked_constraints": required_constraints,
        "checked_forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }


def build_allocation_research_result_review(
    *,
    execution_path: str | Path = DEFAULT_EXECUTION_PATH,
    evidence_freeze_path: str | Path = DEFAULT_EVIDENCE_FREEZE_PATH,
) -> dict[str, object]:
    execution = _read_json(execution_path)
    evidence_freeze = _read_json(evidence_freeze_path)
    if not all((execution, evidence_freeze)):
        raise RuntimeError("V10.2 inputs missing; rebuild V10.1 and V9.9 artifacts first.")
    runs_by_id = _by_id(execution.get("execution_runs"), "experiment_id")
    freeze_by_id = _mapping(evidence_freeze.get("hypothesis_status"))
    if set(runs_by_id) != {"H2", "H4"}:
        raise RuntimeError("V10.2 expects H2 and H4 execution runs only.")
    hypothesis_review = {
        hypothesis_id: _hypothesis_review_row(run, _mapping(freeze_by_id.get(hypothesis_id)))
        for hypothesis_id, run in sorted(runs_by_id.items())
    }
    payload: dict[str, object] = {
        "metadata": {
            "engine": "V10.2 Allocation Research Result Review & Decision Boundary Audit",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": _mapping(execution.get("metadata")).get("as_of"),
            "input_files": {
                "v10_1_execution_runs": _project_path(execution_path),
                "v9_9_evidence_freeze": _project_path(evidence_freeze_path),
            },
            "input_hashes": {
                "v10_1_execution_runs": _file_hash(execution_path),
                "v9_9_evidence_freeze": _file_hash(evidence_freeze_path),
            },
            "purpose": "Review V10.1 research execution results and freeze decision boundaries without producing strategy, allocation, asset, ETF, weight, optimization, or trade outputs.",
        },
        "summary": {
            "research_review_status": "completed",
            "reviewed_hypothesis_count": len(hypothesis_review),
            "continue_research_count": sum(1 for row in hypothesis_review.values() if row["status"] == "continue_research"),
            "retain_research_only_count": sum(1 for row in hypothesis_review.values() if row["status"] == "retain_research_only"),
            "pause_research_count": sum(1 for row in hypothesis_review.values() if row["status"] == "pause_research"),
            "reject_for_now_count": sum(1 for row in hypothesis_review.values() if row["status"] == "reject_for_now"),
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
            "conclusion": "allocation_research_result_review_completed_no_strategy_no_allocation",
            "key_read": "V10.2 reviews H2/H4 execution results only: H2 continues research without promotion; H4 is retained as research-only process gate. No allocation output is ready.",
        },
        "hypothesis_review": hypothesis_review,
        "decision_boundary_audit": {
            "h2_boundary": "risk_protection_research_only_not_stable_enough_for_configuration",
            "h4_boundary": "contradiction_gate_governance_only_not_investable_rule",
            "global_boundary": "manual_research_review_only_no_strategy_no_allocation_no_trade",
        },
        "source_layer_evidence": {
            "v10_1_summary": execution.get("summary") or {},
            "v9_9_summary": evidence_freeze.get("summary") or {},
        },
        "time_safety": {
            "uses_v10_1_execution_only": True,
            "uses_v9_9_evidence_freeze_only": True,
            "input_hashes_recorded": True,
            "does_not_recompute_features": True,
            "does_not_recompute_forward_returns": True,
            "does_not_run_market_backtest": True,
            "no_result_based_parameter_change": True,
        },
        "constraints": {
            "research_only": True,
            "result_review_only": True,
            "uses_v10_1_execution_only": True,
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
    payload["audit"] = validate_allocation_research_result_review(payload)
    return payload


def write_allocation_research_result_review(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
