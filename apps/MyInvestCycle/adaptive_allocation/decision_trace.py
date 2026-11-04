from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Mapping

from config import DATA_DIR
from core.data_loader import normalize_trade_date
from adaptive_allocation.allocation_audit import audit_allocation_trace
from adaptive_allocation.allocation_engine import build_allocation_intent_snapshot


DEFAULT_OUTPUT_PATH = DATA_DIR / "allocation_trace.json"


def _section(payload: Mapping[str, object], name: str) -> Mapping[str, object]:
    value = payload.get(name)
    return value if isinstance(value, Mapping) else {}


def _impact_from_macro(state: str, score: float) -> str:
    if state in {"BULL", "RECOVERY"} and score >= 60:
        return "supportive"
    if state == "BEAR":
        return "defensive"
    return "neutral"


def _impact_from_structure(state: str, breadth: float) -> str:
    if state == "BULL_BROADENING":
        return "positive"
    if state == "BULL_DIVERGENCE" and breadth < 30:
        return "neutral_positive_but_narrow"
    if state in {"BEAR_BREAKDOWN", "BEAR_STRUCTURE"}:
        return "negative"
    return "neutral"


def _impact_from_industry(theme_persistence: float, industry_strength: float) -> str:
    if theme_persistence >= 75 and industry_strength >= 52:
        return "positive_structural_opportunity"
    if industry_strength < 45:
        return "weak"
    return "neutral"


def _impact_from_theme_risk(level: str) -> str:
    if level == "high":
        return "reduce_risk_strongly"
    if level == "medium":
        return "reduce_risk"
    return "no_discount"


def _base_budget_from_structural(state: str) -> str:
    return {
        "BROAD_BULL": "high",
        "STRUCTURAL_BULL_HEALTHY": "high",
        "STRUCTURAL_BULL_OVERHEATED": "medium",
        "STRUCTURAL_BULL_BALANCED": "medium_high",
        "STRUCTURAL_BULL_ROTATION": "medium_high",
        "BEAR_REBOUND": "low",
        "BEAR_STRUCTURE": "defensive",
        "WEAK_MARKET": "defensive",
    }.get(state, "medium")


def _theme_delta(level: str) -> int:
    if level == "high":
        return -2
    if level == "medium":
        return -1
    return 0


def _conflicts(macro_state: str, structure_state: str, breadth: float, theme_risk_level: str) -> list[str]:
    conflicts: list[str] = []
    if macro_state in {"BULL", "RECOVERY"} and theme_risk_level == "high":
        conflicts.append("bull_cycle_but_theme_overheated")
    if structure_state == "BULL_DIVERGENCE" and breadth < 30:
        conflicts.append("index_trend_strong_but_breadth_weak")
    if macro_state == "BEAR" and structure_state in {"STRUCTURAL_BULL_ROTATION", "BULL_BROADENING"}:
        conflicts.append("macro_bear_but_market_structure_positive")
    return conflicts


def build_decision_trace(allocation_payload: Mapping[str, object]) -> dict[str, object]:
    evidence = _section(allocation_payload, "evidence")
    macro = _section(evidence, "macro")
    structure = _section(evidence, "market_structure")
    industry = _section(evidence, "industry_opportunity")
    theme_risk = _section(evidence, "theme_risk")
    intent = _section(allocation_payload, "allocation_intent")
    risk_adjustments = _section(allocation_payload, "risk_adjustments")
    structural_policy = _section(risk_adjustments, "structural_bull_policy")
    structural_state = str(allocation_payload.get("structural_state", "RANGE"))
    allocation_structural_state = str(
        allocation_payload.get("allocation_structural_state")
        or risk_adjustments.get("allocation_structural_state")
        or structural_state
    )
    macro_state = str(macro.get("state", "RANGE"))
    macro_score = float(macro.get("score") or 0.0)
    structure_state = str(structure.get("state", "RANGE"))
    breadth = float(structure.get("breadth") or 0.0)
    theme_persistence = float(industry.get("theme_persistence") or 0.0)
    industry_strength = float(industry.get("industry_strength") or 0.0)
    theme_risk_level = str(theme_risk.get("risk_level", "medium"))
    refined_applies = bool(structural_policy.get("applies"))
    base_budget = _base_budget_from_structural(allocation_structural_state if refined_applies else structural_state)
    delta = int(risk_adjustments.get("theme_risk_delta", _theme_delta(theme_risk_level)) or 0)
    adjustment_path = [
        {
            "step": "base_from_structural_state",
            "value": _base_budget_from_structural(structural_state),
            "reason": f"{structural_state} sets the original base risk budget.",
        }
    ]
    if refined_applies:
        adjustment_path.append(
            {
                "step": "structural_bull_refinement",
                "value": base_budget,
                "allocation_structural_state": allocation_structural_state,
                "reason": "、".join(str(item) for item in structural_policy.get("reasons") or []),
            }
        )
    adjustment_path.append(
        {
            "step": "theme_risk_adjustment",
            "delta": delta,
            "result": intent.get("risk_budget"),
            "reason": "Structural bull refinement already includes theme risk."
            if refined_applies
            else f"theme_risk_level={theme_risk_level} adjusts the base budget.",
        }
    )
    return {
        "macro": {
            "state": macro_state,
            "score": macro.get("score"),
            "impact": _impact_from_macro(macro_state, macro_score),
            "reason": "宏观状态决定风险预算是否有顺风或逆风。",
        },
        "structure": {
            "state": structure_state,
            "breadth": structure.get("breadth"),
            "impact": _impact_from_structure(structure_state, breadth),
            "reason": "市场结构决定权益参与是全面扩散还是结构分化。",
        },
        "industry": {
            "industry_strength": industry.get("industry_strength"),
            "theme_persistence": industry.get("theme_persistence"),
            "impact": _impact_from_industry(theme_persistence, industry_strength),
            "reason": "行业机会决定是否存在持续主线。",
        },
        "theme_risk": {
            "level": theme_risk_level,
            "quality_score": theme_risk.get("quality_score"),
            "crowding_score": theme_risk.get("crowding_score"),
            "impact": _impact_from_theme_risk(theme_risk_level),
            "reason": "主题风险决定是否降低风险预算。",
        },
        "structural_bull_policy": structural_policy if refined_applies else None,
        "adjustment_path": adjustment_path,
        "conflicts": _conflicts(macro_state, structure_state, breadth, theme_risk_level),
        "final_intent": {
            "risk_budget": intent.get("risk_budget"),
            "equity_exposure_range": intent.get("equity_exposure_range"),
            "style_preference": intent.get("style_preference"),
        },
    }


def build_allocation_trace_snapshot(
    as_of: str | int,
    *,
    allocation_payload: Mapping[str, object] | None = None,
    cache_only: bool = True,
) -> dict[str, object]:
    requested_as_of = normalize_trade_date(as_of)
    allocation = allocation_payload or build_allocation_intent_snapshot(requested_as_of, cache_only=cache_only)
    trace = build_decision_trace(allocation)
    audit = audit_allocation_trace(allocation, trace)
    return {
        "engine": "V2.4.2 Allocation Decision Trace & Explainability Layer",
        "requested_as_of": requested_as_of,
        "as_of": allocation.get("as_of"),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "decision_trace": trace,
        "allocation_intent": allocation.get("allocation_intent"),
        "audit": audit,
        "data_quality": {
            "allocation_as_of": allocation.get("as_of"),
            "no_future_data": bool((allocation.get("data_quality") or {}).get("no_future_data"))
            if isinstance(allocation.get("data_quality"), Mapping)
            else False,
        },
        "constraints": {
            "does_not_change_allocation_intent": True,
            "no_etf": True,
            "no_single_stock": True,
            "no_trade": True,
            "no_order": True,
            "no_backtest": True,
        },
    }


def write_allocation_trace_snapshot(payload: Mapping[str, object], output_path: str | Path = DEFAULT_OUTPUT_PATH) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
