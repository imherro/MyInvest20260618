from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from config import DATA_DIR
from allocation_policy.opportunity_risk_classifier import build_opportunity_risk_snapshot
from allocation_policy.opportunity_risk_policy import map_row_policy
from allocation_policy.policy_historical_validation import DEFAULT_PERIODS


DEFAULT_OUTPUT_PATH = DATA_DIR / "opportunity_risk_policy.json"


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


def _transition_matrix(rows: Sequence[Mapping[str, object]]) -> dict[str, dict[str, int]]:
    matrix: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    previous = None
    for row in rows:
        mode = str(row.get("policy_mode") or "unknown")
        if previous is not None:
            matrix[previous][mode] += 1
        previous = mode
    return {from_mode: dict(to_modes) for from_mode, to_modes in sorted(matrix.items())}


def _period_summary(period: Mapping[str, object], rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    start = str(period["start"])
    end = str(period["end"])
    period_rows = [row for row in rows if start <= str(row.get("date") or "") <= end]
    return {
        "period": period.get("id"),
        "label": period.get("label"),
        "window": {"start": start, "end": end},
        "signal_count": len(period_rows),
        "policy_mode_distribution": _distribution(row.get("policy_mode") for row in period_rows),
        "opportunity_state_distribution": _distribution(row.get("opportunity_state") for row in period_rows),
        "risk_state_distribution": _distribution(row.get("risk_state") for row in period_rows),
        "dominant_policy_mode": _dominant_mode(period_rows),
        "interpretation": _period_interpretation(period_rows),
    }


def _dominant_mode(rows: Sequence[Mapping[str, object]]) -> str | None:
    counter = Counter(str(row.get("policy_mode") or "unknown") for row in rows)
    return counter.most_common(1)[0][0] if counter else None


def _period_interpretation(rows: Sequence[Mapping[str, object]]) -> str:
    if not rows:
        return "no_replay_rows"
    modes = Counter(str(row.get("policy_mode") or "unknown") for row in rows)
    defensive_share = (modes["defensive"] + modes["protect_capital"]) / len(rows)
    participation_share = (
        modes["participate"]
        + modes["participate_selectively"]
        + modes["participate_with_control"]
        + modes["late_cycle_control"]
    ) / len(rows)
    if defensive_share >= 0.45:
        return "defensive_or_protection_dominant"
    if participation_share >= 0.45:
        return "participation_with_controls_dominant"
    return "mixed_policy_modes"


def _load_or_build_opportunity_snapshot(data_dir: str | Path) -> dict[str, object]:
    root = Path(data_dir)
    payload = _read_json(root / "opportunity_risk_snapshot.json")
    if isinstance(payload, Mapping) and payload.get("metadata"):
        return dict(payload)
    return build_opportunity_risk_snapshot(data_dir)


def build_opportunity_risk_policy_snapshot(data_dir: str | Path = DATA_DIR) -> dict[str, object]:
    opportunity_snapshot = _load_or_build_opportunity_snapshot(data_dir)
    current = _section(opportunity_snapshot, "current")
    current_policy = map_row_policy(current)
    replay_rows = opportunity_snapshot.get("historical_replay") or []
    mapped_rows = []
    for row in replay_rows:
        if not isinstance(row, Mapping):
            continue
        policy = map_row_policy(row)
        mapped_rows.append(
            {
                "date": row.get("date"),
                "opportunity_state": policy["opportunity_state"],
                "risk_state": policy["risk_state"],
                "combined_state": row.get("combined_state"),
                "policy_mode": policy["policy_mode"],
                "actions_allowed": policy["actions_allowed"],
                "actions_blocked": policy["actions_blocked"],
                "interpretation": policy["interpretation"],
                "source_evidence": row.get("evidence") or [],
                "data_quality": row.get("data_quality") or {},
            }
        )

    period_validation = [_period_summary(period, mapped_rows) for period in DEFAULT_PERIODS]
    return {
        "metadata": {
            "engine": "V4.4 Opportunity-Risk Policy Mapping Validation",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": _section(opportunity_snapshot, "metadata").get("as_of"),
            "source_engine": _section(opportunity_snapshot, "metadata").get("engine"),
            "purpose": "Map opportunity/risk states into qualitative policy modes and validate historical state distributions.",
            "policy_mapping_only": True,
        },
        "current": {
            **current_policy,
            "combined_state": current.get("combined_state"),
            "source_interpretation": current.get("interpretation"),
        },
        "summary": {
            "replay_count": len(mapped_rows),
            "policy_mode_distribution": _distribution(row.get("policy_mode") for row in mapped_rows),
            "opportunity_state_distribution": _distribution(row.get("opportunity_state") for row in mapped_rows),
            "risk_state_distribution": _distribution(row.get("risk_state") for row in mapped_rows),
            "transition_matrix": _transition_matrix(mapped_rows),
            "key_read": _key_read(mapped_rows),
        },
        "period_validation": period_validation,
        "historical_replay": mapped_rows,
        "source_snapshot": {
            "current": current,
            "historical_summary": opportunity_snapshot.get("historical_summary") or {},
        },
        "data_quality": {
            "uses_v4_3_opportunity_risk_snapshot": True,
            "no_future_returns": True,
            "historical_replay_uses_v4_3_dates": True,
            "policy_rules_are_static_mapping": True,
        },
        "constraints": {
            "policy_mapping_only": True,
            "no_etf_code": True,
            "no_asset_weight": True,
            "no_portfolio_weight": True,
            "no_position_sizing": True,
            "no_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
            "no_parameter_optimization": True,
            "does_not_modify_v4_1_policy": True,
            "v4_3_classifier_business_rules_unchanged": True,
            "v4_3_price_extension_field_renamed_to_proxy": True,
        },
    }


def _key_read(rows: Sequence[Mapping[str, object]]) -> str:
    if not rows:
        return "No historical policy mapping rows are available."
    modes = Counter(str(row.get("policy_mode") or "unknown") for row in rows)
    dominant, count = modes.most_common(1)[0]
    control = modes["participate_with_control"] + modes["late_cycle_control"] + modes["protect_capital"]
    return (
        f"Replay mapped {len(rows)} states into policy modes. Dominant mode is {dominant} "
        f"({count}/{len(rows)}); control/protection modes account for {control}/{len(rows)}."
    )


def write_opportunity_risk_policy_snapshot(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
