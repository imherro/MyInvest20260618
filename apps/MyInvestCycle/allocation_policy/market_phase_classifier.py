from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from config import DATA_DIR
from allocation_policy.market_phase_state import (
    MARKET_PHASES,
    MarketPhaseResult,
    normalize_market_phase,
    phase_interpretation,
)
from allocation_policy.policy_historical_validation import DEFAULT_PERIODS


DEFAULT_OUTPUT_PATH = DATA_DIR / "market_phase_snapshot.json"


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


def _score(value: object) -> float:
    number = _num(value)
    if 0.0 <= number <= 1.5:
        return round(number * 100.0, 4)
    return round(number, 4)


def _ratio(value: object) -> float:
    number = _num(value)
    if number > 1.5:
        return round(number / 100.0, 6)
    return round(number, 6)


def _round(value: object, digits: int = 6) -> float | None:
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _share(count: int, total: int) -> float:
    return round(count / total, 6) if total else 0.0


def _distribution(values: Iterable[object]) -> dict[str, dict[str, object]]:
    counter = Counter(str(value or "unknown") for value in values)
    total = sum(counter.values())
    return {
        key: {"count": count, "share": _share(count, total)}
        for key, count in sorted(counter.items())
    }


def classify_market_phase(row: Mapping[str, object]) -> MarketPhaseResult:
    metrics = _section(row, "metrics")
    data_quality = _section(row, "data_quality")
    structural_features_available = data_quality.get("structural_features_available")
    macro_state = str(metrics.get("macro_state") or "unknown").upper()
    structural_state = str(metrics.get("structural_state") or "unknown").upper()
    opportunity_state = str(row.get("opportunity_state") or "unknown").upper()
    risk_state = str(row.get("risk_state") or "unknown").upper()
    trend = _score(metrics.get("trend"))
    breadth = _score(metrics.get("breadth"))
    liquidity = _score(metrics.get("liquidity"))
    theme_persistence = _score(metrics.get("theme_persistence"))
    industry_breadth = _ratio(metrics.get("industry_breadth"))
    top_industry_ratio = _ratio(metrics.get("top_industry_ratio"))
    crowding = _score(metrics.get("crowding_score"))
    price_extension = _score(metrics.get("price_extension_proxy") or metrics.get("price_extension"))
    pressure = _score(metrics.get("pressure"))

    evidence: list[str] = []
    if macro_state in {"RECOVERY", "EXPANSION", "BULL"}:
        evidence.append("macro_recovery")
    if macro_state in {"CONTRACTION", "BEAR", "WEAK"} or structural_state in {"WEAK_MARKET", "BEAR_STRUCTURE"}:
        evidence.append("macro_or_structure_weak")
    if trend >= 65:
        evidence.append("trend_strong")
    elif trend <= 35:
        evidence.append("trend_weak")
    if breadth >= 50:
        evidence.append("breadth_expanding")
    elif breadth <= 30:
        evidence.append("breadth_narrow")
    if liquidity >= 55:
        evidence.append("liquidity_supportive")
    elif liquidity <= 35:
        evidence.append("liquidity_weak")
    if theme_persistence >= 65:
        evidence.append("theme_persistence_high")
    if industry_breadth <= 0.25:
        evidence.append("industry_breadth_narrow")
    elif industry_breadth >= 0.45:
        evidence.append("industry_breadth_broad")
    if top_industry_ratio >= 0.25:
        evidence.append("single_theme_concentration")
    if crowding >= 60 or risk_state == "CROWDED":
        evidence.append("crowding_high")
    if price_extension >= 70:
        evidence.append("price_extension_high")
    if pressure >= 60 or risk_state == "HIGH_RISK":
        evidence.append("risk_pressure_high")

    phase = "UNKNOWN"
    if (
        (trend <= 35 or "macro_or_structure_weak" in evidence)
        and (breadth <= 35 or liquidity <= 35 or pressure >= 60 or risk_state == "HIGH_RISK")
    ) or (risk_state == "HIGH_RISK" and trend <= 45):
        phase = "CONTRACTION"
    elif trend >= 65 and (crowding >= 55 or price_extension >= 70) and (
        breadth <= 35 or industry_breadth <= 0.25 or top_industry_ratio >= 0.25
    ):
        phase = "LATE_CYCLE"
    elif trend >= 60 and breadth >= 45 and liquidity >= 45 and industry_breadth >= 0.35 and crowding < 65:
        phase = "EXPANSION"
    elif theme_persistence >= 65 and trend >= 45 and (breadth <= 45 or industry_breadth <= 0.35):
        phase = "ROTATION"
    elif (
        opportunity_state == "EARLY_RECOVERY"
        or "macro_recovery" in evidence
        or structural_state in {"BROAD_BULL", "STRUCTURAL_BULL_ROTATION"}
    ) and trend < 65:
        phase = "EARLY_CYCLE"

    payload_metrics = {
        "macro_state": macro_state,
        "structural_state": structural_state,
        "opportunity_state": opportunity_state,
        "risk_state": risk_state,
        "trend": _round(trend),
        "breadth": _round(breadth),
        "liquidity": _round(liquidity),
        "theme_persistence": _round(theme_persistence),
        "industry_breadth": _round(industry_breadth),
        "top_industry_ratio": _round(top_industry_ratio),
        "crowding_score": _round(crowding),
        "price_extension_proxy": _round(price_extension),
        "pressure": _round(pressure),
    }
    if structural_features_available is False:
        limited_evidence = ["limited_structural_context"]
        if macro_state in {"RECOVERY", "EXPANSION", "BULL"}:
            limited_evidence.append("macro_recovery")
        if risk_state == "HIGH_RISK":
            limited_evidence.append("risk_pressure_high")
        if opportunity_state == "LATE_BULL":
            limited_evidence.append("late_opportunity_state")
            phase = "LATE_CYCLE"
        elif risk_state == "HIGH_RISK" and structural_state in {"WEAK_MARKET", "BEAR_STRUCTURE"}:
            phase = "CONTRACTION"
        elif opportunity_state == "BULL_EXPANSION":
            limited_evidence.append("bull_expansion_state")
            phase = "EXPANSION"
        elif opportunity_state == "STRUCTURAL_ROTATION":
            limited_evidence.append("structural_rotation_state")
            phase = "ROTATION"
        elif opportunity_state == "EARLY_RECOVERY":
            limited_evidence.append("early_recovery_state")
            phase = "EARLY_CYCLE"
        else:
            phase = "UNKNOWN"
        return MarketPhaseResult(
            phase=normalize_market_phase(phase),
            evidence=tuple(dict.fromkeys(limited_evidence)),
            metrics=payload_metrics,
            interpretation=phase_interpretation(phase),
        )

    return MarketPhaseResult(
        phase=normalize_market_phase(phase),
        evidence=tuple(dict.fromkeys(evidence)),
        metrics=payload_metrics,
        interpretation=phase_interpretation(phase),
    )


def phase_to_payload(result: MarketPhaseResult) -> dict[str, object]:
    return {
        "phase": result.phase,
        "evidence": list(result.evidence),
        "metrics": result.metrics,
        "interpretation": result.interpretation,
        "constraints": {
            "phase_classification_only": True,
            "no_allocation": True,
            "no_weight": True,
            "no_trade": True,
        },
    }


def _transition_matrix(rows: Sequence[Mapping[str, object]]) -> dict[str, dict[str, int]]:
    matrix: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    previous = None
    for row in rows:
        phase = str(row.get("phase") or "UNKNOWN")
        if previous is not None:
            matrix[previous][phase] += 1
        previous = phase
    return {from_phase: dict(to_phases) for from_phase, to_phases in sorted(matrix.items())}


def _future_validation(rows: Sequence[Mapping[str, object]], policy_effectiveness: Mapping[str, object]) -> dict[str, object]:
    validation_rows = policy_effectiveness.get("validation_rows") or []
    if not isinstance(validation_rows, Sequence):
        validation_rows = []
    phase_by_date = {str(row.get("date") or ""): row for row in rows}
    joined = []
    for row in validation_rows:
        if not isinstance(row, Mapping) or not row.get("future_window_complete"):
            continue
        phase_row = phase_by_date.get(str(row.get("date") or ""))
        if not phase_row:
            continue
        joined.append({**row, "phase": phase_row.get("phase")})

    grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in joined:
        grouped[str(row.get("phase") or "UNKNOWN")].append(row)

    groups = {}
    risk_rates = []
    for phase in MARKET_PHASES:
        items = grouped.get(phase, [])
        if not items:
            continue
        high_risk_count = sum(1 for item in items if _section(item, "future_flags").get("high_risk_event"))
        opportunity_count = sum(1 for item in items if _section(item, "future_flags").get("strong_opportunity_event"))
        if len(items) >= 3:
            risk_rates.append(_share(high_risk_count, len(items)))
        groups[phase] = {
            "count": len(items),
            "high_risk_event_rate": _share(high_risk_count, len(items)),
            "strong_opportunity_rate": _share(opportunity_count, len(items)),
            "future_environment_distribution": _distribution(item.get("future_environment") for item in items),
        }

    structural_spread = _section(_section(policy_effectiveness, "summary"), "policy_usefulness").get(
        "structural_high_risk_rate_spread"
    )
    phase_spread = round(max(risk_rates) - min(risk_rates), 6) if risk_rates else 0.0
    return {
        "usable_rows": len(joined),
        "groups": groups,
        "phase_high_risk_rate_spread": phase_spread,
        "structural_high_risk_rate_spread": structural_spread,
        "phase_vs_structural_read": (
            "phase_adds_risk_environment_separation"
            if structural_spread is not None and phase_spread > float(structural_spread)
            else "phase_not_yet_better_than_structural"
        ),
        "future_returns_used_only_for_validation_labels": True,
    }


def _period_summary(period: Mapping[str, object], rows: Sequence[Mapping[str, object]], validation: Mapping[str, object]) -> dict[str, object]:
    start = str(period["start"])
    end = str(period["end"])
    period_rows = [row for row in rows if start <= str(row.get("date") or "") <= end]
    return {
        "period": period.get("id"),
        "label": period.get("label"),
        "window": {"start": start, "end": end},
        "signal_count": len(period_rows),
        "phase_distribution": _distribution(row.get("phase") for row in period_rows),
        "dominant_phase": Counter(str(row.get("phase") or "UNKNOWN") for row in period_rows).most_common(1)[0][0]
        if period_rows
        else None,
        "validation_note": _period_validation_note(str(period.get("id")), validation),
    }


def _period_validation_note(period_id: str, validation: Mapping[str, object]) -> str:
    if not validation.get("usable_rows"):
        return "no_future_validation_rows"
    if period_id in {"2018_bear", "2022_bear"}:
        return "review_contraction_or_late_cycle_capture"
    if period_id == "2024_2026_structural":
        return "review_rotation_vs_late_cycle_split"
    return "phase_distribution_observation"


def build_market_phase_snapshot(data_dir: str | Path = DATA_DIR) -> dict[str, object]:
    root = Path(data_dir)
    opportunity = _read_json(root / "opportunity_risk_snapshot.json")
    if not isinstance(opportunity, Mapping) or not opportunity.get("historical_replay"):
        raise RuntimeError("opportunity_risk_snapshot.json is missing or incomplete.")
    policy_effectiveness = _read_json(root / "policy_effectiveness.json")
    if not isinstance(policy_effectiveness, Mapping):
        policy_effectiveness = {}

    current_source = _section(opportunity, "current")
    current = phase_to_payload(classify_market_phase(current_source))
    current["as_of"] = current_source.get("as_of")
    current["source_combined_state"] = current_source.get("combined_state")

    replay_rows = []
    for row in opportunity.get("historical_replay") or []:
        if not isinstance(row, Mapping):
            continue
        result = phase_to_payload(classify_market_phase(row))
        replay_rows.append(
            {
                "date": row.get("date"),
                "phase": result["phase"],
                "evidence": result["evidence"],
                "metrics": result["metrics"],
                "source_opportunity_state": row.get("opportunity_state"),
                "source_risk_state": row.get("risk_state"),
                "source_combined_state": row.get("combined_state"),
                "interpretation": result["interpretation"],
                "data_quality": row.get("data_quality") or {},
            }
        )

    validation = _future_validation(replay_rows, policy_effectiveness)
    return {
        "metadata": {
            "engine": "V4.6 Market Phase Classification Layer",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": _section(opportunity, "metadata").get("as_of"),
            "source_engine": _section(opportunity, "metadata").get("engine"),
            "purpose": "Add a third market phase dimension beside opportunity and risk without producing allocation.",
        },
        "current": current,
        "historical_summary": {
            "replay_count": len(replay_rows),
            "phase_distribution": _distribution(row.get("phase") for row in replay_rows),
            "transition_matrix": _transition_matrix(replay_rows),
            "future_validation": validation,
            "key_read": _key_read(replay_rows, validation),
        },
        "period_validation": [_period_summary(period, replay_rows, validation) for period in DEFAULT_PERIODS],
        "historical_replay": replay_rows,
        "data_quality": {
            "uses_v4_3_opportunity_risk_snapshot": True,
            "uses_v4_5_future_labels_only_for_validation": bool(policy_effectiveness),
            "classification_no_future_returns": True,
            "historical_replay_uses_v4_3_dates": True,
        },
        "constraints": {
            "phase_classification_only": True,
            "no_etf_code": True,
            "no_asset_weight": True,
            "no_portfolio_weight": True,
            "no_position_sizing": True,
            "no_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
            "no_parameter_optimization": True,
            "does_not_modify_v4_4_policy_mapping": True,
        },
    }


def _key_read(rows: Sequence[Mapping[str, object]], validation: Mapping[str, object]) -> str:
    if not rows:
        return "No market phase replay rows are available."
    phases = Counter(str(row.get("phase") or "UNKNOWN") for row in rows)
    dominant, count = phases.most_common(1)[0]
    spread = validation.get("phase_high_risk_rate_spread")
    return (
        f"Replay classified {len(rows)} rows into market phases. Dominant phase is {dominant} "
        f"({count}/{len(rows)}); phase high-risk spread is {spread}."
    )


def write_market_phase_snapshot(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
