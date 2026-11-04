from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from config import DATA_DIR


DEFAULT_PHASE1_PATH = DATA_DIR / "allocation_experiment_phase1_validation.json"
DEFAULT_VALIDATION_PLAN_PATH = DATA_DIR / "allocation_validation_plan.json"
DEFAULT_EXPERIMENT_TEMPLATES_PATH = DATA_DIR / "allocation_experiment_templates.json"
DEFAULT_OUTPUT_PATH = DATA_DIR / "research_candidate_promotion_gate.json"

ALLOWED_RESEARCH_STATUS = {"continue_research", "freeze", "reject_for_now"}
FORBIDDEN_OUTPUT_KEYS = {
    "asset_selection",
    "broker_order",
    "buy_signal",
    "etf_mapping",
    "exposure_percent",
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


def _project_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


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


def _gate_row(result: Mapping[str, Any]) -> dict[str, object]:
    experiment_id = str(result.get("experiment_id") or "unknown")
    status = str(result.get("validation_status") or "inconclusive")
    if status == "supported":
        research_status = "continue_research"
        reasons = ["supported_validation", "phase1_research_status_positive"]
        next_step = "continue_non_investable_research"
    elif status == "unsupported":
        research_status = "reject_for_now"
        reasons = ["unsupported_validation", "do_not_retest_without_new_evidence"]
        next_step = "archive_until_new_research_evidence"
    else:
        research_status = "freeze"
        reasons = ["inconclusive_validation", "wait_for_stronger_evidence"]
        next_step = "freeze_until_required_evidence_improves"
    return {
        "hypothesis_id": experiment_id,
        "validation_status": status,
        "research_status": research_status,
        "promotion_reason": reasons,
        "next_research_step": next_step,
        "promotion_allowed": False,
        "promotion_to_strategy": False,
        "promotion_to_allocation": False,
        "investable_output": False,
        "boundary": "Research-stage gate only; do not convert to assets, ETFs, weights, allocation, or trades.",
    }


def validate_research_candidate_promotion_gate(payload: Mapping[str, object]) -> dict[str, object]:
    summary = _mapping(payload.get("summary"))
    constraints = _mapping(payload.get("constraints"))
    gate_rows = payload.get("gate_results")
    if not isinstance(gate_rows, list) or not gate_rows:
        raise AssertionError("gate_results must be a non-empty list")

    for key in (
        "promotion_allowed",
        "strategy_promotion",
        "allocation_promotion",
        "investable_output_generated",
        "investable_output",
        "ready_for_asset_selection",
        "ready_for_etf_mapping",
        "ready_for_weight_generation",
        "ready_for_trade",
    ):
        if summary.get(key) is not False:
            raise AssertionError(f"summary.{key} must be false")

    required_constraints = [
        "research_only",
        "gate_audit_only",
        "does_not_select_assets",
        "does_not_map_etf",
        "does_not_generate_portfolio_weight",
        "does_not_generate_allocation",
        "does_not_generate_trade_signal",
        "no_order_generation",
        "no_broker_connection",
    ]
    for key in required_constraints:
        if constraints.get(key) is not True:
            raise AssertionError(f"constraints.{key} must be true")

    for row in gate_rows:
        item = _mapping(row)
        if item.get("research_status") not in ALLOWED_RESEARCH_STATUS:
            raise AssertionError(f"{item.get('hypothesis_id')} invalid research_status")
        if item.get("promotion_allowed") is not False:
            raise AssertionError("promotion must remain false")
        if item.get("promotion_to_strategy") is not False:
            raise AssertionError("strategy promotion must remain false")
        if item.get("promotion_to_allocation") is not False:
            raise AssertionError("allocation promotion must remain false")
        if item.get("investable_output") is not False:
            raise AssertionError("investable output must remain false")

    disallowed_payload_keys = FORBIDDEN_OUTPUT_KEYS.intersection(set(_walk_keys(payload)) - {"forbidden_outputs"})
    if disallowed_payload_keys:
        raise AssertionError(f"forbidden output keys found outside forbidden_outputs: {sorted(disallowed_payload_keys)}")

    return {
        "audit_status": "passed",
        "checked_gate_count": len(gate_rows),
        "checked_constraints": required_constraints,
        "checked_forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }


def build_research_candidate_promotion_gate(
    *,
    phase1_path: str | Path = DEFAULT_PHASE1_PATH,
    validation_plan_path: str | Path = DEFAULT_VALIDATION_PLAN_PATH,
    experiment_templates_path: str | Path = DEFAULT_EXPERIMENT_TEMPLATES_PATH,
) -> dict[str, object]:
    phase1 = _read_json(phase1_path)
    validation_plan = _read_json(validation_plan_path)
    templates = _read_json(experiment_templates_path)
    if not all((phase1, validation_plan, templates)):
        raise RuntimeError("V9.7 inputs missing; rebuild V9.3/V9.4/V9.6 artifacts.")
    phase1_results = phase1.get("validation_results")
    if not isinstance(phase1_results, list) or not phase1_results:
        raise RuntimeError("V9.6 validation results missing.")
    gate_results = [_gate_row(_mapping(row)) for row in phase1_results]
    status_counts = {
        status: sum(1 for row in gate_results if row["research_status"] == status)
        for status in sorted(ALLOWED_RESEARCH_STATUS)
    }
    payload: dict[str, object] = {
        "metadata": {
            "engine": "V9.7 Research Candidate Promotion Gate Audit",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": _mapping(phase1.get("metadata")).get("as_of"),
            "input_files": {
                "v9_6_phase1_validation": _project_path(phase1_path),
                "v9_3_validation_plan": _project_path(validation_plan_path),
                "v9_4_experiment_templates": _project_path(experiment_templates_path),
            },
            "purpose": "Audit which hypotheses may continue research without promoting any strategy, allocation, asset, ETF, weight, or trade output.",
        },
        "summary": {
            "gate_count": len(gate_results),
            "continue_research_count": status_counts.get("continue_research", 0),
            "freeze_count": status_counts.get("freeze", 0),
            "reject_for_now_count": status_counts.get("reject_for_now", 0),
            "promotion_allowed": False,
            "strategy_promotion": False,
            "allocation_promotion": False,
            "investable_output_generated": False,
            "investable_output": False,
            "ready_for_asset_selection": False,
            "ready_for_etf_mapping": False,
            "ready_for_weight_generation": False,
            "ready_for_trade": False,
            "conclusion": "research_candidate_gate_completed_no_strategy_promotion",
            "key_read": "H2 and H4 may continue research; H1 and H3 remain frozen. No hypothesis is promoted to strategy, allocation, asset, ETF, weight, or trade output.",
        },
        "source_layer_evidence": {
            "phase1_summary": phase1.get("summary") or {},
            "validation_plan_summary": validation_plan.get("summary") or {},
            "experiment_template_summary": templates.get("summary") or {},
        },
        "gate_results": gate_results,
        "constraints": {
            "research_only": True,
            "gate_audit_only": True,
            "does_not_select_assets": True,
            "does_not_map_etf": True,
            "does_not_generate_portfolio_weight": True,
            "does_not_generate_allocation": True,
            "does_not_generate_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
        },
        "forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }
    payload["audit"] = validate_research_candidate_promotion_gate(payload)
    return payload


def write_research_candidate_promotion_gate(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
