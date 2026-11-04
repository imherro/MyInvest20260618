from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from config import DATA_DIR
from decision_research.research_decision_audit import audit_research_decision_context


DEFAULT_TWO_AXIS_PATH = DATA_DIR / "two_axis_context_validation.json"
DEFAULT_PROTECTION_PATH = DATA_DIR / "protection_score_validation.json"
DEFAULT_GRADIENT_PATH = DATA_DIR / "exposure_gradient_analysis.json"
DEFAULT_INFORMATION_PATH = DATA_DIR / "context_information_attribution.json"
DEFAULT_OPPORTUNITY_PATH = DATA_DIR / "opportunity_feature_attribution.json"
DEFAULT_OUTPUT_PATH = DATA_DIR / "research_decision_context.json"


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


def _feature_group_retention(rows: list[Mapping[str, Any]]) -> list[dict[str, object]]:
    grouped: dict[str, Counter[str]] = {}
    for row in rows:
        group = str(row.get("feature_group") or "unknown")
        retention = str(row.get("retention") or "unknown")
        grouped.setdefault(group, Counter())[retention] += 1
    return [
        {
            "feature_group": group,
            "retention_counts": dict(sorted(counter.items())),
            "interpretation": "feature_group_attention_only_not_asset_selection",
        }
        for group, counter in sorted(grouped.items())
    ]


def _decision_context(
    *,
    two_axis_summary: Mapping[str, Any],
    information_summary: Mapping[str, Any],
    gradient_summary: Mapping[str, Any],
    opportunity_summary: Mapping[str, Any],
) -> dict[str, object]:
    risk_visible = two_axis_summary.get("conclusion") == "risk_axis_visible_opportunity_axis_weak"
    opportunity_not_ready = opportunity_summary.get("conclusion") == "feature_attribution_not_ready_for_opportunity_score"
    retained_layers = information_summary.get("retained_layers")
    separation = _mapping(gradient_summary.get("separation_review"))
    if risk_visible and opportunity_not_ready:
        context = "risk_controlled_opportunity_watch"
        posture = "observe_without_selection"
    else:
        context = "research_context_needs_review"
        posture = "review_inputs_before_use"
    return {
        "context": context,
        "research_posture": posture,
        "risk_basis": {
            "risk_context_status": two_axis_summary.get("conclusion"),
            "risk_leader": information_summary.get("risk_leader"),
            "retained_context_layers": retained_layers if isinstance(retained_layers, list) else [],
            "risk_gradient_separation": separation.get("risk_gradient_separation"),
        },
        "opportunity_basis": {
            "opportunity_context_status": opportunity_summary.get("conclusion"),
            "retention_counts": opportunity_summary.get("retention_counts") or {},
            "regime_consistency_counts": opportunity_summary.get("regime_consistency_counts") or {},
            "opportunity_gradient_separation": separation.get("opportunity_gradient_separation"),
        },
        "interpretation": "V6 risk context can frame research attention, while V7 opportunity evidence is not ready for scoring, ranking, allocation, or trading.",
    }


def build_research_decision_context(
    *,
    two_axis_path: str | Path = DEFAULT_TWO_AXIS_PATH,
    protection_path: str | Path = DEFAULT_PROTECTION_PATH,
    gradient_path: str | Path = DEFAULT_GRADIENT_PATH,
    information_path: str | Path = DEFAULT_INFORMATION_PATH,
    opportunity_path: str | Path = DEFAULT_OPPORTUNITY_PATH,
) -> dict[str, object]:
    two_axis = _read_json(two_axis_path)
    protection = _read_json(protection_path)
    gradient = _read_json(gradient_path)
    information = _read_json(information_path)
    opportunity = _read_json(opportunity_path)
    if not all((two_axis, protection, gradient, information, opportunity)):
        raise RuntimeError("V8.1 inputs missing; run V6/V7 frozen artifact builders first.")

    two_axis_summary = _mapping(two_axis.get("summary"))
    protection_summary = _mapping(protection.get("summary"))
    gradient_summary = _mapping(gradient.get("summary"))
    information_summary = _mapping(information.get("summary"))
    opportunity_summary = _mapping(opportunity.get("summary"))
    opportunity_rows = [
        _mapping(row)
        for row in opportunity.get("feature_attribution") or []
        if isinstance(row, Mapping)
    ]
    context = _decision_context(
        two_axis_summary=two_axis_summary,
        information_summary=information_summary,
        gradient_summary=gradient_summary,
        opportunity_summary=opportunity_summary,
    )

    payload: dict[str, object] = {
        "metadata": {
            "engine": "V8.1 Research Decision Integration Architecture",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": _mapping(two_axis.get("metadata")).get("as_of"),
            "input_files": {
                "two_axis_context": _project_path(two_axis_path),
                "protection_validation": _project_path(protection_path),
                "risk_gradient": _project_path(gradient_path),
                "context_information_attribution": _project_path(information_path),
                "opportunity_feature_attribution": _project_path(opportunity_path),
            },
            "purpose": "Integrate frozen V6 risk context and frozen V7 opportunity research as research-only decision context; no assets, ranking, allocation, or trade output.",
        },
        "summary": {
            "decision_context": context["context"],
            "research_posture": context["research_posture"],
            "risk_context_status": two_axis_summary.get("conclusion"),
            "opportunity_context_status": opportunity_summary.get("conclusion"),
            "retained_context_layer_count": information_summary.get("retained_layer_count"),
            "opportunity_research_candidate_count": _mapping(opportunity_summary.get("retention_counts")).get("research_candidate", 0),
            "opportunity_watch_count": _mapping(opportunity_summary.get("retention_counts")).get("watch", 0),
            "ready_for_scoring": False,
            "ready_for_ranking": False,
            "ready_for_allocation": False,
            "ready_for_trade": False,
            "key_read": "V8.1 links V6 risk context and V7 opportunity research for explanation only; it is not a decision rule, ranker, allocation model, or trading signal.",
        },
        "research_context": context,
        "risk_context_evidence": {
            "two_axis_conclusion": two_axis_summary.get("conclusion"),
            "two_axis_risk_spread": two_axis_summary.get("two_axis_risk_spread"),
            "two_axis_opportunity_spread": two_axis_summary.get("two_axis_opportunity_spread"),
            "risk_leader": information_summary.get("risk_leader"),
            "opportunity_leader": information_summary.get("opportunity_leader"),
            "protection_overall_future_high_risk_rate": _mapping(protection_summary.get("overall")).get("future_high_risk_rate"),
        },
        "opportunity_context_evidence": {
            "conclusion": opportunity_summary.get("conclusion"),
            "retention_counts": opportunity_summary.get("retention_counts") or {},
            "regime_consistency_counts": opportunity_summary.get("regime_consistency_counts") or {},
            "feature_group_attention": _feature_group_retention(opportunity_rows),
        },
        "time_safety": {
            "uses_existing_v6_outputs_only": True,
            "uses_existing_v7_outputs_only": True,
            "does_not_recompute_features": True,
            "does_not_recompute_forward_returns": True,
            "does_not_use_future_returns_for_decision": True,
        },
        "data_quality": {
            "uses_frozen_v6_artifacts_only": True,
            "uses_frozen_v7_artifacts_only": True,
            "no_new_feature_search": True,
            "no_scoring": True,
            "no_ranking": True,
            "no_top_n": True,
            "no_allocation": True,
            "no_backtest": True,
            "no_parameter_optimization": True,
        },
        "constraints": {
            "research_only": True,
            "does_not_create_opportunity_score": True,
            "does_not_rank_assets": True,
            "does_not_select_top_assets": True,
            "does_not_generate_position": True,
            "no_percentage_exposure": True,
            "no_etf_code": True,
            "no_asset_weight": True,
            "no_portfolio_weight": True,
            "no_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
            "no_parameter_optimization": True,
        },
    }
    payload["audit"] = audit_research_decision_context(payload)
    return payload


def write_research_decision_context(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
