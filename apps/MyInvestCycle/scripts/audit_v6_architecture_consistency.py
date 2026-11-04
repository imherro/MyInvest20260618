from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import DATA_DIR


DOC_PATH = ROOT_DIR / "docs" / "adaptive_exposure_v6_architecture.md"
REQUIRED_ARTIFACTS = (
    "exposure_gradient_analysis.json",
    "risk_gradient_robustness.json",
    "exposure_context_score_audit.json",
    "protection_score_validation.json",
    "two_axis_context_validation.json",
    "context_information_attribution.json",
)
RETAINED_LAYERS = {
    "layer_1_risk_gradient",
    "layer_2_protection_score",
    "layer_3_two_axis_context",
}
FORBIDDEN_READY_FLAGS = ("ready_for_mapper_change", "ready_for_exposure_change")


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AssertionError(f"{path.name} must contain a JSON object")
    return payload


def _assert_doc_contains(doc: str, terms: list[str]) -> None:
    missing = [term for term in terms if term not in doc]
    if missing:
        raise AssertionError(f"architecture doc missing required terms: {missing}")


def _assert_constraints(payload: dict[str, object], artifact_name: str) -> None:
    summary = payload.get("summary")
    constraints = payload.get("constraints")
    data_quality = payload.get("data_quality")
    if not isinstance(summary, dict):
        raise AssertionError(f"{artifact_name} missing summary")
    if not isinstance(constraints, dict):
        raise AssertionError(f"{artifact_name} missing constraints")
    if not isinstance(data_quality, dict):
        raise AssertionError(f"{artifact_name} missing data_quality")
    for flag in FORBIDDEN_READY_FLAGS:
        if summary.get(flag) is True:
            raise AssertionError(f"{artifact_name} unexpectedly has {flag}=true")
    if constraints.get("does_not_modify_mapper") is not True:
        raise AssertionError(f"{artifact_name} must not modify mapper")
    if constraints.get("no_trade_signal") is not True:
        raise AssertionError(f"{artifact_name} must not generate trade signal")
    if data_quality.get("no_parameter_optimization") is not True:
        raise AssertionError(f"{artifact_name} must not optimize parameters")


def main() -> None:
    if not DOC_PATH.exists():
        raise AssertionError(f"missing architecture doc: {DOC_PATH}")
    doc = DOC_PATH.read_text(encoding="utf-8")
    _assert_doc_contains(
        doc,
        [
            "Risk Gradient",
            "Protection Score",
            "Two Axis Context",
            "Participation Score",
            "Baseline only",
            "not as an execution policy",
            "Do not continue adding exposure context states",
        ],
    )

    missing_artifacts = [name for name in REQUIRED_ARTIFACTS if not (DATA_DIR / name).exists()]
    if missing_artifacts:
        raise AssertionError(f"missing required artifacts: {missing_artifacts}")

    attribution = _read_json(DATA_DIR / "context_information_attribution.json")
    summary = attribution.get("summary")
    if not isinstance(summary, dict):
        raise AssertionError("context_information_attribution missing summary")
    if summary.get("joined_sample_count") != 115:
        raise AssertionError("V6 architecture must be frozen against the 115-row common sample")
    if set(summary.get("retained_layers") or []) != RETAINED_LAYERS:
        raise AssertionError(f"retained layers mismatch: {summary.get('retained_layers')}")
    if summary.get("risk_leader") != "layer_3_two_axis_context":
        raise AssertionError("Two Axis Context should be the V6 risk leader")
    if summary.get("conclusion") != "risk_layers_have_research_value_opportunity_layer_not_ready":
        raise AssertionError("unexpected V6.6 conclusion")
    _assert_constraints(attribution, "context_information_attribution.json")

    for artifact_name in (
        "protection_score_validation.json",
        "two_axis_context_validation.json",
        "context_information_attribution.json",
    ):
        _assert_constraints(_read_json(DATA_DIR / artifact_name), artifact_name)

    print(
        "v6 architecture consistency ok | "
        f"retained={','.join(summary['retained_layers'])} "
        f"risk_leader={summary['risk_leader']}"
    )


if __name__ == "__main__":
    main()
