from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from config import DATA_DIR


DEFAULT_OUTPUT_PATH = DATA_DIR / "exposure_context_analysis.json"


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


def classify_balanced_outcome(row: Mapping[str, object]) -> str:
    if _flag(row, "high_risk_event") or _flag(row, "future_drawdown_gt_15"):
        return "BALANCED_FAILURE"
    if _flag(row, "strong_opportunity_event"):
        return "BALANCED_MISSED_OPPORTUNITY"
    return "BALANCED_NEUTRAL"


def _context_key(row: Mapping[str, object]) -> tuple[str, str, str]:
    return (
        str(row.get("opportunity_state") or "UNKNOWN"),
        str(row.get("risk_state") or "UNKNOWN"),
        str(row.get("market_phase") or "UNKNOWN"),
    )


def _row_stats(rows: Sequence[Mapping[str, object]], total: int) -> dict[str, object]:
    usable = [row for row in rows if row.get("future_window_complete")]
    failures = sum(1 for row in usable if classify_balanced_outcome(row) == "BALANCED_FAILURE")
    missed = sum(1 for row in usable if classify_balanced_outcome(row) == "BALANCED_MISSED_OPPORTUNITY")
    return {
        "count": len(rows),
        "share_of_balanced": _share(len(rows), total),
        "usable_rows": len(usable),
        "future_high_risk_rate": _share(sum(1 for row in usable if _flag(row, "high_risk_event")), len(usable)),
        "future_drawdown_gt_15_rate": _share(sum(1 for row in usable if _flag(row, "future_drawdown_gt_15")), len(usable)),
        "future_opportunity_rate": _share(sum(1 for row in usable if _flag(row, "strong_opportunity_event")), len(usable)),
        "failure_rate": _share(failures, len(usable)),
        "missed_opportunity_rate": _share(missed, len(usable)),
        "outcome_distribution": _distribution(classify_balanced_outcome(row) for row in usable),
        "policy_mode_distribution": _distribution(row.get("policy_mode") for row in rows),
        "opportunity_state_distribution": _distribution(row.get("opportunity_state") for row in rows),
        "risk_state_distribution": _distribution(row.get("risk_state") for row in rows),
        "market_phase_distribution": _distribution(row.get("market_phase") for row in rows),
        "reason_distribution": _distribution(reason for row in rows for reason in (row.get("reasons") or [])),
    }


def _subgroups(rows: Sequence[Mapping[str, object]]) -> dict[str, dict[str, object]]:
    total = len(rows)
    return {
        group: _row_stats([row for row in rows if classify_balanced_outcome(row) == group], total)
        for group in ("BALANCED_FAILURE", "BALANCED_MISSED_OPPORTUNITY", "BALANCED_NEUTRAL")
    }


def _context_comparison(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    total = len(rows)
    grouped: dict[tuple[str, str, str], list[Mapping[str, object]]] = {}
    for row in rows:
        grouped.setdefault(_context_key(row), []).append(row)
    payload = []
    for key, group_rows in grouped.items():
        stats = _row_stats(group_rows, total)
        payload.append(
            {
                "opportunity_state": key[0],
                "risk_state": key[1],
                "market_phase": key[2],
                **{
                    name: stats[name]
                    for name in (
                        "count",
                        "share_of_balanced",
                        "usable_rows",
                        "failure_rate",
                        "missed_opportunity_rate",
                        "future_high_risk_rate",
                        "future_opportunity_rate",
                        "outcome_distribution",
                    )
                },
            }
        )
    return sorted(payload, key=lambda item: (item["count"], item["failure_rate"]), reverse=True)


def _reason_flag_analysis(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    total = len(rows)
    grouped: dict[str, list[Mapping[str, object]]] = {}
    for row in rows:
        for reason in row.get("reasons") or []:
            grouped.setdefault(str(reason), []).append(row)
    payload = []
    for reason, reason_rows in grouped.items():
        stats = _row_stats(reason_rows, total)
        payload.append(
            {
                "reason": reason,
                "count": stats["count"],
                "share_of_balanced": stats["share_of_balanced"],
                "failure_rate": stats["failure_rate"],
                "missed_opportunity_rate": stats["missed_opportunity_rate"],
                "future_high_risk_rate": stats["future_high_risk_rate"],
                "future_opportunity_rate": stats["future_opportunity_rate"],
            }
        )
    return sorted(payload, key=lambda item: (item["count"], item["failure_rate"]), reverse=True)


def _split_candidates(context_rows: Sequence[Mapping[str, object]], reason_rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    risk_contexts = [
        row
        for row in context_rows
        if int(row.get("usable_rows") or 0) >= 3 and float(row.get("failure_rate") or 0.0) >= 0.3
    ][:6]
    opportunity_contexts = [
        row
        for row in context_rows
        if int(row.get("usable_rows") or 0) >= 3 and float(row.get("missed_opportunity_rate") or 0.0) >= 0.25
    ][:6]
    risk_reasons = [
        row
        for row in reason_rows
        if int(row.get("count") or 0) >= 5 and float(row.get("failure_rate") or 0.0) >= 0.25
    ][:6]
    opportunity_reasons = [
        row
        for row in reason_rows
        if int(row.get("count") or 0) >= 5 and float(row.get("missed_opportunity_rate") or 0.0) >= 0.2
    ][:6]
    return {
        "risk_contexts": risk_contexts,
        "opportunity_contexts": opportunity_contexts,
        "risk_reasons": risk_reasons,
        "opportunity_reasons": opportunity_reasons,
        "recommendation": "split_balanced_before_mapper_changes"
        if risk_contexts or opportunity_contexts
        else "balanced_split_not_yet_supported",
    }


def _review_items(summary: Mapping[str, object], split: Mapping[str, object]) -> list[dict[str, object]]:
    items = []
    if float(summary.get("balanced_share_of_all") or 0.0) >= 0.65:
        items.append(
            {
                "type": "balanced_bucket_dominates_exposure",
                "severity": "high",
                "evidence": {"balanced_share_of_all": summary.get("balanced_share_of_all")},
            }
        )
    if split.get("risk_contexts"):
        items.append(
            {
                "type": "risk_contexts_inside_balanced",
                "severity": "high",
                "evidence": {"context_count": len(split.get("risk_contexts") or [])},
            }
        )
    if split.get("opportunity_contexts"):
        items.append(
            {
                "type": "opportunity_contexts_inside_balanced",
                "severity": "medium",
                "evidence": {"context_count": len(split.get("opportunity_contexts") or [])},
            }
        )
    items.append(
        {
            "type": "numeric_macro_structure_fields_missing",
            "severity": "medium",
            "evidence": {
                "available_proxy": "reason/evidence flags",
                "missing_fields": ["macro_score", "trend_score", "breadth_score", "liquidity_score"],
            },
        }
    )
    return items


def build_exposure_context_analysis(data_dir: str | Path = DATA_DIR) -> dict[str, object]:
    root = Path(data_dir)
    source = _read_json(root / "exposure_simulation.json")
    if not isinstance(source, Mapping) or not source.get("historical_replay"):
        raise RuntimeError("exposure_simulation.json is missing or incomplete.")
    rows = [row for row in source.get("historical_replay") or [] if isinstance(row, Mapping)]
    balanced_rows = [row for row in rows if row.get("exposure_level") == "BALANCED"]
    balanced_usable = [row for row in balanced_rows if row.get("future_window_complete")]
    subgroups = _subgroups(balanced_usable)
    context_rows = _context_comparison(balanced_usable)
    reason_rows = _reason_flag_analysis(balanced_usable)
    split = _split_candidates(context_rows, reason_rows)
    summary = {
        "total_replay_rows": len(rows),
        "balanced_count": len(balanced_rows),
        "balanced_share_of_all": _share(len(balanced_rows), len(rows)),
        "balanced_usable_rows": len(balanced_usable),
        "balanced_outcome_distribution": _distribution(classify_balanced_outcome(row) for row in balanced_usable),
        "balanced_failure_rate": subgroups["BALANCED_FAILURE"]["share_of_balanced"],
        "balanced_missed_opportunity_rate": subgroups["BALANCED_MISSED_OPPORTUNITY"]["share_of_balanced"],
        "split_candidates": split,
        "review_items": [],
        "key_read": "",
    }
    summary["review_items"] = _review_items(summary, split)
    summary["review_item_count"] = len(summary["review_items"])
    summary["key_read"] = (
        "BALANCED should be decomposed before any mapper change. "
        f"Failure share={summary['balanced_failure_rate']}, "
        f"missed opportunity share={summary['balanced_missed_opportunity_rate']}, "
        f"recommendation={split['recommendation']}."
    )
    return {
        "metadata": {
            "engine": "V5.3 Exposure Context Decomposition Audit",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": (source.get("metadata") or {}).get("as_of"),
            "source_engine": (source.get("metadata") or {}).get("engine"),
            "purpose": "Decompose the fixed V5.1 BALANCED bucket to identify risk and opportunity contexts without changing rules.",
        },
        "summary": summary,
        "balanced_subgroups": subgroups,
        "context_comparison": context_rows,
        "reason_flag_analysis": reason_rows,
        "sample_review_rows": {
            "failures": [
                _sample_row(row)
                for row in balanced_usable
                if classify_balanced_outcome(row) == "BALANCED_FAILURE"
            ][:8],
            "missed_opportunities": [
                _sample_row(row)
                for row in balanced_usable
                if classify_balanced_outcome(row) == "BALANCED_MISSED_OPPORTUNITY"
            ][:8],
        },
        "data_quality": {
            "uses_fixed_v5_1_exposure_simulation": True,
            "balanced_bucket_only": True,
            "future_labels_used_for_validation_only": True,
            "available_context_fields": [
                "policy_mode",
                "opportunity_state",
                "risk_state",
                "market_phase",
                "reasons",
                "blocked",
            ],
            "missing_numeric_context_fields": [
                "macro_score",
                "trend_score",
                "breadth_score",
                "liquidity_score",
            ],
        },
        "constraints": {
            "audit_only": True,
            "does_not_modify_v5_1_rules": True,
            "does_not_add_exposure_levels": True,
            "balanced_analysis_only": True,
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


def _sample_row(row: Mapping[str, object]) -> dict[str, object]:
    return {
        "date": row.get("date"),
        "policy_mode": row.get("policy_mode"),
        "opportunity_state": row.get("opportunity_state"),
        "risk_state": row.get("risk_state"),
        "market_phase": row.get("market_phase"),
        "outcome": classify_balanced_outcome(row),
        "future_environment": row.get("future_environment"),
        "reasons": row.get("reasons"),
    }


def write_exposure_context_analysis(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
