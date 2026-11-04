from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import mean
from typing import Iterable, Mapping, Sequence

from config import DATA_DIR


DEFAULT_OUTPUT_PATH = DATA_DIR / "risk_gradient_robustness.json"

FIXED_RISK_THRESHOLDS = {
    "high_risk_min": 65.0,
    "medium_risk_min": 45.0,
    "low_risk_max_exclusive": 45.0,
}

REQUIRED_PERIODS = (
    ("2015-2017", "20150101", "20171231"),
    ("2018", "20180101", "20181231"),
    ("2020", "20200101", "20201231"),
    ("2021", "20210101", "20211231"),
    ("2022", "20220101", "20221231"),
    ("2024-2026", "20240101", "20261231"),
)

RISK_BUCKET_ORDER = ("high_risk", "medium_risk", "low_risk", "unknown")


def _read_json(path: Path) -> object:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _date_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text if len(text) == 8 and text.isdigit() else None


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 6)
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


def _fixed_risk_bucket(score: object) -> str:
    value = _to_float(score)
    if value is None:
        return "unknown"
    if value >= FIXED_RISK_THRESHOLDS["high_risk_min"]:
        return "high_risk"
    if value >= FIXED_RISK_THRESHOLDS["medium_risk_min"]:
        return "medium_risk"
    return "low_risk"


def _rate(rows: Sequence[Mapping[str, object]], outcome: str = "failure") -> float:
    return _share(sum(1 for row in rows if row.get("outcome") == outcome), len(rows))


def _score_stats(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    values = [_to_float(row.get("risk_gradient_score")) for row in rows]
    values = [value for value in values if value is not None]
    if not values:
        return {"available_count": 0, "avg": None, "min": None, "max": None}
    return {
        "available_count": len(values),
        "avg": round(mean(values), 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
    }


def _bucket_metrics(rows: Sequence[Mapping[str, object]]) -> dict[str, dict[str, object]]:
    payload: dict[str, dict[str, object]] = {}
    for bucket in RISK_BUCKET_ORDER:
        group_rows = [row for row in rows if row.get("risk_gradient_bucket") == bucket]
        payload[bucket] = {
            "sample_count": len(group_rows),
            "share_of_period": _share(len(group_rows), len(rows)),
            "failure_rate": _rate(group_rows, "failure"),
            "opportunity_rate": _rate(group_rows, "missed_opportunity"),
            "outcome_distribution": _distribution(row.get("outcome") for row in group_rows),
            "risk_score": _score_stats(group_rows),
        }
    return payload


def _period_status(total_rows: int, high_rows: int, lift: float | None) -> str:
    if total_rows < 6:
        return "insufficient_total_sample"
    if high_rows < 3:
        return "insufficient_high_risk_sample"
    if lift is None:
        return "insufficient_high_risk_sample"
    if lift >= 0.05:
        return "positive"
    if lift <= -0.05:
        return "negative"
    return "flat"


def _period_analysis(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    periods = []
    for name, start, end in REQUIRED_PERIODS:
        period_rows = [
            row
            for row in rows
            if (date := _date_text(row.get("date"))) is not None and start <= date <= end
        ]
        high_rows = [row for row in period_rows if row.get("risk_gradient_bucket") == "high_risk"]
        overall_failure = _rate(period_rows, "failure")
        high_failure = _rate(high_rows, "failure") if high_rows else None
        high_lift = round(high_failure - overall_failure, 6) if high_failure is not None else None
        periods.append(
            {
                "period": name,
                "start_date": start,
                "end_date": end,
                "sample_count": len(period_rows),
                "overall_failure_rate": overall_failure,
                "overall_opportunity_rate": _rate(period_rows, "missed_opportunity"),
                "high_risk_sample_count": len(high_rows),
                "high_risk_failure_rate": high_failure,
                "high_risk_lift": high_lift,
                "status": _period_status(len(period_rows), len(high_rows), high_lift),
                "bucket_metrics": _bucket_metrics(period_rows),
                "high_risk_sample_rows": [
                    {
                        "date": row.get("date"),
                        "outcome": row.get("outcome"),
                        "risk_gradient_score": row.get("risk_gradient_score"),
                        "context_state": row.get("context_state"),
                    }
                    for row in high_rows[:8]
                ],
            }
        )
    return periods


def _threshold_consistency(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    mismatches = []
    for row in rows:
        expected = _fixed_risk_bucket(row.get("risk_gradient_score"))
        actual = str(row.get("risk_gradient_bucket") or "unknown")
        if expected != actual:
            mismatches.append(
                {
                    "date": row.get("date"),
                    "risk_gradient_score": row.get("risk_gradient_score"),
                    "expected_bucket": expected,
                    "actual_bucket": actual,
                }
            )
    return {
        "fixed_thresholds": FIXED_RISK_THRESHOLDS,
        "checked_rows": len(rows),
        "mismatch_count": len(mismatches),
        "mismatch_examples": mismatches[:10],
        "thresholds_were_not_optimized": True,
    }


def _time_safety(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    violations = [
        {"date": row.get("date"), **violation}
        for row in rows
        for violation in ((row.get("data_quality") or {}).get("time_safety_violations") or [])
    ]
    checked = sum(
        1
        for row in rows
        for trace in ((row.get("source_trace") or {}).values() if isinstance(row.get("source_trace"), Mapping) else [])
        if isinstance(trace, Mapping) and trace.get("available") is True
    )
    return {
        "feature_release_or_source_lte_signal_date": not violations,
        "checked_values": checked,
        "violation_count": len(violations),
        "violation_examples": violations[:10],
        "future_labels_used_for_validation_only": True,
        "risk_gradient_score_is_precomputed_v5_10": True,
    }


def _overall_robustness(periods: Sequence[Mapping[str, object]]) -> dict[str, object]:
    evaluated = [period for period in periods if period.get("status") in {"positive", "negative", "flat"}]
    positive = [period for period in evaluated if period.get("status") == "positive"]
    negative = [period for period in evaluated if period.get("status") == "negative"]
    flat = [period for period in evaluated if period.get("status") == "flat"]
    insufficient = [
        period
        for period in periods
        if str(period.get("status") or "").startswith("insufficient")
    ]
    if len(evaluated) < 3:
        consistency = "insufficient_evidence"
    elif len(negative) == 0 and _share(len(positive), len(evaluated)) >= 0.75:
        consistency = "high"
    elif len(negative) <= 1 and _share(len(positive), len(evaluated)) >= 0.5:
        consistency = "medium"
    else:
        consistency = "weak"
    return {
        "period_consistency": consistency,
        "evaluated_period_count": len(evaluated),
        "positive_period_count": len(positive),
        "negative_period_count": len(negative),
        "flat_period_count": len(flat),
        "insufficient_period_count": len(insufficient),
        "positive_periods": [period.get("period") for period in positive],
        "negative_periods": [period.get("period") for period in negative],
        "insufficient_periods": [period.get("period") for period in insufficient],
    }


def _review_items(overall_lift: float, robustness: Mapping[str, object], threshold: Mapping[str, object], time_safety: Mapping[str, object]) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    if int(time_safety.get("violation_count") or 0) > 0:
        items.append({"type": "time_safety_violation", "severity": "high", "evidence": {"violation_count": time_safety.get("violation_count")}})
    if int(threshold.get("mismatch_count") or 0) > 0:
        items.append({"type": "risk_threshold_mismatch", "severity": "high", "evidence": {"mismatch_count": threshold.get("mismatch_count")}})
    if robustness.get("period_consistency") in {"insufficient_evidence", "weak"}:
        items.append(
            {
                "type": "risk_gradient_not_robust_enough",
                "severity": "high",
                "evidence": {
                    "period_consistency": robustness.get("period_consistency"),
                    "positive_period_count": robustness.get("positive_period_count"),
                    "negative_period_count": robustness.get("negative_period_count"),
                    "insufficient_period_count": robustness.get("insufficient_period_count"),
                },
            }
        )
    if overall_lift >= 0.05:
        items.append({"type": "overall_risk_edge_visible", "severity": "low", "evidence": {"overall_lift": overall_lift}})
    items.append(
        {
            "type": "robustness_audit_research_only_do_not_modify_mapper",
            "severity": "high",
            "evidence": {"reason": "V5.11 audits fixed V5.10 risk gradient only; no threshold, mapper, exposure, ETF, or trade change."},
        }
    )
    return items


def _conclusion(overall_lift: float, robustness: Mapping[str, object]) -> str:
    if overall_lift < 0.05:
        return "risk_gradient_edge_not_confirmed"
    if robustness.get("period_consistency") in {"high", "medium"}:
        return "research_value_confirmed_but_still_not_mapper_ready"
    return "overall_edge_visible_but_not_robust"


def build_risk_gradient_robustness(data_dir: str | Path = DATA_DIR) -> dict[str, object]:
    root = Path(data_dir)
    source = _read_json(root / "exposure_gradient_analysis.json")
    if not isinstance(source, Mapping) or not isinstance(source.get("rows"), list):
        raise RuntimeError("exposure_gradient_analysis.json is missing or incomplete.")
    rows = [row for row in source.get("rows") or [] if isinstance(row, Mapping) and _date_text(row.get("date"))]
    high_rows = [row for row in rows if row.get("risk_gradient_bucket") == "high_risk"]
    overall_failure = _rate(rows, "failure")
    high_failure = _rate(high_rows, "failure")
    overall_lift = round(high_failure - overall_failure, 6)
    periods = _period_analysis(rows)
    threshold = _threshold_consistency(rows)
    time_safety = _time_safety(rows)
    robustness = _overall_robustness(periods)
    review_items = _review_items(overall_lift, robustness, threshold, time_safety)
    summary = {
        "source_rows": len(rows),
        "overall_failure_rate": overall_failure,
        "high_risk_failure_rate": high_failure,
        "overall_high_risk_lift": overall_lift,
        "period_consistency": robustness["period_consistency"],
        "ready_for_mapper_change": False,
        "conclusion": _conclusion(overall_lift, robustness),
        "review_items": review_items,
        "review_item_count": len(review_items),
        "key_read": (
            "The V5.10 high-risk bucket has visible overall lift, but period-level robustness is not confirmed; "
            "it should remain a research diagnostic, not a mapper or exposure rule."
        ),
    }
    return {
        "metadata": {
            "engine": "V5.11 Risk Gradient Robustness & Stability Audit",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": (source.get("metadata") or {}).get("as_of"),
            "source_engine": (source.get("metadata") or {}).get("engine"),
            "purpose": "Audit fixed V5.10 risk gradient stability across market periods without changing thresholds or exposure rules.",
        },
        "summary": summary,
        "robustness": robustness,
        "period_analysis": periods,
        "threshold_consistency": threshold,
        "overall_bucket_metrics": _bucket_metrics(rows),
        "time_safety": time_safety,
        "data_quality": {
            "uses_v5_10_risk_gradient_rows": True,
            "risk_gradient_score_reused_not_reweighted": True,
            "fixed_thresholds_reused": True,
            "future_labels_used_for_validation_only": True,
            "no_parameter_optimization": True,
            "periods_are_predefined": True,
        },
        "constraints": {
            "audit_only": True,
            "does_not_modify_gradient_weight": True,
            "does_not_modify_threshold": True,
            "does_not_modify_mapper": True,
            "does_not_modify_policy": True,
            "does_not_add_formal_state": True,
            "does_not_add_exposure_level": True,
            "no_parameter_optimization": True,
            "no_percentage_exposure": True,
            "no_etf_code": True,
            "no_asset_weight": True,
            "no_portfolio_weight": True,
            "no_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
        },
    }


def write_risk_gradient_robustness(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
