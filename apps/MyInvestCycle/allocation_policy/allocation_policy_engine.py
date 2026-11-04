from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Mapping

from config import DATA_DIR
from allocation_policy.style_constraint_engine import build_style_constraints


DEFAULT_OUTPUT_PATH = DATA_DIR / "allocation_policy_snapshot.json"


def _read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _section(payload: Mapping[str, object], name: str) -> Mapping[str, object]:
    value = payload.get(name)
    return value if isinstance(value, Mapping) else {}


def _first_available(*values: object) -> object | None:
    for value in values:
        if value is not None:
            return value
    return None


def _source_as_of(payload: Mapping[str, object]) -> str | None:
    metadata = _section(payload, "metadata")
    value = _first_available(metadata.get("as_of"), payload.get("as_of"))
    return None if value is None else str(value)


def _resolved_as_of(*payloads: Mapping[str, object]) -> str | None:
    dates = [_source_as_of(payload) for payload in payloads]
    clean = [date for date in dates if date]
    return min(clean) if clean else None


def _style_incremental_edge(payload: Mapping[str, object]) -> dict[str, object]:
    summary = _section(payload, "summary")
    edge = _section(summary, "edge_read")
    return {
        "style_incremental_edge_status": edge.get("style_incremental_edge_status"),
        "tradable_20d_combined_minus_baseline_return": edge.get("tradable_20d_combined_minus_baseline_return"),
        "tradable_60d_combined_minus_baseline_return": edge.get("tradable_60d_combined_minus_baseline_return"),
        "tradable_20d_combined_ic_minus_baseline": edge.get("tradable_20d_combined_ic_minus_baseline"),
        "tradable_60d_combined_ic_minus_baseline": edge.get("tradable_60d_combined_ic_minus_baseline"),
        "tradable_20d_combined_hit_rate": edge.get("tradable_20d_combined_hit_rate"),
        "tradable_60d_combined_hit_rate": edge.get("tradable_60d_combined_hit_rate"),
    }


def extract_allocation_policy_inputs(data_dir: str | Path = DATA_DIR) -> dict[str, object]:
    root = Path(data_dir)
    macro_payload = _read_json(root / "macro_cycle_snapshot.json")
    structural_payload = _read_json(root / "structural_bull_snapshot.json")
    theme_risk_payload = _read_json(root / "theme_risk_snapshot.json")
    style_payload = _read_json(root / "style_allocation_snapshot.json")
    style_incremental_payload = _read_json(root / "style_incremental_analysis.json")

    style_inputs = _section(style_payload, "inputs")
    generated_sources = _section(style_inputs, "generated_sources")
    return {
        "as_of": _resolved_as_of(style_payload, structural_payload, theme_risk_payload) or style_inputs.get("as_of"),
        "macro": _section(style_inputs, "macro") or {
            "state": macro_payload.get("macro_state"),
            "score": macro_payload.get("macro_score"),
            "confidence": macro_payload.get("confidence"),
        },
        "structural": _section(style_inputs, "structural") or {
            "state": structural_payload.get("structural_state"),
            "score": structural_payload.get("score"),
            "confidence": structural_payload.get("confidence"),
        },
        "market_structure": _section(style_inputs, "market_structure") or _section(_section(structural_payload, "evidence"), "market_structure"),
        "industry_opportunity": _section(style_inputs, "industry_opportunity") or _section(_section(structural_payload, "evidence"), "industry_opportunity"),
        "theme_risk": _section(style_inputs, "theme_risk") or {
            "level": theme_risk_payload.get("theme_risk_level"),
            "quality_score": theme_risk_payload.get("quality_score"),
            "crowding_score": theme_risk_payload.get("crowding_score"),
            "warnings": theme_risk_payload.get("warnings") or [],
        },
        "style_preference": _section(style_payload, "preference"),
        "style_incremental": _style_incremental_edge(style_incremental_payload),
        "source_payloads": {
            "macro_cycle": {
                "engine": macro_payload.get("engine") or _section(generated_sources, "macro_cycle").get("engine"),
                "as_of": macro_payload.get("as_of") or _section(generated_sources, "macro_cycle").get("as_of"),
            },
            "structural_bull": {
                "engine": structural_payload.get("engine") or _section(generated_sources, "structural_bull").get("engine"),
                "as_of": structural_payload.get("as_of") or _section(generated_sources, "structural_bull").get("as_of"),
            },
            "theme_risk": {
                "engine": theme_risk_payload.get("engine") or _section(generated_sources, "theme_risk").get("engine"),
                "as_of": theme_risk_payload.get("as_of") or _section(generated_sources, "theme_risk").get("as_of"),
            },
            "style_allocation": {
                "engine": _section(style_payload, "metadata").get("engine"),
                "as_of": _section(style_payload, "metadata").get("as_of"),
            },
            "style_incremental": {
                "engine": _section(style_incremental_payload, "metadata").get("engine"),
                "score_end": _section(style_incremental_payload, "summary").get("score_end"),
                "edge_status": _style_incremental_edge(style_incremental_payload).get("style_incremental_edge_status"),
            },
        },
    }


def build_allocation_policy_snapshot(data_dir: str | Path = DATA_DIR) -> dict[str, object]:
    inputs = extract_allocation_policy_inputs(data_dir)
    constraint_result = build_style_constraints(inputs)
    return {
        "metadata": {
            "engine": "V4.1 Allocation Policy Foundation",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": inputs.get("as_of"),
            "purpose": "Translate macro, structure, theme risk and style preference into qualitative beta risk-budget constraints only.",
            "not_a_portfolio_weight_model": True,
        },
        "source_snapshots": inputs.get("source_payloads"),
        "inputs": {
            "macro": inputs.get("macro"),
            "structural": inputs.get("structural"),
            "market_structure": inputs.get("market_structure"),
            "industry_opportunity": inputs.get("industry_opportunity"),
            "theme_risk": inputs.get("theme_risk"),
            "style_incremental": inputs.get("style_incremental"),
            "style_preference_summary": {
                "dominant_style": _section(inputs, "style_preference").get("dominant_style"),
                "top_styles": _section(inputs, "style_preference").get("top_styles"),
                "confidence": _section(inputs, "style_preference").get("confidence"),
            },
        },
        "policy": {
            "policy_state": constraint_result["policy_state"],
            "policy_summary": constraint_result["policy_summary"],
            "allocation_environment": constraint_result["allocation_environment"],
            "risk_constraints": constraint_result["risk_constraints"],
            "style_permissions": constraint_result["style_permissions"],
            "style_budget_universe": constraint_result["style_budget_universe"],
            "rule_trace": constraint_result["rule_trace"],
            "evidence": constraint_result["evidence"],
        },
        "data_quality": {
            "resolved_as_of": inputs.get("as_of"),
            "uses_generated_snapshots_only": True,
            "no_future_data": True,
            "style_incremental_is_validation_input_only": True,
        },
        "constraints": {
            "policy_foundation_only": True,
            "qualitative_risk_budget_only": True,
            "no_etf_code": True,
            "no_asset_weight": True,
            "no_portfolio_weight": True,
            "no_position_sizing": True,
            "no_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
            "no_backtest": True,
            "style_preference_formula_unchanged": True,
            "opportunity_score_formula_unchanged": True,
            "router_unchanged": True,
            "alpha_model_unchanged": True,
        },
        "notes": [
            "This layer is a rule foundation for future beta allocation research, not an executable allocation.",
            "V3.5.7 weak incremental edge is used as a guardrail: style scores cannot expand budgets by themselves.",
            "Budget levels are qualitative labels, not percentages, ETF weights, or trade instructions.",
        ],
    }


def write_allocation_policy_snapshot(payload: Mapping[str, object], output_path: str | Path = DEFAULT_OUTPUT_PATH) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
