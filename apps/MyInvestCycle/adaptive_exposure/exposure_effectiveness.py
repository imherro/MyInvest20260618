from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from config import DATA_DIR
from adaptive_exposure.exposure_schema import EXPOSURE_LEVELS, exposure_rank
from allocation_policy.policy_historical_validation import DEFAULT_PERIODS


DEFAULT_OUTPUT_PATH = DATA_DIR / "exposure_effectiveness.json"


def _read_json(path: Path) -> object:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


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


def _contradiction_types(rows: Sequence[Mapping[str, object]]) -> dict[str, dict[str, object]]:
    types = []
    for row in rows:
        for item in row.get("contradictions") or []:
            if isinstance(item, Mapping):
                types.append(item.get("type"))
    return _distribution(types)


def _level_interpretation(level: str, stats: Mapping[str, object], all_opportunity_rate: float) -> str:
    usable = int(stats.get("usable_rows") or 0)
    total_share = float(stats.get("total_share") or 0.0)
    high_risk_rate = float(stats.get("future_high_risk_rate") or 0.0)
    opportunity_rate = float(stats.get("future_opportunity_rate") or 0.0)
    contradiction_rate = float(stats.get("contradiction_rate") or 0.0)
    if usable == 0:
        return "missing_bucket"
    if usable < 10:
        return "sample_too_sparse"
    if level == "BALANCED" and total_share >= 0.65:
        return "too_wide_bucket"
    if high_risk_rate >= 0.25 and exposure_rank(level) >= exposure_rank("BALANCED"):
        return "risk_too_high_for_level"
    if opportunity_rate >= all_opportunity_rate and exposure_rank(level) <= exposure_rank("LOW"):
        return "possible_opportunity_miss_bucket"
    if contradiction_rate >= 0.2:
        return "contradiction_review_needed"
    return "acceptable_for_now"


def _level_stats(rows: Sequence[Mapping[str, object]]) -> dict[str, dict[str, object]]:
    total_rows = len(rows)
    usable_all = [row for row in rows if row.get("future_window_complete")]
    all_opportunity_rate = _share(
        sum(1 for row in usable_all if _flag(row, "strong_opportunity_event")),
        len(usable_all),
    )
    payload: dict[str, dict[str, object]] = {}
    for level in EXPOSURE_LEVELS:
        level_rows = [row for row in rows if row.get("exposure_level") == level]
        usable = [row for row in level_rows if row.get("future_window_complete")]
        contradiction_count = sum(len(row.get("contradictions") or []) for row in usable)
        opportunity_miss_count = sum(
            1
            for row in usable
            for item in row.get("contradictions") or []
            if isinstance(item, Mapping) and item.get("type") == "strong_opportunity_with_low_exposure_level"
        )
        stats = {
            "level": level,
            "total_count": len(level_rows),
            "total_share": _share(len(level_rows), total_rows),
            "usable_rows": len(usable),
            "future_high_risk_count": sum(1 for row in usable if _flag(row, "high_risk_event")),
            "future_high_risk_rate": _share(sum(1 for row in usable if _flag(row, "high_risk_event")), len(usable)),
            "future_drawdown_gt_15_count": sum(1 for row in usable if _flag(row, "future_drawdown_gt_15")),
            "future_drawdown_gt_15_rate": _share(sum(1 for row in usable if _flag(row, "future_drawdown_gt_15")), len(usable)),
            "future_opportunity_count": sum(1 for row in usable if _flag(row, "strong_opportunity_event")),
            "future_opportunity_rate": _share(sum(1 for row in usable if _flag(row, "strong_opportunity_event")), len(usable)),
            "contradiction_count": contradiction_count,
            "contradiction_rate": _share(contradiction_count, len(usable)),
            "opportunity_miss_count": opportunity_miss_count,
            "opportunity_miss_rate": _share(opportunity_miss_count, len(usable)),
            "future_environment_distribution": _distribution(row.get("future_environment") for row in usable),
            "contradiction_type_distribution": _contradiction_types(usable),
        }
        stats["interpretation"] = _level_interpretation(level, stats, all_opportunity_rate)
        payload[level] = stats
    return payload


def _distribution_review(level_stats: Mapping[str, Mapping[str, object]]) -> dict[str, object]:
    rows = [(level, int(stats.get("total_count") or 0), float(stats.get("total_share") or 0.0)) for level, stats in level_stats.items()]
    dominant_level, dominant_count, dominant_share = max(rows, key=lambda item: item[1]) if rows else ("unknown", 0, 0.0)
    missing_levels = [level for level, count, _share_value in rows if count == 0]
    sparse_levels = [level for level, _count, _share_value in rows if 0 < int(level_stats[level].get("usable_rows") or 0) < 10]
    status = "usable_distribution"
    if dominant_level == "BALANCED" and dominant_share >= 0.65:
        status = "balanced_bucket_too_dominant"
    if missing_levels:
        status = "missing_positive_or_defensive_buckets" if status == "usable_distribution" else status
    return {
        "status": status,
        "dominant_level": dominant_level,
        "dominant_count": dominant_count,
        "dominant_share": round(dominant_share, 6),
        "missing_levels": missing_levels,
        "sparse_levels": sparse_levels,
    }


def _ordering_review(level_stats: Mapping[str, Mapping[str, object]]) -> dict[str, object]:
    usable_levels = [
        level
        for level in EXPOSURE_LEVELS
        if int(level_stats.get(level, {}).get("usable_rows") or 0) > 0
    ]
    risk_rates = {level: level_stats[level]["future_high_risk_rate"] for level in usable_levels}
    opportunity_rates = {level: level_stats[level]["future_opportunity_rate"] for level in usable_levels}
    risk_monotonic = all(
        float(risk_rates[usable_levels[i]]) >= float(risk_rates[usable_levels[i + 1]])
        for i in range(len(usable_levels) - 1)
    )
    opportunity_monotonic = all(
        float(opportunity_rates[usable_levels[i]]) <= float(opportunity_rates[usable_levels[i + 1]])
        for i in range(len(usable_levels) - 1)
    )
    issues = []
    for i in range(len(usable_levels) - 1):
        left = usable_levels[i]
        right = usable_levels[i + 1]
        if float(risk_rates[left]) < float(risk_rates[right]):
            issues.append(
                {
                    "type": "risk_rate_rebounds_at_higher_level",
                    "from_level": left,
                    "to_level": right,
                    "from_rate": risk_rates[left],
                    "to_rate": risk_rates[right],
                }
            )
        if float(opportunity_rates[left]) > float(opportunity_rates[right]):
            issues.append(
                {
                    "type": "opportunity_rate_declines_at_higher_level",
                    "from_level": left,
                    "to_level": right,
                    "from_rate": opportunity_rates[left],
                    "to_rate": opportunity_rates[right],
                }
            )
    missing_levels = [level for level in EXPOSURE_LEVELS if int(level_stats.get(level, {}).get("usable_rows") or 0) == 0]
    if missing_levels:
        issues.append({"type": "missing_levels_prevent_full_order_test", "levels": missing_levels})
    return {
        "usable_levels": usable_levels,
        "risk_rates": risk_rates,
        "opportunity_rates": opportunity_rates,
        "risk_monotonic_expected": risk_monotonic,
        "opportunity_monotonic_expected": opportunity_monotonic,
        "issue_count": len(issues),
        "issues": issues,
        "status": "ordered" if risk_monotonic and opportunity_monotonic and not missing_levels else "ordering_review_needed",
    }


def _absence_review(rows: Sequence[Mapping[str, object]], level_stats: Mapping[str, Mapping[str, object]]) -> dict[str, object]:
    policy_modes = Counter(str(row.get("policy_mode") or "unknown") for row in rows)
    combined = Counter(
        (
            str(row.get("opportunity_state") or "unknown"),
            str(row.get("risk_state") or "unknown"),
            str(row.get("market_phase") or "unknown"),
        )
        for row in rows
    )
    missing_positive_levels = [
        level
        for level in ("HIGH", "OFFENSIVE")
        if int(level_stats.get(level, {}).get("total_count") or 0) == 0
    ]
    reasons = []
    if "participate" not in policy_modes:
        reasons.append("source_policy_never_emits_participate_mode")
    if missing_positive_levels:
        reasons.append("positive_exposure_levels_have_no_historical_rows")
    expansion_low_risk = sum(
        1
        for row in rows
        if row.get("opportunity_state") == "BULL_EXPANSION"
        and row.get("risk_state") == "LOW_RISK"
        and row.get("market_phase") == "EXPANSION"
    )
    if expansion_low_risk == 0:
        reasons.append("strict_bull_expansion_low_risk_expansion_combo_absent")
    return {
        "missing_positive_levels": missing_positive_levels,
        "policy_mode_distribution": _distribution(row.get("policy_mode") for row in rows),
        "top_source_contexts": [
            {
                "opportunity_state": key[0],
                "risk_state": key[1],
                "market_phase": key[2],
                "count": count,
                "share": _share(count, len(rows)),
            }
            for key, count in combined.most_common(8)
        ],
        "strict_positive_combo_count": expansion_low_risk,
        "reasons": reasons,
        "interpretation": "positive_exposure_not_observed_in_fixed_v5_1",
    }


def _period_summary(period: Mapping[str, object], rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    start = str(period["start"])
    end = str(period["end"])
    period_rows = [row for row in rows if start <= str(row.get("date") or "") <= end]
    usable = [row for row in period_rows if row.get("future_window_complete")]
    high_risk = sum(1 for row in usable if _flag(row, "high_risk_event"))
    opportunity = sum(1 for row in usable if _flag(row, "strong_opportunity_event"))
    contradictions = sum(len(row.get("contradictions") or []) for row in usable)
    return {
        "period": period.get("id"),
        "label": period.get("label"),
        "window": {"start": start, "end": end},
        "signal_count": len(period_rows),
        "usable_rows": len(usable),
        "exposure_level_distribution": _distribution(row.get("exposure_level") for row in period_rows),
        "future_high_risk_rate": _share(high_risk, len(usable)),
        "future_opportunity_rate": _share(opportunity, len(usable)),
        "contradiction_rate": _share(contradictions, len(usable)),
    }


def _review_items(
    level_stats: Mapping[str, Mapping[str, object]],
    distribution: Mapping[str, object],
    ordering: Mapping[str, object],
) -> list[dict[str, object]]:
    items = []
    if distribution.get("status") == "balanced_bucket_too_dominant":
        items.append(
            {
                "type": "balanced_bucket_too_dominant",
                "severity": "high",
                "evidence": {
                    "dominant_level": distribution.get("dominant_level"),
                    "dominant_share": distribution.get("dominant_share"),
                },
            }
        )
    for level in distribution.get("missing_levels") or []:
        items.append({"type": "missing_exposure_level", "severity": "medium", "evidence": {"level": level}})
    balanced = level_stats.get("BALANCED", {})
    if float(balanced.get("future_high_risk_rate") or 0.0) > float(level_stats.get("LOW", {}).get("future_high_risk_rate") or 0.0):
        items.append(
            {
                "type": "balanced_risk_higher_than_low",
                "severity": "high",
                "evidence": {
                    "balanced_high_risk_rate": balanced.get("future_high_risk_rate"),
                    "low_high_risk_rate": level_stats.get("LOW", {}).get("future_high_risk_rate"),
                },
            }
        )
    if ordering.get("status") != "ordered":
        items.append(
            {
                "type": "exposure_ordering_not_proven",
                "severity": "high",
                "evidence": {"issue_count": ordering.get("issue_count")},
            }
        )
    return items


def _key_read(summary: Mapping[str, object]) -> str:
    distribution = summary.get("distribution_review") or {}
    ordering = summary.get("ordering_review") or {}
    return (
        f"Exposure levels are not yet proven as an ordered signal. Dominant level is "
        f"{distribution.get('dominant_level')} with share {distribution.get('dominant_share')}; "
        f"ordering_status={ordering.get('status')}."
    )


def build_exposure_effectiveness(data_dir: str | Path = DATA_DIR) -> dict[str, object]:
    root = Path(data_dir)
    source = _read_json(root / "exposure_simulation.json")
    if not isinstance(source, Mapping) or not source.get("historical_replay"):
        raise RuntimeError("exposure_simulation.json is missing or incomplete.")
    rows = [row for row in source.get("historical_replay") or [] if isinstance(row, Mapping)]
    usable_rows = [row for row in rows if row.get("future_window_complete")]
    level_stats = _level_stats(rows)
    distribution = _distribution_review(level_stats)
    ordering = _ordering_review(level_stats)
    absence = _absence_review(rows, level_stats)
    summary = {
        "replay_count": len(rows),
        "usable_rows": len(usable_rows),
        "level_effectiveness": level_stats,
        "distribution_review": distribution,
        "ordering_review": ordering,
        "high_offensive_absence": absence,
        "review_items": _review_items(level_stats, distribution, ordering),
    }
    summary["review_item_count"] = len(summary["review_items"])
    summary["key_read"] = _key_read(summary)
    return {
        "metadata": {
            "engine": "V5.2 Exposure Level Effectiveness Audit & Calibration Review",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": (source.get("metadata") or {}).get("as_of"),
            "source_engine": (source.get("metadata") or {}).get("engine"),
            "purpose": "Audit fixed V5.1 qualitative exposure levels for risk/opportunity separation without changing rules.",
        },
        "current": source.get("current") or {},
        "summary": summary,
        "period_validation": [_period_summary(period, rows) for period in DEFAULT_PERIODS],
        "sample_review_rows": [
            {
                "date": row.get("date"),
                "exposure_level": row.get("exposure_level"),
                "policy_mode": row.get("policy_mode"),
                "future_environment": row.get("future_environment"),
                "contradictions": row.get("contradictions"),
            }
            for row in usable_rows
            if row.get("contradictions")
        ][:12],
        "data_quality": {
            "uses_fixed_v5_1_exposure_simulation": True,
            "future_labels_used_for_validation_only": True,
            "qualitative_levels_only": True,
            "does_not_modify_mapper": True,
        },
        "constraints": {
            "audit_only": True,
            "does_not_modify_v5_1_rules": True,
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


def write_exposure_effectiveness(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
