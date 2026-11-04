from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from config import DATA_DIR
from adaptive_exposure.exposure_policy_mapper import decision_to_payload, map_policy_to_exposure
from adaptive_exposure.exposure_schema import exposure_rank
from allocation_policy.policy_historical_validation import DEFAULT_PERIODS


DEFAULT_OUTPUT_PATH = DATA_DIR / "exposure_simulation.json"


def _read_json(path: Path) -> object:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _section(payload: Mapping[str, object], name: str) -> Mapping[str, object]:
    value = payload.get(name)
    return value if isinstance(value, Mapping) else {}


def _share(count: int, total: int) -> float:
    return round(count / total, 6) if total else 0.0


def _distribution(values: Iterable[object]) -> dict[str, dict[str, object]]:
    counter = Counter(str(value or "unknown") for value in values)
    total = sum(counter.values())
    return {
        key: {"count": count, "share": _share(count, total)}
        for key, count in sorted(counter.items())
    }


def _row_contradictions(row: Mapping[str, object]) -> list[dict[str, object]]:
    flags = _section(row, "future_flags")
    level = str(row.get("exposure_level") or "BALANCED")
    items = []
    if flags.get("high_risk_event") and exposure_rank(level) >= exposure_rank("HIGH"):
        items.append(
            {
                "type": "high_risk_environment_with_high_exposure_level",
                "severity": "high",
                "evidence": {"exposure_level": level, "future_environment": row.get("future_environment")},
            }
        )
    if flags.get("future_drawdown_gt_15") and exposure_rank(level) >= exposure_rank("BALANCED"):
        items.append(
            {
                "type": "large_drawdown_with_non_defensive_level",
                "severity": "medium",
                "evidence": {"exposure_level": level, "future_environment": row.get("future_environment")},
            }
        )
    if flags.get("strong_opportunity_event") and exposure_rank(level) <= exposure_rank("LOW"):
        items.append(
            {
                "type": "strong_opportunity_with_low_exposure_level",
                "severity": "medium",
                "evidence": {"exposure_level": level, "future_environment": row.get("future_environment")},
            }
        )
    return items


def _join_rows(
    policy_rows: Sequence[Mapping[str, object]],
    phase_rows: Sequence[Mapping[str, object]],
    validation_rows: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    phase_by_date = {str(row.get("date") or ""): row for row in phase_rows}
    validation_by_date = {str(row.get("date") or ""): row for row in validation_rows if row.get("future_window_complete")}
    rows = []
    for policy_row in policy_rows:
        date_text = str(policy_row.get("date") or "")
        phase_row = phase_by_date.get(date_text, {})
        decision = decision_to_payload(map_policy_to_exposure(policy_row, phase_row))
        validation = validation_by_date.get(date_text, {})
        row = {
            "date": date_text,
            "policy_mode": policy_row.get("policy_mode"),
            "opportunity_state": policy_row.get("opportunity_state"),
            "risk_state": policy_row.get("risk_state"),
            "market_phase": phase_row.get("phase"),
            **decision,
            "future_environment": validation.get("future_environment"),
            "future_flags": validation.get("future_flags") or {},
            "future_metrics": validation.get("future_metrics") or {},
            "future_window_complete": bool(validation),
        }
        row["contradictions"] = _row_contradictions(row)
        rows.append(row)
    return rows


def _audit(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    usable = [row for row in rows if row.get("future_window_complete")]
    contradictions = []
    opportunity_miss = []
    for row in usable:
        for item in row.get("contradictions") or []:
            enriched = {"date": row.get("date"), "exposure_level": row.get("exposure_level"), **item}
            contradictions.append(enriched)
            if item.get("type") == "strong_opportunity_with_low_exposure_level":
                opportunity_miss.append(enriched)
    return {
        "usable_rows": len(usable),
        "contradiction_count": len(contradictions),
        "contradiction_rate": _share(len(contradictions), len(usable)),
        "opportunity_miss_count": len(opportunity_miss),
        "opportunity_miss_rate": _share(len(opportunity_miss), len(usable)),
        "type_distribution": _distribution(item.get("type") for item in contradictions),
        "sample_review_items": contradictions[:12],
    }


def _period_summary(period: Mapping[str, object], rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    start = str(period["start"])
    end = str(period["end"])
    period_rows = [row for row in rows if start <= str(row.get("date") or "") <= end]
    usable = [row for row in period_rows if row.get("future_window_complete")]
    contradictions = sum(len(row.get("contradictions") or []) for row in usable)
    return {
        "period": period.get("id"),
        "label": period.get("label"),
        "window": {"start": start, "end": end},
        "signal_count": len(period_rows),
        "usable_rows": len(usable),
        "exposure_level_distribution": _distribution(row.get("exposure_level") for row in period_rows),
        "contradiction_count": contradictions,
        "contradiction_rate": _share(contradictions, len(usable)),
    }


def build_exposure_simulation(data_dir: str | Path = DATA_DIR) -> dict[str, object]:
    root = Path(data_dir)
    policy = _read_json(root / "opportunity_risk_policy.json")
    phase = _read_json(root / "market_phase_snapshot.json")
    validation = _read_json(root / "policy_effectiveness.json")
    if not isinstance(policy, Mapping) or not policy.get("historical_replay"):
        raise RuntimeError("opportunity_risk_policy.json is missing or incomplete.")
    if not isinstance(phase, Mapping):
        phase = {}
    if not isinstance(validation, Mapping):
        validation = {}

    current = decision_to_payload(
        map_policy_to_exposure(_section(policy, "current"), _section(phase, "current"))
    )
    current["as_of"] = _section(policy, "metadata").get("as_of")
    rows = _join_rows(
        [row for row in policy.get("historical_replay") or [] if isinstance(row, Mapping)],
        [row for row in phase.get("historical_replay") or [] if isinstance(row, Mapping)],
        [row for row in validation.get("validation_rows") or [] if isinstance(row, Mapping)],
    )
    audit = _audit(rows)
    return {
        "metadata": {
            "engine": "V5.1 Adaptive Exposure Policy Simulation Foundation",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": current.get("as_of"),
            "source_policy_engine": _section(policy, "metadata").get("engine"),
            "source_phase_engine": _section(phase, "metadata").get("engine"),
            "purpose": "Map fixed qualitative policy modes to qualitative exposure levels and audit historical contradictions.",
        },
        "current": current,
        "summary": {
            "replay_count": len(rows),
            "exposure_level_distribution": _distribution(row.get("exposure_level") for row in rows),
            "policy_mode_distribution": _distribution(row.get("policy_mode") for row in rows),
            "audit": audit,
            "key_read": _key_read(rows, audit),
        },
        "period_validation": [_period_summary(period, rows) for period in DEFAULT_PERIODS],
        "historical_replay": rows,
        "data_quality": {
            "uses_fixed_v4_4_policy": True,
            "uses_fixed_v4_6_phase": True,
            "uses_v4_5_future_labels_only_for_validation": True,
            "qualitative_levels_only": True,
            "no_percentage_exposure": True,
        },
        "constraints": {
            "simulation_only": True,
            "qualitative_level_only": True,
            "no_percentage": True,
            "no_etf_code": True,
            "no_asset_weight": True,
            "no_portfolio_weight": True,
            "no_position_sizing": True,
            "no_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
            "no_return_optimization": True,
        },
    }


def _key_read(rows: Sequence[Mapping[str, object]], audit: Mapping[str, object]) -> str:
    levels = Counter(str(row.get("exposure_level") or "unknown") for row in rows)
    dominant, count = levels.most_common(1)[0] if levels else ("unknown", 0)
    return (
        f"Mapped {len(rows)} policy rows to qualitative exposure levels. Dominant level is {dominant} "
        f"({count}/{len(rows)}); contradiction_rate={audit.get('contradiction_rate')}."
    )


def write_exposure_simulation(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
