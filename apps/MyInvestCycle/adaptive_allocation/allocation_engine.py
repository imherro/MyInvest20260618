from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Mapping

from config import DATA_DIR
from core.data_loader import normalize_trade_date
from adaptive_allocation.allocation_explainer import explain_allocation_intent
from adaptive_allocation.exposure_policy import determine_exposure_policy
from adaptive_allocation.style_allocator import determine_style_preference
from structural_bull.structural_bull_engine import build_structural_bull_snapshot
from theme_risk.opportunity_quality_engine import build_theme_risk_snapshot


DEFAULT_OUTPUT_PATH = DATA_DIR / "allocation_intent_snapshot.json"


def _section(payload: Mapping[str, object], name: str) -> Mapping[str, object]:
    value = payload.get(name)
    return value if isinstance(value, Mapping) else {}


def _theme_risk_evidence(theme_risk_payload: Mapping[str, object]) -> dict[str, object]:
    return {
        "risk_level": theme_risk_payload.get("theme_risk_level"),
        "quality_score": theme_risk_payload.get("quality_score"),
        "crowding_score": theme_risk_payload.get("crowding_score"),
        "warnings": theme_risk_payload.get("warnings") or [],
        "as_of": theme_risk_payload.get("as_of"),
    }


def _resolved_as_of(structural_payload: Mapping[str, object], theme_risk_payload: Mapping[str, object], requested_as_of: str) -> str:
    dates = [
        str(value)
        for value in (structural_payload.get("as_of"), theme_risk_payload.get("as_of"))
        if value is not None and str(value) <= requested_as_of
    ]
    return min(dates) if dates else requested_as_of


def build_allocation_intent_snapshot(
    as_of: str | int,
    *,
    structural_payload: Mapping[str, object] | None = None,
    theme_risk_payload: Mapping[str, object] | None = None,
    cache_only: bool = True,
) -> dict[str, object]:
    requested_as_of = normalize_trade_date(as_of)
    structural = structural_payload or build_structural_bull_snapshot(requested_as_of, cache_only=cache_only)
    theme_risk = theme_risk_payload or build_theme_risk_snapshot(requested_as_of, cache_only=cache_only)
    exposure = determine_exposure_policy(structural, theme_risk)
    style_preference = determine_style_preference(structural, theme_risk)
    structural_evidence = _section(structural, "evidence")
    evidence = {
        "macro": structural_evidence.get("macro"),
        "market_structure": structural_evidence.get("market_structure"),
        "industry_opportunity": structural_evidence.get("industry_opportunity"),
        "theme_risk": _theme_risk_evidence(theme_risk),
    }
    intent = {
        "equity_exposure_range": exposure["equity_exposure_range"],
        "risk_budget": exposure["risk_budget"],
        "style_preference": style_preference,
        "allocation_philosophy": "risk-budget intent only; no ETF, no order, no execution.",
    }
    payload: dict[str, object] = {
        "engine": "V2.4.1 Adaptive Allocation Intent Engine",
        "requested_as_of": requested_as_of,
        "as_of": _resolved_as_of(structural, theme_risk, requested_as_of),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "structural_state": structural.get("structural_state"),
        "allocation_structural_state": exposure["risk_adjustments"].get("allocation_structural_state"),
        "allocation_intent": intent,
        "risk_adjustments": exposure["risk_adjustments"],
        "evidence": evidence,
        "source_snapshots": {
            "structural_bull_engine": structural.get("engine"),
            "theme_risk_engine": theme_risk.get("engine"),
        },
        "data_quality": {
            "structural_as_of": structural.get("as_of"),
            "theme_risk_as_of": theme_risk.get("as_of"),
            "no_future_data": _resolved_as_of(structural, theme_risk, requested_as_of) <= requested_as_of,
        },
        "constraints": {
            "intent_only": True,
            "no_single_stock": True,
            "no_etf_code": True,
            "no_buy_sell": True,
            "no_order": True,
            "no_broker_connection": True,
            "no_specific_execution_position": True,
        },
    }
    payload["explanation"] = explain_allocation_intent(payload)
    return payload


def write_allocation_intent_snapshot(payload: Mapping[str, object], output_path: str | Path = DEFAULT_OUTPUT_PATH) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
