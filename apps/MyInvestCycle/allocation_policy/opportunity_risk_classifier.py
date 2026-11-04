from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from config import DATA_DIR
from allocation_policy.allocation_policy_engine import extract_allocation_policy_inputs
from allocation_policy.opportunity_risk_state import OpportunityRiskResult


DEFAULT_OUTPUT_PATH = DATA_DIR / "opportunity_risk_snapshot.json"
DEFAULT_START_DATE = "20150101"
DEFAULT_END_DATE = "20261231"


def _read_json(path: Path) -> object:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _section(payload: Mapping[str, object], name: str) -> Mapping[str, object]:
    value = payload.get(name)
    return value if isinstance(value, Mapping) else {}


def _num(value: object, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _round(value: object, digits: int = 4) -> float:
    return round(_num(value), digits)


def _score_0_100(value: object) -> float:
    number = _num(value)
    if 0.0 <= number <= 1.5:
        return round(number * 100.0, 4)
    return round(number, 4)


def _share(count: int, total: int) -> float:
    return round(count / total, 6) if total else 0.0


def _distribution(values: Iterable[object]) -> dict[str, dict[str, object]]:
    counter = Counter(str(value or "unknown") for value in values)
    total = sum(counter.values())
    return {
        key: {"count": count, "share": _share(count, total)}
        for key, count in sorted(counter.items())
    }


def _context_rows(payload: Mapping[str, object]) -> list[Mapping[str, object]]:
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return []
    return sorted((row for row in rows if isinstance(row, Mapping)), key=lambda row: str(row.get("date") or ""))


def _latest_context(context_rows: Sequence[Mapping[str, object]], date_text: str) -> Mapping[str, object] | None:
    latest = None
    for row in context_rows:
        row_date = str(row.get("date") or "")
        if row_date and row_date <= date_text:
            latest = row
        if row_date > date_text:
            break
    return latest


def classify_opportunity_risk(inputs: Mapping[str, object]) -> OpportunityRiskResult:
    macro = _section(inputs, "macro")
    structural = _section(inputs, "structural")
    market = _section(inputs, "market_structure")
    industry = _section(inputs, "industry_opportunity")
    theme = _section(inputs, "theme_risk")

    macro_state = str(macro.get("state") or "UNKNOWN")
    structural_state = str(structural.get("state") or "UNKNOWN")
    market_state = str(market.get("state") or "UNKNOWN")
    theme_risk_level = str(theme.get("level") or theme.get("theme_risk_level") or "unknown")
    warnings = {str(item) for item in theme.get("warnings") or []}

    trend = _score_0_100(market.get("index_trend") or market.get("trend"))
    breadth = _score_0_100(market.get("breadth"))
    liquidity = _score_0_100(market.get("liquidity"))
    theme_persistence = _score_0_100(industry.get("theme_persistence"))
    industry_breadth = _num(industry.get("industry_breadth"))
    top_industry_ratio = _num(industry.get("top_industry_ratio"))
    crowding_score = _score_0_100(theme.get("crowding_score"))
    raw_price_extension = theme.get("price_extension")
    price_extension = _score_0_100(raw_price_extension)
    price_extension_source = "direct_value" if raw_price_extension is not None else "missing"
    if price_extension == 0 and (
        "price_extension_high" in warnings
        or "top_theme_price_extension_high" in warnings
        or "high_60d_momentum_extension" in warnings
    ):
        price_extension = 75.0
        price_extension_source = "warning_proxy"
    pressure = _score_0_100(theme.get("pressure"))

    evidence: list[str] = []
    if macro_state == "RECOVERY":
        evidence.append("macro_recovery")
    if structural_state == "BROAD_BULL":
        evidence.append("broad_bull_structure")
    if structural_state == "STRUCTURAL_BULL_ROTATION":
        evidence.append("structural_rotation")
    if structural_state in {"WEAK_MARKET", "BEAR_STRUCTURE"}:
        evidence.append("weak_or_bear_structure")
    if market_state == "BULL_DIVERGENCE":
        evidence.append("bull_divergence")
    if trend >= 70:
        evidence.append("trend_strong")
    if breadth >= 45 or industry_breadth >= 0.35:
        evidence.append("breadth_expanding")
    if liquidity >= 55:
        evidence.append("liquidity_supportive")
    if theme_persistence >= 70:
        evidence.append("theme_persistence_high")
    if industry_breadth < 0.2:
        evidence.append("industry_breadth_narrow")
    if top_industry_ratio >= 0.25:
        evidence.append("single_theme_concentration")
    if crowding_score >= 56 or "crowding_score_elevated" in warnings:
        evidence.append("crowding_elevated")
    if price_extension >= 70 or "price_extension_high" in warnings or "top_theme_price_extension_high" in warnings:
        evidence.append("price_extension_high")
    if theme_risk_level in {"medium", "high"}:
        evidence.append(f"theme_risk_{theme_risk_level}")

    opportunity_state = "UNKNOWN"
    if structural_state in {"WEAK_MARKET", "BEAR_STRUCTURE"}:
        opportunity_state = "DEFENSIVE_REPAIR"
    elif structural_state == "BROAD_BULL" and (breadth >= 45 or industry_breadth >= 0.35):
        opportunity_state = "BULL_EXPANSION"
    elif structural_state == "STRUCTURAL_BULL_ROTATION" or theme_persistence >= 70:
        opportunity_state = "STRUCTURAL_ROTATION"
    elif macro_state == "RECOVERY":
        opportunity_state = "EARLY_RECOVERY"

    if opportunity_state in {"BULL_EXPANSION", "STRUCTURAL_ROTATION"} and (
        theme_risk_level == "high"
        or crowding_score >= 72
        or price_extension >= 85
        or ("price_extension_high" in evidence and "industry_breadth_narrow" in evidence)
    ):
        opportunity_state = "LATE_BULL"

    risk_state = "NORMAL"
    if theme_risk_level == "high" or crowding_score >= 72 or (price_extension >= 85 and breadth < 30):
        risk_state = "HIGH_RISK"
    elif (
        theme_risk_level == "medium"
        or crowding_score >= 56
        or price_extension >= 70
        or top_industry_ratio >= 0.25
        or "industry_breadth_narrow" in evidence
    ):
        risk_state = "CROWDED"
    elif (
        theme_risk_level == "low"
        and crowding_score < 45
        and price_extension < 60
        and (breadth >= 45 or industry_breadth >= 0.35)
    ):
        risk_state = "LOW_RISK"

    combined_state = f"{opportunity_state}__{risk_state}"
    return OpportunityRiskResult(
        opportunity_state=opportunity_state,
        risk_state=risk_state,
        combined_state=combined_state,
        evidence=tuple(evidence),
        metrics={
            "macro_state": macro_state,
            "structural_state": structural_state,
            "market_structure_state": market_state,
            "theme_risk_level": theme_risk_level,
            "trend": _round(trend),
            "breadth": _round(breadth),
            "liquidity": _round(liquidity),
            "theme_persistence": _round(theme_persistence),
            "industry_breadth": _round(industry_breadth, 6),
            "top_industry_ratio": _round(top_industry_ratio, 6),
            "crowding_score": _round(crowding_score),
            "price_extension_proxy": _round(price_extension),
            "price_extension_source": price_extension_source,
            "pressure": _round(pressure),
        },
        interpretation=_interpret(opportunity_state, risk_state),
    )


def _interpret(opportunity_state: str, risk_state: str) -> str:
    if opportunity_state in {"BULL_EXPANSION", "STRUCTURAL_ROTATION"} and risk_state in {"LOW_RISK", "NORMAL"}:
        return "Opportunity is favorable and risk is not elevated; later policy layers may study higher beta budgets."
    if opportunity_state in {"BULL_EXPANSION", "STRUCTURAL_ROTATION"} and risk_state in {"CROWDED", "HIGH_RISK"}:
        return "Opportunity exists, but crowding or extension requires risk-budget controls before any allocation layer."
    if opportunity_state == "LATE_BULL":
        return "Opportunity is late-cycle or extended; future policy should prioritize top-risk controls over raw participation."
    if opportunity_state == "DEFENSIVE_REPAIR":
        return "Opportunity is weak or defensive; future policy should avoid expanding offensive beta without recovery evidence."
    if opportunity_state == "EARLY_RECOVERY":
        return "Recovery evidence exists but has not broadened enough; future policy should require confirmation."
    return "Opportunity/risk state is inconclusive and should not drive allocation."


def _historical_inputs(signal: Mapping[str, object], context_row: Mapping[str, object] | None) -> dict[str, object]:
    style_context = _section(context_row or {}, "style_context")
    theme_risk_level = str(signal.get("theme_risk_level") or style_context.get("theme_risk_level") or "unknown")
    return {
        "as_of": signal.get("as_of") or signal.get("date"),
        "macro": {"state": signal.get("macro_state") or "UNKNOWN"},
        "structural": {"state": signal.get("structural_state") or signal.get("allocation_structural_state") or "UNKNOWN"},
        "market_structure": {
            "state": signal.get("market_structure_state") or "UNKNOWN",
            "index_trend": _score_0_100(style_context.get("trend")),
            "breadth": _score_0_100(style_context.get("breadth")),
            "liquidity": _score_0_100(style_context.get("liquidity")),
        },
        "industry_opportunity": {
            "theme_persistence": _score_0_100(style_context.get("theme_persistence")),
            "industry_breadth": _num(style_context.get("industry_breadth")),
            "top_industry_ratio": _num(style_context.get("top_industry_ratio")),
        },
        "theme_risk": {
            "level": theme_risk_level,
            "crowding_score": _score_0_100(style_context.get("crowding_score")),
            "price_extension": _score_0_100(style_context.get("price_extension")),
            "pressure": _score_0_100(style_context.get("pressure")),
            "warnings": [
                f"theme_risk_{theme_risk_level}",
                *("price_extension_high" for _ in [0] if _score_0_100(style_context.get("price_extension")) >= 70),
                *("crowding_score_elevated" for _ in [0] if _score_0_100(style_context.get("crowding_score")) >= 56),
            ],
        },
    }


def _current_inputs(data_dir: str | Path) -> dict[str, object]:
    inputs = extract_allocation_policy_inputs(data_dir)
    theme = dict(_section(inputs, "theme_risk"))
    warnings = list(theme.get("warnings") or [])
    if "top_theme_price_extension_high" in warnings and "price_extension_high" not in warnings:
        warnings.append("price_extension_high")
    theme["warnings"] = warnings
    return {
        "as_of": inputs.get("as_of"),
        "macro": inputs.get("macro"),
        "structural": inputs.get("structural"),
        "market_structure": inputs.get("market_structure"),
        "industry_opportunity": inputs.get("industry_opportunity"),
        "theme_risk": theme,
    }


def _replay_history(data_dir: str | Path, start_date: str, end_date: str) -> list[dict[str, object]]:
    root = Path(data_dir)
    v2_payload = _read_json(root / "v2_full_cycle_backtest.json")
    context_payload = _read_json(root / "historical_style_context.json")
    if not isinstance(v2_payload, Mapping):
        return []
    signals = _section(v2_payload, "signals").get("v2_structural_refined") or []
    if not isinstance(signals, list):
        return []
    context_rows = _context_rows(context_payload if isinstance(context_payload, Mapping) else {})
    rows = []
    for signal in signals:
        if not isinstance(signal, Mapping):
            continue
        signal_date = str(signal.get("date") or signal.get("as_of") or "")
        if not signal_date or signal_date < start_date or signal_date > end_date:
            continue
        context_row = _latest_context(context_rows, signal_date)
        inputs = _historical_inputs(signal, context_row)
        result = classify_opportunity_risk(inputs)
        rows.append(
            {
                "date": signal_date,
                "opportunity_state": result.opportunity_state,
                "risk_state": result.risk_state,
                "combined_state": result.combined_state,
                "evidence": list(result.evidence),
                "metrics": result.metrics,
                "interpretation": result.interpretation,
                "data_quality": {
                    "context_date": (context_row or {}).get("date"),
                    "context_future_safe": (context_row or {}).get("future_safe"),
                    "structural_features_available": _section(context_row or {}, "data_quality").get(
                        "structural_features_available"
                    ),
                    "missing_fields": _section(context_row or {}, "data_quality").get("missing_fields") or [],
                },
            }
        )
    return rows


def _state_matrix(rows: Sequence[Mapping[str, object]]) -> dict[str, dict[str, int]]:
    matrix: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in rows:
        matrix[str(row.get("opportunity_state") or "UNKNOWN")][str(row.get("risk_state") or "UNKNOWN")] += 1
    return {left: dict(right) for left, right in sorted(matrix.items())}


def _summary(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    complete_context = sum(1 for row in rows if _section(row, "data_quality").get("structural_features_available") is True)
    return {
        "replay_count": len(rows),
        "opportunity_state_distribution": _distribution(row.get("opportunity_state") for row in rows),
        "risk_state_distribution": _distribution(row.get("risk_state") for row in rows),
        "combined_state_distribution": _distribution(row.get("combined_state") for row in rows),
        "opportunity_risk_matrix": _state_matrix(rows),
        "complete_structural_context_count": complete_context,
        "complete_structural_context_share": _share(complete_context, len(rows)),
        "key_read": _key_read(rows),
    }


def _key_read(rows: Sequence[Mapping[str, object]]) -> str:
    if not rows:
        return "No historical opportunity/risk replay rows are available."
    combined = Counter(str(row.get("combined_state") or "UNKNOWN") for row in rows)
    dominant, count = combined.most_common(1)[0]
    crowded = sum(1 for row in rows if str(row.get("risk_state")) in {"CROWDED", "HIGH_RISK"})
    return (
        f"Replay generated {len(rows)} opportunity/risk states. Dominant combined state is {dominant} "
        f"({count}/{len(rows)}), while crowded/high-risk observations account for {crowded}/{len(rows)}."
    )


def build_opportunity_risk_snapshot(
    data_dir: str | Path = DATA_DIR,
    start_date: str = DEFAULT_START_DATE,
    end_date: str = DEFAULT_END_DATE,
) -> dict[str, object]:
    current_inputs = _current_inputs(data_dir)
    current_result = classify_opportunity_risk(current_inputs)
    replay_rows = _replay_history(data_dir, start_date, end_date)
    return {
        "metadata": {
            "engine": "V4.3 Market Opportunity vs Risk State Separation Engine",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": current_inputs.get("as_of"),
            "window": {"start": start_date, "end": end_date},
            "purpose": "Separate opportunity state from risk state before any adaptive allocation research.",
            "state_separation_only": True,
        },
        "current": {
            "as_of": current_inputs.get("as_of"),
            "opportunity_state": current_result.opportunity_state,
            "risk_state": current_result.risk_state,
            "combined_state": current_result.combined_state,
            "evidence": list(current_result.evidence),
            "metrics": current_result.metrics,
            "interpretation": current_result.interpretation,
        },
        "historical_summary": _summary(replay_rows),
        "historical_replay": replay_rows,
        "data_quality": {
            "uses_existing_snapshots": True,
            "historical_context_same_day_or_prior_only": True,
            "no_future_returns": True,
            "no_policy_rule_change": True,
        },
        "constraints": {
            "state_separation_only": True,
            "no_allocation": True,
            "no_etf_code": True,
            "no_asset_weight": True,
            "no_portfolio_weight": True,
            "no_position_sizing": True,
            "no_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
            "does_not_modify_v4_1_policy": True,
            "not_a_backtest_optimization": True,
        },
    }


def write_opportunity_risk_snapshot(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
