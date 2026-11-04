from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from config import DATA_DIR


DEFAULT_OUTPUT_PATH = DATA_DIR / "balanced_context_audit.json"


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


def classify_candidate_context(row: Mapping[str, object]) -> str:
    count = int(row.get("usable_rows") or row.get("count") or 0)
    failure_rate = float(row.get("failure_rate") or 0.0)
    opportunity_rate = float(row.get("missed_opportunity_rate") or row.get("future_opportunity_rate") or 0.0)
    if count >= 3 and failure_rate >= 0.3:
        return "BALANCED_RISK"
    if count >= 3 and opportunity_rate >= 0.25 and failure_rate <= 0.15:
        return "BALANCED_OPPORTUNITY"
    return "BALANCED_NEUTRAL"


def _quality_label(sample_count: int, primary_rate: float, opposing_rate: float) -> str:
    if sample_count >= 12 and primary_rate >= 0.3 and opposing_rate <= 0.15:
        return "medium"
    if sample_count >= 6 and primary_rate >= 0.25:
        return "low_medium"
    return "low"


def _stability_label(context_count: int, sample_count: int) -> str:
    if context_count >= 3 and sample_count >= 20:
        return "medium"
    if context_count >= 2 and sample_count >= 10:
        return "low_medium"
    return "low"


def _candidate_summary(candidate: str, rows: Sequence[Mapping[str, object]], balanced_total: int) -> dict[str, object]:
    sample_count = sum(int(row.get("usable_rows") or 0) for row in rows)
    failure_rate = _weighted_rate(rows, "failure_rate")
    opportunity_rate = _weighted_rate(rows, "missed_opportunity_rate")
    high_risk_rate = _weighted_rate(rows, "future_high_risk_rate")
    if candidate == "BALANCED_RISK":
        primary_rate = failure_rate
        opposing_rate = opportunity_rate
    elif candidate == "BALANCED_OPPORTUNITY":
        primary_rate = opportunity_rate
        opposing_rate = failure_rate
    else:
        primary_rate = max(failure_rate, opportunity_rate)
        opposing_rate = min(failure_rate, opportunity_rate)
    return {
        "candidate": candidate,
        "research_label_only": True,
        "context_count": len(rows),
        "sample_count": sample_count,
        "share_of_balanced": _share(sample_count, balanced_total),
        "future_failure_rate": failure_rate,
        "future_high_risk_rate": high_risk_rate,
        "future_opportunity_rate": opportunity_rate,
        "stability": _stability_label(len(rows), sample_count),
        "confidence": _quality_label(sample_count, primary_rate, opposing_rate),
        "dominant_contexts": [
            {
                "opportunity_state": row.get("opportunity_state"),
                "risk_state": row.get("risk_state"),
                "market_phase": row.get("market_phase"),
                "sample_count": row.get("usable_rows"),
                "failure_rate": row.get("failure_rate"),
                "opportunity_rate": row.get("missed_opportunity_rate"),
            }
            for row in sorted(rows, key=lambda item: int(item.get("usable_rows") or 0), reverse=True)[:6]
        ],
    }


def _candidate_rows(context_rows: Sequence[Mapping[str, object]]) -> dict[str, list[Mapping[str, object]]]:
    grouped = {"BALANCED_RISK": [], "BALANCED_OPPORTUNITY": [], "BALANCED_NEUTRAL": []}
    for row in context_rows:
        grouped[classify_candidate_context(row)].append(row)
    return grouped


def _source_reason_summary(reason_rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    risk_reasons = [
        row
        for row in reason_rows
        if int(row.get("count") or 0) >= 5 and float(row.get("failure_rate") or 0.0) >= 0.25
    ][:8]
    opportunity_reasons = [
        row
        for row in reason_rows
        if int(row.get("count") or 0) >= 5 and float(row.get("missed_opportunity_rate") or 0.0) >= 0.2
    ][:8]
    return {
        "risk_reasons": risk_reasons,
        "opportunity_reasons": opportunity_reasons,
        "reason_distribution": _distribution(row.get("reason") for row in reason_rows),
    }


def _quality_review(candidates: Mapping[str, Mapping[str, object]]) -> dict[str, object]:
    low_confidence = [
        name
        for name, item in candidates.items()
        if item.get("confidence") in {"low", "low_medium"}
    ]
    missing = [
        name
        for name, item in candidates.items()
        if int(item.get("sample_count") or 0) == 0
    ]
    return {
        "status": "candidate_not_ready_for_mapper_change" if low_confidence or missing else "candidate_quality_review_passed",
        "low_confidence_candidates": low_confidence,
        "missing_candidates": missing,
        "ready_for_formal_rule": False,
        "reason": "Candidates are research labels only; stability and confidence are not high enough for rule changes.",
    }


def _review_items(candidates: Mapping[str, Mapping[str, object]], quality: Mapping[str, object]) -> list[dict[str, object]]:
    items = []
    for name in quality.get("low_confidence_candidates") or []:
        items.append(
            {
                "type": "candidate_low_confidence",
                "severity": "medium",
                "evidence": {"candidate": name, "confidence": candidates.get(name, {}).get("confidence")},
            }
        )
    for name, item in candidates.items():
        if int(item.get("sample_count") or 0) < 10:
            items.append(
                {
                    "type": "candidate_sample_too_small",
                    "severity": "medium",
                    "evidence": {"candidate": name, "sample_count": item.get("sample_count")},
                }
            )
    if quality.get("status") == "candidate_not_ready_for_mapper_change":
        items.append(
            {
                "type": "do_not_modify_mapper_yet",
                "severity": "high",
                "evidence": {"status": quality.get("status")},
            }
        )
    return items


def build_balanced_context_audit(data_dir: str | Path = DATA_DIR) -> dict[str, object]:
    root = Path(data_dir)
    source = _read_json(root / "exposure_context_analysis.json")
    if not isinstance(source, Mapping) or not source.get("context_comparison"):
        raise RuntimeError("exposure_context_analysis.json is missing or incomplete.")
    context_rows = [row for row in source.get("context_comparison") or [] if isinstance(row, Mapping)]
    reason_rows = [row for row in source.get("reason_flag_analysis") or [] if isinstance(row, Mapping)]
    balanced_total = int((source.get("summary") or {}).get("balanced_usable_rows") or 0)
    grouped = _candidate_rows(context_rows)
    candidates = {
        candidate: _candidate_summary(candidate, rows, balanced_total)
        for candidate, rows in grouped.items()
    }
    quality = _quality_review(candidates)
    summary = {
        "balanced_usable_rows": balanced_total,
        "candidate_quality": quality,
        "candidate_count": len(candidates),
        "review_items": _review_items(candidates, quality),
        "key_read": (
            "BALANCED candidate states remain research-only. "
            f"quality_status={quality['status']}; ready_for_formal_rule={quality['ready_for_formal_rule']}."
        ),
    }
    summary["review_item_count"] = len(summary["review_items"])
    return {
        "metadata": {
            "engine": "V5.4 Balanced Context Candidate State Audit",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": (source.get("metadata") or {}).get("as_of"),
            "source_engine": (source.get("metadata") or {}).get("engine"),
            "purpose": "Audit research-only BALANCED sub-state candidates without changing exposure rules.",
        },
        "summary": summary,
        "candidate_states": candidates,
        "source_reason_summary": _source_reason_summary(reason_rows),
        "source_context_count": len(context_rows),
        "data_quality": {
            "uses_fixed_v5_3_context_analysis": True,
            "balanced_context_only": True,
            "research_labels_only": True,
            "future_labels_used_for_candidate_quality_only": True,
        },
        "constraints": {
            "audit_only": True,
            "does_not_modify_v5_1_rules": True,
            "does_not_add_formal_exposure_levels": True,
            "research_labels_only": True,
            "balanced_analysis_only": True,
            "no_percentage_exposure": True,
            "no_etf_code": True,
            "no_asset_weight": True,
            "no_portfolio_weight": True,
            "no_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
            "no_parameter_optimization": True,
            "no_return_optimization": True,
        },
    }


def write_balanced_context_audit(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
