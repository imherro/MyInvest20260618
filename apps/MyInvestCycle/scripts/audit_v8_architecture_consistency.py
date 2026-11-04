from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = ROOT / "docs" / "research_decision_v8_architecture.md"
DATA_DIR = ROOT / "data"


ARTIFACTS = {
    "V8.1": DATA_DIR / "research_decision_context.json",
    "V8.2": DATA_DIR / "research_decision_scenario_audit.json",
    "V8.3": DATA_DIR / "research_decision_contradiction.json",
}


REQUIRED_DOC_TOKENS = [
    "V8.1 Research Decision Context",
    "V8.2 Historical Scenario Audit",
    "V8.3 Contradiction Attribution",
    "Score: rejected",
    "Ranking: rejected",
    "Asset Selection: rejected",
    "Top N: rejected",
    "Allocation: rejected",
    "ETF Weight: rejected",
    "Trading: rejected",
    "New State: rejected",
    "V6/V7 Modification: rejected",
    "scenario_explanation_audit_only_no_strategy",
    "contradiction_attribution_research_only_no_rule_change",
]


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise AssertionError(f"missing artifact: {path.relative_to(ROOT)}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AssertionError(f"artifact is not an object: {path.relative_to(ROOT)}")
    return payload


def _summary(payload: dict[str, Any], layer: str) -> dict[str, Any]:
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        raise AssertionError(f"{layer} missing summary")
    return summary


def _constraints(payload: dict[str, Any], layer: str) -> dict[str, Any]:
    constraints = payload.get("constraints")
    if not isinstance(constraints, dict):
        raise AssertionError(f"{layer} missing constraints")
    return constraints


def _assert_ready_flags_false(summary: dict[str, Any], layer: str) -> None:
    for key in (
        "ready_for_scoring",
        "ready_for_ranking",
        "ready_for_allocation",
        "ready_for_trade",
    ):
        if summary.get(key) is not False:
            raise AssertionError(f"{layer} {key} must be false")


def _assert_no_output_constraints(constraints: dict[str, Any], layer: str) -> None:
    required = (
        "does_not_create_opportunity_score",
        "does_not_rank_assets",
        "does_not_select_top_assets",
        "does_not_generate_position",
        "no_trade_signal",
        "no_broker_connection",
        "no_parameter_optimization",
    )
    for key in required:
        if constraints.get(key) is not True:
            raise AssertionError(f"{layer} constraint {key} must be true")


def main() -> int:
    if not DOC_PATH.exists():
        raise AssertionError(f"missing architecture doc: {DOC_PATH.relative_to(ROOT)}")
    doc_text = DOC_PATH.read_text(encoding="utf-8")
    missing_tokens = [token for token in REQUIRED_DOC_TOKENS if token not in doc_text]
    if missing_tokens:
        raise AssertionError(f"architecture doc missing tokens: {missing_tokens}")

    payloads = {layer: _load_json(path) for layer, path in ARTIFACTS.items()}
    summaries = {layer: _summary(payload, layer) for layer, payload in payloads.items()}
    constraints = {layer: _constraints(payload, layer) for layer, payload in payloads.items()}

    for layer, summary in summaries.items():
        _assert_ready_flags_false(summary, layer)
    for layer, item in constraints.items():
        _assert_no_output_constraints(item, layer)

    v81 = summaries["V8.1"]
    if v81.get("decision_context") != "risk_controlled_opportunity_watch":
        raise AssertionError("V8.1 decision_context must stay risk_controlled_opportunity_watch")
    if v81.get("research_posture") != "observe_without_selection":
        raise AssertionError("V8.1 research_posture must stay observe_without_selection")

    v82 = summaries["V8.2"]
    if v82.get("scenario_count") != 6 or v82.get("covered_scenario_count") != 6:
        raise AssertionError("V8.2 must keep 6 covered scenarios")
    if v82.get("conclusion") != "scenario_explanation_audit_only_no_strategy":
        raise AssertionError("V8.2 conclusion must reject strategy conversion")

    v83 = summaries["V8.3"]
    if v83.get("focus_scenario_count") != 5 or v83.get("attribution_count") != 5:
        raise AssertionError("V8.3 must keep 5 focused scenario attributions")
    if v83.get("conclusion") != "contradiction_attribution_research_only_no_rule_change":
        raise AssertionError("V8.3 conclusion must reject rule changes")
    v83_constraints = constraints["V8.3"]
    for key in ("does_not_modify_v6", "does_not_modify_v7", "does_not_add_state"):
        if v83_constraints.get(key) is not True:
            raise AssertionError(f"V8.3 constraint {key} must be true")

    print(
        "v8 architecture consistency ok | "
        f"v8.1={v81.get('decision_context')} | "
        f"v8.2={v82.get('consistency_counts')} | "
        f"v8.3={v83.get('contradiction_type_counts')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
