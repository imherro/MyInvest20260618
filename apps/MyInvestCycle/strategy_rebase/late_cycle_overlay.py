from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import json
from pathlib import Path

from config import DATA_DIR


DEFAULT_OUTPUT_PATH = DATA_DIR / "v15_late_cycle_overlay_manifest.json"


def _feature(
    feature_id: str,
    definition: str,
    source_candidates: list[str],
    availability: str,
    gap: str,
) -> dict[str, object]:
    return {
        "feature_id": feature_id,
        "definition": definition,
        "source_candidates": source_candidates,
        "current_availability": availability,
        "current_gap": gap,
        "required_lineage": [
            "observation_date",
            "release_date",
            "effective_date",
            "captured_at",
            "source_version",
            "source_sha256",
        ],
        "missing_value_policy": "null_and_ineligible; never substitute zero or a current observation",
        "parameter_status": "not_selected_not_optimized",
    }


def validate_v15_late_cycle_overlay_manifest(payload: Mapping[str, object]) -> dict[str, object]:
    constraints = payload.get("constraints") if isinstance(payload.get("constraints"), Mapping) else {}
    features = payload.get("features")
    required = {
        "valuation_percentile",
        "crowding_score",
        "turnover_concentration",
        "breadth_divergence",
        "late_cycle_heat",
        "high_level_drawdown_risk",
    }
    if payload.get("phase") != "V15.5":
        raise AssertionError("phase must be V15.5")
    if not isinstance(features, list) or {item.get("feature_id") for item in features if isinstance(item, Mapping)} != required:
        raise AssertionError("overlay manifest must define the six required features")
    if payload.get("promotion_ready") is not False:
        raise AssertionError("overlay manifest cannot be promotion-ready")
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
        "checked_feature_count": len(features),
        "checked_promotion_ready": False,
    }


def build_v15_late_cycle_overlay_manifest() -> dict[str, object]:
    features = [
        _feature(
            "valuation_percentile",
            "Point-in-time broad-index PE/PB and equity-risk-premium percentile over an expanding historical window.",
            ["Tushare index_dailybasic or equivalent licensed index valuation history", "release-safe bond yield history for ERP"],
            "missing",
            "The current macro history has no PE percentile, PB percentile, or ERP observations.",
        ),
        _feature(
            "crowding_score",
            "Cross-industry crowding derived from breadth, persistence, extension, and concentration using only data available by decision close.",
            ["SW2021 L1 index daily history", "historical_style_context reconstruction logic"],
            "partial_unverified",
            "Values exist, but immutable point-in-time universe/version hashes and capture timestamps do not.",
        ),
        _feature(
            "turnover_concentration",
            "Share of market turnover concentrated in the leading industries, compared with its expanding historical distribution.",
            ["Tushare daily/basic turnover", "SW2021 constituent or industry turnover aggregation"],
            "missing",
            "top_industry_ratio is a strength-score ratio, not turnover concentration, and must not be used as a silent substitute.",
        ),
        _feature(
            "breadth_divergence",
            "Divergence between broad-index trend/price highs and cross-industry or constituent participation breadth.",
            ["CSI300/CSI500 index daily history", "SW2021 L1 or constituent advance/decline breadth"],
            "partial_unverified",
            "Breadth proxies exist, but early dates are incomplete and historical source snapshots are not versioned.",
        ),
        _feature(
            "late_cycle_heat",
            "Derived explanatory composite requiring a point-in-time late-cycle phase plus elevated valuation or crowding evidence.",
            ["strict point-in-time phase series", "valuation_percentile", "crowding_score", "turnover_concentration", "breadth_divergence"],
            "blocked_by_inputs",
            "No formula or threshold may be selected until all components pass point-in-time lineage checks.",
        ),
        _feature(
            "high_level_drawdown_risk",
            "Drawdown occurring from a historically high valuation/crowding state, separated from an early- or mid-cycle pullback.",
            ["broad-index close history", "late_cycle_heat", "expanding-window peak and drawdown series"],
            "blocked_by_inputs",
            "Drawdown is available, but the high-level qualifier is not auditable without the late-cycle inputs.",
        ),
    ]
    payload: dict[str, object] = {
        "metadata": {
            "engine": "V15.5 Late-Cycle Overlay Data Contract",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "purpose": "Define auditable late-cycle risk inputs before any overlay backtest or parameter selection.",
        },
        "phase": "V15.5",
        "manifest_status": "design_ready_data_blocked",
        "promotion_ready": False,
        "summary": {
            "phase": "V15.5",
            "feature_count": len(features),
            "available_feature_count": 0,
            "partial_feature_count": 2,
            "blocked_or_missing_feature_count": 4,
            "backtest_allowed": False,
            "promotion_ready": False,
            "conclusion": "The overlay concept is defined, but historical valuation and strict point-in-time lineage are not ready; no overlay result is claimed.",
        },
        "features": features,
        "intended_research_logic": {
            "reduce_risk_only_when": [
                "strict point-in-time phase indicates late cycle",
                "valuation or crowding/concentration evidence is elevated",
                "a drawdown or breadth divergence confirms deterioration",
            ],
            "do_not_reduce_for": "An early- or mid-bull pullback without high-level valuation/crowding evidence.",
            "output_before_backtest": "explanatory eligibility flags only; no percentage exposure or trade action",
            "thresholds": "unset; must be specified before preregistered out-of-sample testing",
        },
        "readiness_gate": {
            "strict_point_in_time_phase_required": True,
            "publication_time_lineage_required": True,
            "historical_valuation_required": True,
            "immutable_source_hash_required": True,
            "minimum_coverage_policy": "to be preregistered; not selected in V15.5",
            "current_gate_passed": False,
        },
        "constraints": {
            "design_manifest_only": True,
            "does_not_run_backtest": True,
            "does_not_generate_position": True,
            "does_not_generate_trade_signal": True,
            "no_parameter_optimization": True,
            "no_order_generation": True,
            "no_broker_connection": True,
        },
    }
    payload["audit"] = validate_v15_late_cycle_overlay_manifest(payload)
    return payload


def write_v15_late_cycle_overlay_manifest(
    payload: Mapping[str, object], output_path: str | Path = DEFAULT_OUTPUT_PATH
) -> Path:
    validate_v15_late_cycle_overlay_manifest(payload)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target
