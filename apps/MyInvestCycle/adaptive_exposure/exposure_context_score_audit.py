from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import mean
from typing import Iterable, Mapping, Sequence

from config import DATA_DIR
from adaptive_exposure.exposure_context_score import exposure_context_scores, score_bucket


DEFAULT_OUTPUT_PATH = DATA_DIR / "exposure_context_score_audit.json"
BUCKETS = ("high", "medium", "low", "unknown")


def _read_json(path: Path) -> object:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _date_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text if len(text) == 8 and text.isdigit() else None


def _share(count: int, total: int) -> float:
    return round(count / total, 6) if total else 0.0


def _distribution(values: Iterable[object]) -> dict[str, dict[str, object]]:
    counter = Counter(str(value or "unknown") for value in values)
    total = sum(counter.values())
    return {
        key: {"count": count, "share": _share(count, total)}
        for key, count in sorted(counter.items())
    }


def _flag(row: Mapping[str, object], key: str) -> bool:
    flags = row.get("future_flags")
    return bool(isinstance(flags, Mapping) and flags.get(key))


def _joined_rows(
    exposure_rows: Sequence[Mapping[str, object]],
    gradient_rows: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    exposure_by_date = {str(row.get("date") or ""): row for row in exposure_rows}
    rows = []
    for gradient_row in gradient_rows:
        date = _date_text(gradient_row.get("date"))
        exposure_row = exposure_by_date.get(date or "")
        if not date or not isinstance(exposure_row, Mapping) or not exposure_row.get("future_window_complete"):
            continue
        scores = exposure_context_scores(gradient_row)
        rows.append(
            {
                "date": date,
                "v5_1_exposure_level": exposure_row.get("exposure_level"),
                "future_flags": exposure_row.get("future_flags") or {},
                "future_environment": exposure_row.get("future_environment"),
                "risk_gradient_bucket": gradient_row.get("risk_gradient_bucket"),
                "risk_gradient_score": gradient_row.get("risk_gradient_score"),
                "analysis_context": gradient_row.get("analysis_context") or {},
                "source_trace": gradient_row.get("source_trace") or {},
                "gradient_data_quality": gradient_row.get("data_quality") or {},
                **scores,
                "participation_bucket": score_bucket(scores.get("participation_score")),
                "protection_bucket": score_bucket(scores.get("protection_score")),
            }
        )
    return rows


def _rate(rows: Sequence[Mapping[str, object]], flag_name: str) -> float:
    return _share(sum(1 for row in rows if _flag(row, flag_name)), len(rows))


def _score_stats(rows: Sequence[Mapping[str, object]], field: str) -> dict[str, object]:
    values = [row.get(field) for row in rows if isinstance(row.get(field), (int, float))]
    if not values:
        return {"available_count": 0, "avg": None, "min": None, "max": None}
    return {
        "available_count": len(values),
        "avg": round(mean(float(value) for value in values), 4),
        "min": round(min(float(value) for value in values), 4),
        "max": round(max(float(value) for value in values), 4),
    }


def _bucket_analysis(rows: Sequence[Mapping[str, object]], bucket_field: str) -> dict[str, dict[str, object]]:
    payload = {}
    for bucket in BUCKETS:
        bucket_rows = [row for row in rows if row.get(bucket_field) == bucket]
        payload[bucket] = {
            "sample_count": len(bucket_rows),
            "sample_share": _share(len(bucket_rows), len(rows)),
            "future_high_risk_rate": _rate(bucket_rows, "high_risk_event"),
            "future_opportunity_rate": _rate(bucket_rows, "strong_opportunity_event"),
            "future_drawdown_gt_15_rate": _rate(bucket_rows, "future_drawdown_gt_15"),
        }
    return payload


def _separation(rows: Sequence[Mapping[str, object]], participation: Mapping[str, Mapping[str, object]], protection: Mapping[str, Mapping[str, object]]) -> dict[str, object]:
    overall_risk = _rate(rows, "high_risk_event")
    overall_opportunity = _rate(rows, "strong_opportunity_event")
    high_protection = protection.get("high", {})
    high_participation = participation.get("high", {})
    risk_lift = round(float(high_protection.get("future_high_risk_rate") or 0.0) - overall_risk, 6)
    opportunity_lift = round(float(high_participation.get("future_opportunity_rate") or 0.0) - overall_opportunity, 6)
    return {
        "overall_future_high_risk_rate": overall_risk,
        "overall_future_opportunity_rate": overall_opportunity,
        "high_protection_risk_lift": risk_lift,
        "high_participation_opportunity_lift": opportunity_lift,
        "protection_separation": "visible" if risk_lift >= 0.05 and int(high_protection.get("sample_count") or 0) >= 8 else "weak",
        "participation_separation": "visible" if opportunity_lift >= 0.05 and int(high_participation.get("sample_count") or 0) >= 8 else "weak",
    }


def _time_safety(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    violations = [
        {"date": row.get("date"), **violation}
        for row in rows
        for violation in ((row.get("gradient_data_quality") or {}).get("time_safety_violations") or [])
    ]
    return {
        "feature_release_or_source_lte_signal_date": not violations,
        "violation_count": len(violations),
        "violation_examples": violations[:10],
        "future_labels_used_for_validation_only": True,
    }


def _review_items(separation: Mapping[str, object], time_safety: Mapping[str, object]) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    if int(time_safety.get("violation_count") or 0) > 0:
        items.append({"type": "time_safety_violation", "severity": "high", "evidence": {"violation_count": time_safety.get("violation_count")}})
    if separation.get("protection_separation") == "weak":
        items.append({"type": "protection_score_risk_separation_weak", "severity": "high", "evidence": {"risk_lift": separation.get("high_protection_risk_lift")}})
    if separation.get("participation_separation") == "weak":
        items.append({"type": "participation_score_opportunity_separation_weak", "severity": "high", "evidence": {"opportunity_lift": separation.get("high_participation_opportunity_lift")}})
    items.append({"type": "context_scores_research_only_do_not_modify_exposure", "severity": "high", "evidence": {"reason": "V6.3 creates continuous research scores only; no mapper, exposure, ETF, weight, or trade change."}})
    return items


def build_exposure_context_score_audit(data_dir: str | Path = DATA_DIR) -> dict[str, object]:
    root = Path(data_dir)
    exposure_source = _read_json(root / "exposure_simulation.json")
    gradient_source = _read_json(root / "exposure_gradient_analysis.json")
    if not isinstance(exposure_source, Mapping) or not isinstance(exposure_source.get("historical_replay"), list):
        raise RuntimeError("exposure_simulation.json is missing or incomplete.")
    if not isinstance(gradient_source, Mapping) or not isinstance(gradient_source.get("rows"), list):
        raise RuntimeError("exposure_gradient_analysis.json is missing or incomplete.")
    rows = _joined_rows(
        [row for row in exposure_source.get("historical_replay") or [] if isinstance(row, Mapping)],
        [row for row in gradient_source.get("rows") or [] if isinstance(row, Mapping)],
    )
    participation = _bucket_analysis(rows, "participation_bucket")
    protection = _bucket_analysis(rows, "protection_bucket")
    separation = _separation(rows, participation, protection)
    time_safety = _time_safety(rows)
    review_items = _review_items(separation, time_safety)
    summary = {
        "joined_sample_count": len(rows),
        "score_coverage": {
            "participation_score": _score_stats(rows, "participation_score"),
            "protection_score": _score_stats(rows, "protection_score"),
        },
        "context_label_distribution": _distribution(row.get("context_label") for row in rows),
        "participation_bucket_distribution": _distribution(row.get("participation_bucket") for row in rows),
        "protection_bucket_distribution": _distribution(row.get("protection_bucket") for row in rows),
        "protection_separation": separation["protection_separation"],
        "participation_separation": separation["participation_separation"],
        "ready_for_mapper_change": False,
        "ready_for_exposure_change": False,
        "conclusion": "continuous_context_scores_not_validated",
        "review_items": review_items,
        "review_item_count": len(review_items),
        "key_read": "Continuous context scores are available, but current buckets do not validate enough risk/opportunity separation for policy use.",
    }
    return {
        "metadata": {
            "engine": "V6.3 Continuous Exposure Context Score Audit",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": (exposure_source.get("metadata") or {}).get("as_of"),
            "source_exposure_engine": (exposure_source.get("metadata") or {}).get("engine"),
            "source_gradient_engine": (gradient_source.get("metadata") or {}).get("engine"),
            "purpose": "Audit continuous participation/protection context scores without changing exposure policy.",
        },
        "summary": summary,
        "participation_bucket_analysis": participation,
        "protection_bucket_analysis": protection,
        "separation_review": separation,
        "rows": rows,
        "time_safety": time_safety,
        "data_quality": {
            "uses_fixed_v5_1_exposure_simulation": True,
            "uses_fixed_v5_risk_gradient": True,
            "continuous_scores_are_research_only": True,
            "future_labels_used_for_validation_only": True,
            "no_parameter_optimization": True,
        },
        "constraints": {
            "audit_only": True,
            "does_not_modify_mapper": True,
            "does_not_modify_exposure_level": True,
            "does_not_generate_position": True,
            "no_percentage_exposure": True,
            "no_etf_code": True,
            "no_asset_weight": True,
            "no_portfolio_weight": True,
            "no_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
            "no_return_optimization": True,
            "no_parameter_optimization": True,
        },
    }


def write_exposure_context_score_audit(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
