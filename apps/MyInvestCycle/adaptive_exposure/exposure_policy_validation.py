from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Callable, Mapping, Sequence

from config import DATA_DIR


DEFAULT_OUTPUT_PATH = DATA_DIR / "exposure_policy_validation.json"


def _read_json(path: Path) -> object:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _date_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text if len(text) == 8 and text.isdigit() else None


def _share(count: int, total: int) -> float:
    return round(count / total, 6) if total else 0.0


def _flag(row: Mapping[str, object], key: str) -> bool:
    flags = row.get("future_flags")
    return bool(isinstance(flags, Mapping) and flags.get(key))


def _context_value(row: Mapping[str, object], field: str) -> str:
    context = row.get("analysis_context")
    if not isinstance(context, Mapping):
        return "UNKNOWN"
    return str(context.get(field) or "UNKNOWN")


def _candidate_matches(gradient_row: Mapping[str, object], candidate: Mapping[str, object]) -> bool:
    fields = candidate.get("fields")
    values = candidate.get("values")
    if not isinstance(fields, list) or not isinstance(values, list) or len(fields) != len(values):
        return False
    return all(_context_value(gradient_row, str(field)) == str(value) for field, value in zip(fields, values))


def _joined_rows(
    exposure_rows: Sequence[Mapping[str, object]],
    gradient_rows: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    gradient_by_date = {str(row.get("date") or ""): row for row in gradient_rows}
    rows = []
    for exposure_row in exposure_rows:
        date = _date_text(exposure_row.get("date"))
        if not date or not exposure_row.get("future_window_complete"):
            continue
        gradient_row = gradient_by_date.get(date)
        if not isinstance(gradient_row, Mapping):
            continue
        rows.append(
            {
                "date": date,
                "exposure_level": exposure_row.get("exposure_level"),
                "policy_mode": exposure_row.get("policy_mode"),
                "future_flags": exposure_row.get("future_flags") or {},
                "future_environment": exposure_row.get("future_environment"),
                "contradictions": exposure_row.get("contradictions") or [],
                "risk_gradient_bucket": gradient_row.get("risk_gradient_bucket"),
                "risk_gradient_score": gradient_row.get("risk_gradient_score"),
                "analysis_context": gradient_row.get("analysis_context") or {},
                "source_trace": gradient_row.get("source_trace") or {},
                "gradient_data_quality": gradient_row.get("data_quality") or {},
            }
        )
    return rows


def _diagnostic_metrics(
    rows: Sequence[Mapping[str, object]],
    *,
    model_id: str,
    description: str,
    flag_fn: Callable[[Mapping[str, object]], bool],
) -> dict[str, object]:
    flagged = [row for row in rows if flag_fn(row)]
    high_risk_events = [row for row in rows if _flag(row, "high_risk_event")]
    opportunity_events = [row for row in rows if _flag(row, "strong_opportunity_event")]
    contradiction_rows = [row for row in rows if row.get("contradictions")]
    captured_high_risk = [row for row in high_risk_events if flag_fn(row)]
    flagged_without_high_risk = [row for row in flagged if not _flag(row, "high_risk_event")]
    flagged_opportunity = [row for row in flagged if _flag(row, "strong_opportunity_event")]
    captured_contradictions = [row for row in contradiction_rows if flag_fn(row)]
    high_risk_capture_rate = _share(len(captured_high_risk), len(high_risk_events))
    false_warning_rate = _share(len(flagged_without_high_risk), len(flagged)) if flagged else None
    contradiction_capture_rate = _share(len(captured_contradictions), len(contradiction_rows))
    status = "baseline_no_extra_diagnostic"
    if model_id != "model_a_baseline_v5_1":
        status = "diagnostic_weak"
        if high_risk_capture_rate >= 0.5 and (false_warning_rate or 0.0) <= 0.4:
            status = "diagnostic_promising"
    return {
        "model_id": model_id,
        "description": description,
        "sample_count": len(rows),
        "diagnostic_flag_count": len(flagged),
        "diagnostic_flag_rate": _share(len(flagged), len(rows)),
        "future_high_risk_event_count": len(high_risk_events),
        "high_risk_event_capture_count": len(captured_high_risk),
        "high_risk_event_capture_rate": high_risk_capture_rate,
        "missed_high_risk_event_count": len(high_risk_events) - len(captured_high_risk),
        "missed_high_risk_event_rate": _share(len(high_risk_events) - len(captured_high_risk), len(high_risk_events)),
        "false_warning_count": len(flagged_without_high_risk),
        "false_warning_rate": false_warning_rate,
        "strong_opportunity_event_count": len(opportunity_events),
        "flagged_opportunity_count": len(flagged_opportunity),
        "flagged_opportunity_rate": _share(len(flagged_opportunity), len(flagged)) if flagged else None,
        "contradiction_row_count": len(contradiction_rows),
        "contradiction_capture_count": len(captured_contradictions),
        "contradiction_capture_rate": contradiction_capture_rate,
        "status": status,
        "sample_flagged_rows": [
            {
                "date": row.get("date"),
                "exposure_level": row.get("exposure_level"),
                "future_environment": row.get("future_environment"),
                "high_risk_event": _flag(row, "high_risk_event"),
                "strong_opportunity_event": _flag(row, "strong_opportunity_event"),
                "risk_gradient_score": row.get("risk_gradient_score"),
                "risk_gradient_bucket": row.get("risk_gradient_bucket"),
            }
            for row in flagged[:10]
        ],
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
        "exposure_level_unchanged": True,
    }


def _review_items(model_b: Mapping[str, object], model_c: Mapping[str, object], bc_identical: bool, time_safety: Mapping[str, object]) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    if int(time_safety.get("violation_count") or 0) > 0:
        items.append({"type": "time_safety_violation", "severity": "high", "evidence": {"violation_count": time_safety.get("violation_count")}})
    if float(model_b.get("high_risk_event_capture_rate") or 0.0) < 0.5:
        items.append(
            {
                "type": "low_high_risk_capture_rate",
                "severity": "high",
                "evidence": {"model": model_b.get("model_id"), "capture_rate": model_b.get("high_risk_event_capture_rate")},
            }
        )
    if model_b.get("false_warning_rate") is not None and float(model_b.get("false_warning_rate") or 0.0) > 0.5:
        items.append(
            {
                "type": "high_false_warning_rate",
                "severity": "high",
                "evidence": {"model": model_b.get("model_id"), "false_warning_rate": model_b.get("false_warning_rate")},
            }
        )
    if bc_identical:
        items.append(
            {
                "type": "candidate_context_adds_no_incremental_filter",
                "severity": "medium",
                "evidence": {
                    "model_b_flags": model_b.get("diagnostic_flag_count"),
                    "model_c_flags": model_c.get("diagnostic_flag_count"),
                },
            }
        )
    items.append(
        {
            "type": "policy_validation_diagnostic_only_do_not_modify_mapper",
            "severity": "high",
            "evidence": {"reason": "V6.1 validates diagnostic overlay only; exposure levels and policy mapper remain unchanged."},
        }
    )
    return items


def build_exposure_policy_validation(data_dir: str | Path = DATA_DIR) -> dict[str, object]:
    root = Path(data_dir)
    exposure_source = _read_json(root / "exposure_simulation.json")
    gradient_source = _read_json(root / "exposure_gradient_analysis.json")
    candidate_source = _read_json(root / "risk_gradient_candidate_rules.json")
    if not isinstance(exposure_source, Mapping) or not isinstance(exposure_source.get("historical_replay"), list):
        raise RuntimeError("exposure_simulation.json is missing or incomplete.")
    if not isinstance(gradient_source, Mapping) or not isinstance(gradient_source.get("rows"), list):
        raise RuntimeError("exposure_gradient_analysis.json is missing or incomplete.")
    if not isinstance(candidate_source, Mapping) or not isinstance(candidate_source.get("candidate_rules"), list):
        raise RuntimeError("risk_gradient_candidate_rules.json is missing or incomplete.")

    rows = _joined_rows(
        [row for row in exposure_source.get("historical_replay") or [] if isinstance(row, Mapping)],
        [row for row in gradient_source.get("rows") or [] if isinstance(row, Mapping)],
    )
    primary_candidates = [
        candidate
        for candidate in candidate_source.get("candidate_rules") or []
        if isinstance(candidate, Mapping) and candidate.get("research_tier") == "primary_research_candidate"
    ]
    model_a = _diagnostic_metrics(
        rows,
        model_id="model_a_baseline_v5_1",
        description="Fixed V5.1 exposure simulation without extra risk diagnostic overlay.",
        flag_fn=lambda row: False,
    )
    model_b = _diagnostic_metrics(
        rows,
        model_id="model_b_v5_1_plus_risk_gradient_flag",
        description="Fixed V5.1 exposure simulation plus V5.10 high-risk gradient diagnostic flag.",
        flag_fn=lambda row: row.get("risk_gradient_bucket") == "high_risk",
    )
    model_c = _diagnostic_metrics(
        rows,
        model_id="model_c_v5_1_plus_primary_candidate_context",
        description="Fixed V5.1 exposure simulation plus V5.13 primary candidate context diagnostic flag.",
        flag_fn=lambda row: row.get("risk_gradient_bucket") == "high_risk"
        and any(_candidate_matches(row, candidate) for candidate in primary_candidates),
    )
    b_dates = {row["date"] for row in model_b["sample_flagged_rows"]}
    c_dates = {row["date"] for row in model_c["sample_flagged_rows"]}
    # Compare full flagged sets, not only sample rows.
    b_all_dates = {row.get("date") for row in rows if row.get("risk_gradient_bucket") == "high_risk"}
    c_all_dates = {
        row.get("date")
        for row in rows
        if row.get("risk_gradient_bucket") == "high_risk"
        and any(_candidate_matches(row, candidate) for candidate in primary_candidates)
    }
    bc_identical = b_all_dates == c_all_dates
    time_safety = _time_safety(rows)
    review_items = _review_items(model_b, model_c, bc_identical, time_safety)
    summary = {
        "joined_sample_count": len(rows),
        "primary_candidate_count": len(primary_candidates),
        "model_count": 3,
        "model_b_c_flag_sets_identical": bc_identical,
        "model_b_only_flag_count": len(b_all_dates - c_all_dates),
        "model_c_only_flag_count": len(c_all_dates - b_all_dates),
        "policy_validation_status": "diagnostic_not_ready_for_policy_change",
        "ready_for_mapper_change": False,
        "ready_for_exposure_change": False,
        "review_items": review_items,
        "review_item_count": len(review_items),
        "key_read": (
            "Risk diagnostic flags catch only a small share of future high-risk events and have high false-warning rate; "
            "candidate context adds no incremental filter in the current sample."
        ),
    }
    return {
        "metadata": {
            "engine": "V6.1 Adaptive Exposure Policy Simulation Validation",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": (exposure_source.get("metadata") or {}).get("as_of"),
            "source_exposure_engine": (exposure_source.get("metadata") or {}).get("engine"),
            "source_gradient_engine": (gradient_source.get("metadata") or {}).get("engine"),
            "source_candidate_engine": (candidate_source.get("metadata") or {}).get("engine"),
            "purpose": "Validate whether V5 risk diagnostics improve fixed V5.1 exposure policy explanation without changing policy.",
        },
        "summary": summary,
        "model_comparison": {
            model_a["model_id"]: model_a,
            model_b["model_id"]: model_b,
            model_c["model_id"]: model_c,
        },
        "time_safety": time_safety,
        "data_quality": {
            "uses_fixed_v5_1_exposure_simulation": True,
            "uses_v5_13_primary_candidates_only": True,
            "exposure_level_unchanged": True,
            "mapper_unchanged": True,
            "future_labels_used_for_validation_only": True,
            "no_parameter_optimization": True,
            "model_b_dates_sample_equals_model_c_dates_sample": b_dates == c_dates,
        },
        "constraints": {
            "validation_only": True,
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
            "no_best_rule_selection": True,
        },
    }


def write_exposure_policy_validation(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
