from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from config import DATA_DIR
from adaptive_exposure.exposure_decision_context import (
    CAUTION_MODES,
    DECISION_MODES,
    PARTICIPATION_MODES,
    decision_context,
)


DEFAULT_OUTPUT_PATH = DATA_DIR / "exposure_decision_audit.json"


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
    gradient_by_date = {str(row.get("date") or ""): row for row in gradient_rows}
    rows = []
    for exposure_row in exposure_rows:
        date = _date_text(exposure_row.get("date"))
        if not date or not exposure_row.get("future_window_complete"):
            continue
        gradient_row = gradient_by_date.get(date)
        if not isinstance(gradient_row, Mapping):
            continue
        context = decision_context(gradient_row)
        rows.append(
            {
                "date": date,
                "v5_1_exposure_level": exposure_row.get("exposure_level"),
                "v5_1_policy_mode": exposure_row.get("policy_mode"),
                "future_flags": exposure_row.get("future_flags") or {},
                "future_environment": exposure_row.get("future_environment"),
                "contradictions": exposure_row.get("contradictions") or [],
                "source_trace": gradient_row.get("source_trace") or {},
                "gradient_data_quality": gradient_row.get("data_quality") or {},
                **context,
            }
        )
    return rows


def _mode_stats(rows: Sequence[Mapping[str, object]]) -> dict[str, dict[str, object]]:
    payload: dict[str, dict[str, object]] = {}
    for mode in DECISION_MODES:
        group_rows = [row for row in rows if row.get("decision_mode") == mode]
        contradiction_rows = [row for row in group_rows if row.get("contradictions")]
        payload[mode] = {
            "sample_count": len(group_rows),
            "sample_share": _share(len(group_rows), len(rows)),
            "future_high_risk_count": sum(1 for row in group_rows if _flag(row, "high_risk_event")),
            "future_high_risk_rate": _share(sum(1 for row in group_rows if _flag(row, "high_risk_event")), len(group_rows)),
            "future_opportunity_count": sum(1 for row in group_rows if _flag(row, "strong_opportunity_event")),
            "future_opportunity_rate": _share(sum(1 for row in group_rows if _flag(row, "strong_opportunity_event")), len(group_rows)),
            "contradiction_row_count": len(contradiction_rows),
            "contradiction_row_rate": _share(len(contradiction_rows), len(group_rows)),
            "reason_distribution": _distribution(row.get("reason") for row in group_rows),
        }
    return payload


def _group_metrics(rows: Sequence[Mapping[str, object]], modes: Sequence[str]) -> dict[str, object]:
    group_rows = [row for row in rows if row.get("decision_mode") in modes]
    return {
        "sample_count": len(group_rows),
        "future_high_risk_rate": _share(sum(1 for row in group_rows if _flag(row, "high_risk_event")), len(group_rows)),
        "future_opportunity_rate": _share(sum(1 for row in group_rows if _flag(row, "strong_opportunity_event")), len(group_rows)),
        "contradiction_row_rate": _share(sum(1 for row in group_rows if row.get("contradictions")), len(group_rows)),
    }


def _separation_review(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    caution = _group_metrics(rows, CAUTION_MODES)
    participation = _group_metrics(rows, PARTICIPATION_MODES)
    risk_lift = round(float(caution["future_high_risk_rate"]) - float(participation["future_high_risk_rate"]), 6)
    opportunity_lift = round(float(participation["future_opportunity_rate"]) - float(caution["future_opportunity_rate"]), 6)
    return {
        "caution_group": caution,
        "participation_group": participation,
        "caution_vs_participation_risk_lift": risk_lift,
        "participation_vs_caution_opportunity_lift": opportunity_lift,
        "risk_separation": "visible" if risk_lift >= 0.05 else "weak",
        "opportunity_separation": "visible" if opportunity_lift >= 0.05 else "weak",
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
        "v5_1_exposure_level_unchanged": True,
    }


def _review_items(separation: Mapping[str, object], time_safety: Mapping[str, object]) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    if int(time_safety.get("violation_count") or 0) > 0:
        items.append({"type": "time_safety_violation", "severity": "high", "evidence": {"violation_count": time_safety.get("violation_count")}})
    if separation.get("risk_separation") == "weak":
        items.append(
            {
                "type": "decision_context_risk_separation_weak",
                "severity": "high",
                "evidence": {"risk_lift": separation.get("caution_vs_participation_risk_lift")},
            }
        )
    if separation.get("opportunity_separation") == "weak":
        items.append(
            {
                "type": "decision_context_opportunity_separation_weak",
                "severity": "high",
                "evidence": {"opportunity_lift": separation.get("participation_vs_caution_opportunity_lift")},
            }
        )
    items.append(
        {
            "type": "decision_context_research_only_do_not_modify_exposure",
            "severity": "high",
            "evidence": {"reason": "V6.2 creates research labels only; no exposure level, mapper, weight, ETF, or trade change."},
        }
    )
    return items


def build_exposure_decision_audit(data_dir: str | Path = DATA_DIR) -> dict[str, object]:
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
    mode_stats = _mode_stats(rows)
    separation = _separation_review(rows)
    time_safety = _time_safety(rows)
    review_items = _review_items(separation, time_safety)
    summary = {
        "joined_sample_count": len(rows),
        "decision_mode_distribution": _distribution(row.get("decision_mode") for row in rows),
        "risk_separation": separation["risk_separation"],
        "opportunity_separation": separation["opportunity_separation"],
        "ready_for_mapper_change": False,
        "ready_for_exposure_change": False,
        "conclusion": "decision_context_design_not_validated",
        "review_items": review_items,
        "review_item_count": len(review_items),
        "key_read": (
            "Decision context labels are interpretable, but they do not yet separate risk or opportunity enough "
            "to support any exposure policy change."
        ),
    }
    return {
        "metadata": {
            "engine": "V6.2 Adaptive Exposure Decision Layer Design Audit",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": (exposure_source.get("metadata") or {}).get("as_of"),
            "source_exposure_engine": (exposure_source.get("metadata") or {}).get("engine"),
            "source_gradient_engine": (gradient_source.get("metadata") or {}).get("engine"),
            "purpose": "Audit research-only decision context labels without changing exposure policy.",
        },
        "summary": summary,
        "mode_stats": mode_stats,
        "separation_review": separation,
        "rows": rows,
        "time_safety": time_safety,
        "data_quality": {
            "uses_fixed_v5_1_exposure_simulation": True,
            "uses_fixed_v5_risk_gradient": True,
            "decision_modes_are_research_labels_only": True,
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


def write_exposure_decision_audit(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
