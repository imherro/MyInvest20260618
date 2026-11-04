from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = ROOT / "docs" / "opportunity_research_v7_architecture.md"
DATA_DIR = ROOT / "data"


ARTIFACTS = {
    "V7.1": DATA_DIR / "opportunity_research_foundation.json",
    "V7.2": DATA_DIR / "opportunity_context_features.json",
    "V7.3": DATA_DIR / "opportunity_feature_validation.json",
    "V7.4": DATA_DIR / "opportunity_feature_attribution.json",
}


REQUIRED_DOC_TOKENS = [
    "V7.1 Asset Research Foundation",
    "V7.2 Context Features",
    "V7.3 Feature Validation",
    "V7.4 Feature Attribution",
    "Opportunity Score: rejected",
    "Ranking: rejected",
    "Top N: rejected",
    "Allocation: rejected",
    "ETF weight: rejected",
    "Trading: rejected",
    "feature_attribution_not_ready_for_opportunity_score",
    "no Opportunity Score",
    "no rank",
    "no allocation",
    "no trading",
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
        "no_trade_signal",
        "no_broker_connection",
    )
    for key in required:
        if constraints.get(key) is not True:
            raise AssertionError(f"{layer} constraint {key} must be true")
    if layer in {"V7.2", "V7.3", "V7.4"} and constraints.get("does_not_select_top_assets") is not True:
        raise AssertionError(f"{layer} constraint does_not_select_top_assets must be true")


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

    v73 = summaries["V7.3"]
    if v73.get("feature_count") != 14:
        raise AssertionError("V7.3 feature_count must stay 14")
    if v73.get("horizons") != [5, 20, 60]:
        raise AssertionError("V7.3 horizons must stay [5, 20, 60]")
    if v73.get("result_count") != 42:
        raise AssertionError("V7.3 result_count must stay 42")

    v74 = summaries["V7.4"]
    if v74.get("source_result_count") != 42 or v74.get("attribution_count") != 42:
        raise AssertionError("V7.4 source_result_count and attribution_count must stay 42")
    if v74.get("conclusion") != "feature_attribution_not_ready_for_opportunity_score":
        raise AssertionError("V7.4 conclusion must reject opportunity score readiness")

    retention = v74.get("retention_counts")
    if not isinstance(retention, dict):
        raise AssertionError("V7.4 missing retention_counts")
    expected_retention = {
        "research_candidate": 1,
        "watch": 17,
        "reject_for_now": 18,
        "insufficient": 6,
    }
    for key, expected in expected_retention.items():
        if retention.get(key) != expected:
            raise AssertionError(f"V7.4 retention_counts.{key} expected {expected}, got {retention.get(key)}")

    v74_constraints = constraints["V7.4"]
    if v74_constraints.get("does_not_create_feature_weight") is not True:
        raise AssertionError("V7.4 must not create feature weights")

    print(
        "v7 architecture consistency ok | "
        f"conclusion={v74.get('conclusion')} | "
        f"attribution={v74.get('attribution_count')} | "
        f"retention={retention}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
