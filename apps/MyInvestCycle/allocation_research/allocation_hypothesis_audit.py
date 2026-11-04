from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from config import DATA_DIR
from allocation_research.allocation_hypothesis_schema import build_allocation_hypothesis_schema


DEFAULT_V9_1_PATH = DATA_DIR / "allocation_research_architecture.json"
DEFAULT_OUTPUT_PATH = DATA_DIR / "allocation_research_hypotheses.json"

FORBIDDEN_OUTPUT_KEYS = {
    "asset_selection",
    "backtest_result",
    "broker_order",
    "buy_signal",
    "etf_mapping",
    "exposure_percent",
    "optimization",
    "portfolio_weight",
    "rebalance_instruction",
    "sell_signal",
    "top_n",
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


def _base_hypotheses() -> list[dict[str, object]]:
    required_validation = build_allocation_hypothesis_schema()["required_validation"]
    return [
        {
            "id": "H1",
            "name": "risk_relief_opportunity_readiness",
            "research_question": "Can risk relief and improving opportunity evidence jointly explain better future participation research outcomes?",
            "hypothesis": "When frozen risk evidence weakens and opportunity research evidence improves from watch status toward validated candidates, future research may test a more constructive participation posture.",
            "source_context": ["V6 risk axis", "V7 opportunity readiness", "V8 risk controlled opportunity watch"],
            "required_validation": required_validation,
            "invalidation_conditions": [
                "opportunity evidence remains unvalidated",
                "drawdown audit shows risk relief is unstable",
                "contradiction audit finds repeated false participation context",
            ],
            "status": "unvalidated",
            "forbidden_interpretation": "Do not convert this hypothesis into assets, ETFs, weights, exposure percentages, rebalancing, or trades.",
        },
        {
            "id": "H2",
            "name": "risk_dominant_protection_persistence",
            "research_question": "When the risk axis dominates the opportunity axis, should allocation research first test protection quality instead of opportunity seeking?",
            "hypothesis": "If risk evidence remains materially stronger than opportunity evidence, future research should test whether a protection-first posture explains outcomes better than opportunity pursuit.",
            "source_context": ["V6 risk spread", "V7 insufficient opportunity score readiness", "V8 contradiction attribution"],
            "required_validation": required_validation,
            "invalidation_conditions": [
                "protection posture fails drawdown audit",
                "opportunity evidence becomes independently validated",
                "historical contradiction audit shows persistent opportunity miss",
            ],
            "status": "unvalidated",
            "forbidden_interpretation": "Do not convert this hypothesis into cash level, asset exclusion, ETF mapping, or trade timing.",
        },
        {
            "id": "H3",
            "name": "structural_opportunity_independent_confirmation",
            "research_question": "Can structural opportunity be confirmed independently when broad index evidence is mixed?",
            "hypothesis": "If broad index context is mixed but structure-aware opportunity evidence improves, future research should test whether opportunity confirmation can be separated from broad-market regime labels.",
            "source_context": ["V7 feature attribution", "V8 structural market opportunity not captured", "V9.1 research boundary"],
            "required_validation": required_validation,
            "invalidation_conditions": [
                "structural opportunity evidence cannot pass time-safety audit",
                "contradiction audit shows broad regime dominates structural evidence",
                "out-of-sample test cannot separate structure from broad beta",
            ],
            "status": "unvalidated",
            "forbidden_interpretation": "Do not map this hypothesis to industries, ETFs, themes, weights, or rotation rules.",
        },
        {
            "id": "H4",
            "name": "contradiction_first_promotion_gate",
            "research_question": "Should recurring contradiction types gate promotion from research hypothesis to any later allocation candidate?",
            "hypothesis": "If rapid context switching, bear participation, persistent waiting, or structural opportunity misses recur, future research should require contradiction clearance before promoting any candidate.",
            "source_context": ["V8 scenario audit", "V8 contradiction attribution", "V9.1 readiness flags"],
            "required_validation": required_validation,
            "invalidation_conditions": [
                "contradiction types are not reproducible out of sample",
                "contradiction audit is too sparse for a promotion gate",
                "time-safety audit cannot reproduce source context",
            ],
            "status": "unvalidated",
            "forbidden_interpretation": "Do not treat this gate as a buy, sell, rebalance, ranking, or optimization rule.",
        },
    ]


def validate_allocation_hypothesis_framework(payload: Mapping[str, object]) -> dict[str, object]:
    summary = _mapping(payload.get("summary"))
    schema = _mapping(payload.get("schema"))
    constraints = _mapping(payload.get("constraints"))
    hypotheses = payload.get("hypotheses")
    if not isinstance(hypotheses, list) or not hypotheses:
        raise AssertionError("hypotheses must be a non-empty list")

    for key in (
        "hypothesis_framework_ready",
        "ready_for_asset_selection",
        "ready_for_etf_mapping",
        "ready_for_weight_generation",
        "ready_for_backtest",
        "ready_for_optimization",
        "ready_for_trade",
    ):
        if summary.get(key) is not False:
            raise AssertionError(f"summary.{key} must be false")

    required_constraints = [
        "research_only",
        "hypotheses_only",
        "does_not_select_assets",
        "does_not_map_etf",
        "does_not_generate_portfolio_weight",
        "does_not_generate_exposure_percent",
        "does_not_run_backtest",
        "does_not_optimize_parameters",
        "no_buy_sell_signal",
        "no_rebalance_instruction",
        "no_order_generation",
        "no_broker_connection",
    ]
    for key in required_constraints:
        if constraints.get(key) is not True:
            raise AssertionError(f"constraints.{key} must be true")

    forbidden = schema.get("forbidden_outputs")
    if not isinstance(forbidden, list) or not FORBIDDEN_OUTPUT_KEYS.issubset(set(str(item) for item in forbidden)):
        raise AssertionError("schema.forbidden_outputs missing required forbidden outputs")

    required_validation = set(str(item) for item in schema.get("required_validation", []))
    for hypothesis in hypotheses:
        row = _mapping(hypothesis)
        if row.get("status") != "unvalidated":
            raise AssertionError("all hypotheses must remain unvalidated")
        validations = set(str(item) for item in row.get("required_validation", []))
        if not required_validation.issubset(validations):
            raise AssertionError(f"{row.get('id')} missing required validation items")

    disallowed_payload_keys = FORBIDDEN_OUTPUT_KEYS.intersection(set(_walk_keys(payload)) - {"forbidden_outputs"})
    if disallowed_payload_keys:
        raise AssertionError(f"forbidden output keys found outside schema.forbidden_outputs: {sorted(disallowed_payload_keys)}")

    return {
        "audit_status": "passed",
        "checked_hypothesis_count": len(hypotheses),
        "checked_constraints": required_constraints,
        "checked_forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }


def build_allocation_hypothesis_framework(
    *,
    v9_1_path: str | Path = DEFAULT_V9_1_PATH,
) -> dict[str, object]:
    architecture = _read_json(v9_1_path)
    if not architecture:
        raise RuntimeError("V9.2 input missing; run scripts/audit_allocation_research_architecture.py first.")
    v9_summary = _mapping(architecture.get("summary"))
    v9_metadata = _mapping(architecture.get("metadata"))
    source_evidence = _mapping(architecture.get("source_layer_evidence"))
    schema = build_allocation_hypothesis_schema()
    hypotheses = _base_hypotheses()
    payload: dict[str, object] = {
        "metadata": {
            "engine": "V9.2 Allocation Research Hypothesis Framework",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": v9_metadata.get("as_of"),
            "input_files": {
                "v9_1_allocation_research_architecture": _project_path(v9_1_path),
            },
            "purpose": "Define unvalidated future allocation research hypotheses; no assets, ETFs, weights, backtests, optimization, or trades.",
        },
        "summary": {
            "source_context": v9_summary.get("environment_context"),
            "source_conclusion": v9_summary.get("conclusion"),
            "hypothesis_count": len(hypotheses),
            "unvalidated_count": len(hypotheses),
            "validated_count": 0,
            "hypothesis_framework_ready": False,
            "ready_for_asset_selection": False,
            "ready_for_etf_mapping": False,
            "ready_for_weight_generation": False,
            "ready_for_backtest": False,
            "ready_for_optimization": False,
            "ready_for_trade": False,
            "conclusion": "allocation_hypothesis_framework_defined_unvalidated",
            "key_read": "V9.2 defines research hypotheses only; every hypothesis must pass future out-of-sample, drawdown, contradiction, and time-safety audits before any later candidate work.",
        },
        "schema": schema,
        "source_layer_evidence": {
            "v9_1_summary": v9_summary,
            "v6_v7_v8_evidence": source_evidence,
        },
        "hypotheses": hypotheses,
        "time_safety": {
            "uses_v9_1_artifact_only": True,
            "does_not_recompute_features": True,
            "does_not_recompute_forward_returns": True,
            "future_returns_not_used": True,
        },
        "data_quality": {
            "no_asset_data_loaded": True,
            "no_etf_data_loaded": True,
            "no_backtest": True,
            "no_parameter_scan": True,
            "no_optimization": True,
            "all_hypotheses_unvalidated": True,
        },
        "constraints": {
            "research_only": True,
            "hypotheses_only": True,
            "does_not_select_assets": True,
            "does_not_map_etf": True,
            "does_not_generate_portfolio_weight": True,
            "does_not_generate_exposure_percent": True,
            "does_not_run_backtest": True,
            "does_not_optimize_parameters": True,
            "no_buy_sell_signal": True,
            "no_rebalance_instruction": True,
            "no_order_generation": True,
            "no_broker_connection": True,
        },
    }
    payload["audit"] = validate_allocation_hypothesis_framework(payload)
    return payload


def write_allocation_hypothesis_framework(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
