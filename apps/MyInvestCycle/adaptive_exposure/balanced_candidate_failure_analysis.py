from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from config import DATA_DIR
from adaptive_exposure.balanced_context_audit import classify_candidate_context


DEFAULT_OUTPUT_PATH = DATA_DIR / "balanced_candidate_failure_analysis.json"


def _read_json(path: Path) -> object:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _share(count: int, total: int) -> float:
    return round(count / total, 6) if total else 0.0


def _weighted_rate(rows: Sequence[Mapping[str, object]], key: str) -> float:
    total = sum(int(row.get("usable_rows") or 0) for row in rows)
    if not total:
        return 0.0
    weighted = sum(float(row.get(key) or 0.0) * int(row.get("usable_rows") or 0) for row in rows)
    return round(weighted / total, 6)


def _distribution(values: Iterable[object]) -> dict[str, dict[str, object]]:
    counter = Counter(str(value or "unknown") for value in values)
    total = sum(counter.values())
    return {
        key: {"count": count, "share": _share(count, total)}
        for key, count in sorted(counter.items())
    }


def _pattern_tags(row: Mapping[str, object]) -> list[str]:
    opportunity = str(row.get("opportunity_state") or "UNKNOWN")
    risk = str(row.get("risk_state") or "UNKNOWN")
    phase = str(row.get("market_phase") or "UNKNOWN")
    tags = []
    if opportunity == "EARLY_RECOVERY" and risk == "NORMAL":
        tags.append("early_recovery_normal_false_safety")
    if risk == "CROWDED" and phase in {"UNKNOWN", "LATE_CYCLE"}:
        tags.append("crowding_phase_uncertainty")
    if opportunity == "STRUCTURAL_ROTATION" and risk in {"NORMAL", "CROWDED"}:
        tags.append("structural_rotation_opportunity_suppressed")
    if opportunity == "BULL_EXPANSION" and risk == "CROWDED":
        tags.append("bull_expansion_crowding_conflict")
    if phase == "CONTRACTION":
        tags.append("contraction_phase_inside_balanced")
    return tags or ["mixed_context"]


def _confidence(sample_count: int, context_count: int) -> str:
    if sample_count >= 20 and context_count >= 4:
        return "medium"
    if sample_count >= 10 and context_count >= 2:
        return "low_medium"
    return "low"


def _candidate_contexts(context_rows: Sequence[Mapping[str, object]], candidate: str) -> list[Mapping[str, object]]:
    return [row for row in context_rows if classify_candidate_context(row) == candidate]


def _context_payload(row: Mapping[str, object]) -> dict[str, object]:
    return {
        "context": "+".join(
            [
                str(row.get("opportunity_state") or "UNKNOWN"),
                str(row.get("risk_state") or "UNKNOWN"),
                str(row.get("market_phase") or "UNKNOWN"),
            ]
        ),
        "opportunity_state": row.get("opportunity_state"),
        "risk_state": row.get("risk_state"),
        "market_phase": row.get("market_phase"),
        "sample_count": row.get("usable_rows"),
        "failure_rate": row.get("failure_rate"),
        "future_high_risk_rate": row.get("future_high_risk_rate"),
        "opportunity_rate": row.get("missed_opportunity_rate"),
        "pattern_tags": _pattern_tags(row),
    }


def _candidate_attribution(
    candidate: str,
    rows: Sequence[Mapping[str, object]],
    reason_rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    sample_count = sum(int(row.get("usable_rows") or 0) for row in rows)
    context_count = len(rows)
    tag_counter = Counter(tag for row in rows for tag in _pattern_tags(row))
    if candidate == "BALANCED_RISK":
        primary_patterns = sorted(rows, key=lambda row: (float(row.get("failure_rate") or 0.0), int(row.get("usable_rows") or 0)), reverse=True)
        reasons = [
            row
            for row in reason_rows
            if int(row.get("count") or 0) >= 5 and float(row.get("failure_rate") or 0.0) >= 0.25
        ][:8]
        question = "why_future_risk_increased"
    elif candidate == "BALANCED_OPPORTUNITY":
        primary_patterns = sorted(rows, key=lambda row: (float(row.get("missed_opportunity_rate") or 0.0), int(row.get("usable_rows") or 0)), reverse=True)
        reasons = [
            row
            for row in reason_rows
            if int(row.get("count") or 0) >= 5 and float(row.get("missed_opportunity_rate") or 0.0) >= 0.2
        ][:8]
        question = "why_opportunity_was_capped"
    else:
        primary_patterns = sorted(rows, key=lambda row: int(row.get("usable_rows") or 0), reverse=True)
        reasons = reason_rows[:8]
        question = "why_bucket_remains_mixed"
    return {
        "candidate": candidate,
        "question": question,
        "sample_count": sample_count,
        "context_count": context_count,
        "future_failure_rate": _weighted_rate(rows, "failure_rate"),
        "future_high_risk_rate": _weighted_rate(rows, "future_high_risk_rate"),
        "future_opportunity_rate": _weighted_rate(rows, "missed_opportunity_rate"),
        "confidence": _confidence(sample_count, context_count),
        "dominant_pattern_tags": _distribution(tag_counter.elements()),
        "primary_patterns": [_context_payload(row) for row in primary_patterns[:8]],
        "reason_patterns": reasons,
        "interpretation": _interpret_candidate(candidate, sample_count, tag_counter),
    }


def _interpret_candidate(candidate: str, sample_count: int, tags: Counter[str]) -> str:
    if sample_count < 10:
        return "sample_too_small_for_actionable_attribution"
    if candidate == "BALANCED_RISK":
        if tags.get("early_recovery_normal_false_safety"):
            return "risk_candidate_may_include_false_recovery_safety"
        return "risk_candidate_needs_more_context_features"
    if candidate == "BALANCED_OPPORTUNITY":
        if tags.get("structural_rotation_opportunity_suppressed"):
            return "opportunity_candidate_may_be_structural_rotation_suppressed_by_controls"
        return "opportunity_candidate_needs_more_context_features"
    return "neutral_candidate_still_mixes_risk_and_opportunity"


def _review_items(attribution: Mapping[str, Mapping[str, object]]) -> list[dict[str, object]]:
    items = []
    for candidate, payload in attribution.items():
        if payload.get("confidence") != "medium":
            items.append(
                {
                    "type": "attribution_confidence_not_medium",
                    "severity": "medium",
                    "evidence": {"candidate": candidate, "confidence": payload.get("confidence")},
                }
            )
    items.append(
        {
            "type": "need_numeric_context_enrichment_before_rules",
            "severity": "high",
            "evidence": {
                "missing_fields": ["macro_score", "trend_score", "breadth_score", "liquidity_score", "crowding_numeric"],
            },
        }
    )
    return items


def build_balanced_candidate_failure_analysis(data_dir: str | Path = DATA_DIR) -> dict[str, object]:
    root = Path(data_dir)
    audit = _read_json(root / "balanced_context_audit.json")
    context = _read_json(root / "exposure_context_analysis.json")
    if not isinstance(audit, Mapping) or not isinstance(context, Mapping):
        raise RuntimeError("balanced_context_audit.json or exposure_context_analysis.json is missing.")
    context_rows = [row for row in context.get("context_comparison") or [] if isinstance(row, Mapping)]
    reason_rows = [row for row in context.get("reason_flag_analysis") or [] if isinstance(row, Mapping)]
    attribution = {
        candidate: _candidate_attribution(candidate, _candidate_contexts(context_rows, candidate), reason_rows)
        for candidate in ("BALANCED_RISK", "BALANCED_OPPORTUNITY", "BALANCED_NEUTRAL")
    }
    review_items = _review_items(attribution)
    summary = {
        "source_candidate_quality_status": ((audit.get("summary") or {}).get("candidate_quality") or {}).get("status"),
        "ready_for_rule_change": False,
        "review_items": review_items,
        "review_item_count": len(review_items),
        "key_read": (
            "Candidate attribution is informative but not rule-ready; numeric context enrichment is needed before mapper changes."
        ),
    }
    return {
        "metadata": {
            "engine": "V5.5 Balanced Candidate Failure Attribution",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": (audit.get("metadata") or {}).get("as_of"),
            "source_engine": (audit.get("metadata") or {}).get("engine"),
            "purpose": "Attribute BALANCED_RISK failure and BALANCED_OPPORTUNITY missed opportunity without changing rules.",
        },
        "summary": summary,
        "candidate_attribution": attribution,
        "data_quality": {
            "uses_fixed_v5_4_candidate_labels": True,
            "uses_v5_3_context_rows": True,
            "future_labels_used_for_attribution_only": True,
            "needs_numeric_context_enrichment": True,
        },
        "constraints": {
            "audit_only": True,
            "does_not_modify_mapper": True,
            "does_not_add_formal_state": True,
            "no_parameter_optimization": True,
            "no_percentage_exposure": True,
            "no_etf_code": True,
            "no_asset_weight": True,
            "no_portfolio_weight": True,
            "no_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
            "no_return_optimization": True,
        },
    }


def write_balanced_candidate_failure_analysis(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
