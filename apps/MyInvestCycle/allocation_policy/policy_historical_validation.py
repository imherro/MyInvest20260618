from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from config import DATA_DIR
from allocation_policy.risk_budget_schema import budget_level_index
from allocation_policy.style_constraint_engine import build_style_constraints
from style_allocation.style_allocator import build_style_preference


DEFAULT_OUTPUT_PATH = DATA_DIR / "allocation_policy_validation.json"
DEFAULT_START_DATE = "20150101"
DEFAULT_END_DATE = "20261231"
DEFAULT_PERIODS: tuple[dict[str, object], ...] = (
    {"id": "2015_bull_bear", "label": "2015 bull/bear", "start": "20150101", "end": "20151231"},
    {"id": "2018_bear", "label": "2018 bear", "start": "20180101", "end": "20181231"},
    {"id": "2020_covid_recovery", "label": "2020 covid/recovery", "start": "20200101", "end": "20201231"},
    {"id": "2021_core_asset", "label": "2021 core asset divergence", "start": "20210101", "end": "20211231"},
    {"id": "2022_bear", "label": "2022 bear", "start": "20220101", "end": "20221231"},
    {"id": "2024_2026_structural", "label": "2024-2026 structural bull", "start": "20240101", "end": "20261231"},
)


def _read_json(path: Path) -> object:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _section(payload: Mapping[str, object], name: str) -> Mapping[str, object]:
    value = payload.get(name)
    return value if isinstance(value, Mapping) else {}


def _num(value: object, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _round_or_none(value: object, digits: int = 6) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _score_0_100(value: object) -> float:
    number = _num(value)
    if 0.0 <= number <= 1.5:
        return round(number * 100.0, 4)
    return round(number, 4)


def _share(count: int, total: int) -> float:
    return round(count / total, 6) if total else 0.0


def _distribution(values: Iterable[object]) -> dict[str, dict[str, object]]:
    counter = Counter(str(value or "unknown") for value in values)
    total = sum(counter.values())
    return {
        key: {"count": count, "share": _share(count, total)}
        for key, count in sorted(counter.items())
    }


def _latest_context(context_rows: Sequence[Mapping[str, object]], date_text: str) -> Mapping[str, object] | None:
    latest = None
    for row in context_rows:
        row_date = str(row.get("date") or "")
        if row_date and row_date <= date_text:
            latest = row
        if row_date > date_text:
            break
    return latest


def _context_rows(payload: Mapping[str, object]) -> list[Mapping[str, object]]:
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return []
    return sorted((row for row in rows if isinstance(row, Mapping)), key=lambda row: str(row.get("date") or ""))


def _style_incremental_edge(payload: Mapping[str, object]) -> dict[str, object]:
    summary = _section(payload, "summary")
    edge = _section(summary, "edge_read")
    return {
        "style_incremental_edge_status": edge.get("style_incremental_edge_status") or "weak_short_horizon_trace",
        "tradable_20d_combined_minus_baseline_return": edge.get("tradable_20d_combined_minus_baseline_return"),
        "tradable_60d_combined_minus_baseline_return": edge.get("tradable_60d_combined_minus_baseline_return"),
        "tradable_20d_combined_ic_minus_baseline": edge.get("tradable_20d_combined_ic_minus_baseline"),
        "tradable_60d_combined_ic_minus_baseline": edge.get("tradable_60d_combined_ic_minus_baseline"),
        "tradable_20d_combined_hit_rate": edge.get("tradable_20d_combined_hit_rate"),
        "tradable_60d_combined_hit_rate": edge.get("tradable_60d_combined_hit_rate"),
    }


def _theme_warnings(style_context: Mapping[str, object], theme_risk_level: str) -> list[str]:
    warnings = []
    if theme_risk_level in {"medium", "high"}:
        warnings.append(f"theme_risk_{theme_risk_level}")
    if _num(style_context.get("crowding_score")) >= 56:
        warnings.append("crowding_score_elevated")
    if _num(style_context.get("price_extension")) >= 70:
        warnings.append("price_extension_high")
    if _num(style_context.get("industry_breadth")) < 0.2:
        warnings.append("industry_breadth_narrow")
    return warnings


def _historical_inputs(
    signal: Mapping[str, object],
    context_row: Mapping[str, object] | None,
    style_incremental: Mapping[str, object],
) -> dict[str, object]:
    style_context = _section(context_row or {}, "style_context")
    theme_risk_level = str(signal.get("theme_risk_level") or style_context.get("theme_risk_level") or "unknown")
    market_structure = {
        "state": signal.get("market_structure_state") or "UNKNOWN",
        "index_trend": _score_0_100(style_context.get("trend")),
        "breadth": _score_0_100(style_context.get("breadth")),
        "liquidity": _score_0_100(style_context.get("liquidity")),
    }
    industry_opportunity = {
        "state": "HISTORICAL_CONTEXT",
        "theme_persistence": _round_or_none(style_context.get("theme_persistence"), 4),
        "rotation_health": _score_0_100(style_context.get("positive_industry_ratio")),
        "industry_breadth": _round_or_none(style_context.get("industry_breadth"), 6),
        "top_industry_ratio": _round_or_none(style_context.get("top_industry_ratio"), 6),
        "top_themes": (context_row or {}).get("top_themes") or [],
    }
    theme_risk = {
        "level": theme_risk_level,
        "quality_score": round(max(0.0, 100.0 - _score_0_100(style_context.get("pressure"))), 4),
        "crowding_score": _round_or_none(style_context.get("crowding_score"), 4),
        "warnings": _theme_warnings(style_context, theme_risk_level),
    }
    base_inputs = {
        "as_of": signal.get("as_of") or signal.get("date"),
        "macro": {"state": signal.get("macro_state") or "UNKNOWN", "score": None, "confidence": None},
        "structural": {
            "state": signal.get("structural_state") or signal.get("allocation_structural_state") or "UNKNOWN",
            "score": None,
            "confidence": None,
        },
        "market_structure": market_structure,
        "industry_opportunity": industry_opportunity,
        "theme_risk": theme_risk,
        "asset_opportunity_by_style": {},
        "latest_alpha_style_exposure": {},
        "residual_alpha": {"economic_strength": "not_evaluated_in_historical_validation"},
    }
    preference = build_style_preference(base_inputs)
    return {
        **base_inputs,
        "style_preference": preference,
        "style_incremental": dict(style_incremental),
    }


def _curve_value(row: Mapping[str, object]) -> float | None:
    for key in ("buy_hold_equal_equity", "benchmark_510500_equity", "benchmark_510300_equity"):
        value = _round_or_none(row.get(key), 8)
        if value is not None:
            return value
    return None


def _market_return_between(
    equity_curve: Sequence[Mapping[str, object]],
    start_date: str,
    end_date: str | None,
) -> float | None:
    rows = [
        row
        for row in equity_curve
        if str(row.get("date") or "") > start_date and (end_date is None or str(row.get("date") or "") <= end_date)
    ]
    if len(rows) < 2:
        return None
    start_value = _curve_value(rows[0])
    end_value = _curve_value(rows[-1])
    if start_value in (None, 0) or end_value is None:
        return None
    return round(end_value / start_value - 1.0, 6)


def _period_market_return(period_attribution: Mapping[str, object], period_id: str) -> float | None:
    period = _section(period_attribution, period_id)
    strategies = _section(period, "strategies")
    for key in ("buy_hold_equal_510300_510500", "benchmark_510500", "benchmark_510300"):
        row = _section(strategies, key)
        value = _round_or_none(row.get("total_return"), 6)
        if value is not None:
            return value
    return None


def _risk_posture(policy: Mapping[str, object]) -> str:
    constraints = _section(policy, "risk_constraints")
    max_offensive = str(constraints.get("max_offensive_beta_budget") or "blocked")
    defensive_floor = str(constraints.get("min_defensive_beta_budget") or "blocked")
    if budget_level_index(defensive_floor) >= budget_level_index("medium_high"):
        return "defensive"
    if budget_level_index(max_offensive) >= budget_level_index("medium_high"):
        return "offensive"
    if budget_level_index(max_offensive) <= budget_level_index("low"):
        return "risk_off"
    return "balanced"


def _controls_from_policy(policy: Mapping[str, object]) -> list[str]:
    constraints = _section(policy, "risk_constraints")
    controls = []
    if constraints.get("requires_breadth_confirmation_for_offensive_expansion"):
        controls.append("breadth_confirmation")
    if constraints.get("requires_crowding_control"):
        controls.append("crowding_control")
    if constraints.get("style_score_may_not_expand_budget_by_itself"):
        controls.append("style_descriptor_only")
    environment = _section(policy, "allocation_environment")
    if environment.get("single_theme_concentration_watch"):
        controls.append("single_theme_watch")
    return controls


def _signal_contradictions(row: Mapping[str, object]) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    constraints = _section(row, "risk_constraints")
    environment = _section(row, "allocation_environment")
    market_return = row.get("forward_market_return")
    max_offensive = str(constraints.get("max_offensive_beta_budget") or "blocked")
    defensive_floor = str(constraints.get("min_defensive_beta_budget") or "blocked")
    structural_state = str(environment.get("structural_state") or "")
    theme_risk = str(environment.get("theme_risk_level") or "")

    if (
        isinstance(market_return, (int, float))
        and market_return <= -0.08
        and budget_level_index(max_offensive) >= budget_level_index("medium_high")
    ):
        items.append(
            {
                "date": row.get("date"),
                "type": "high_offensive_budget_before_negative_forward_window",
                "severity": "medium",
                "evidence": {
                    "forward_market_return": market_return,
                    "max_offensive_beta_budget": max_offensive,
                    "structural_state": structural_state,
                },
            }
        )
    if (
        isinstance(market_return, (int, float))
        and market_return >= 0.12
        and budget_level_index(max_offensive) <= budget_level_index("low")
    ):
        items.append(
            {
                "date": row.get("date"),
                "type": "over_defensive_budget_before_positive_forward_window",
                "severity": "medium",
                "evidence": {
                    "forward_market_return": market_return,
                    "max_offensive_beta_budget": max_offensive,
                    "structural_state": structural_state,
                },
            }
        )
    if structural_state in {"WEAK_MARKET", "BEAR_STRUCTURE"} and budget_level_index(max_offensive) >= budget_level_index("medium_high"):
        items.append(
            {
                "date": row.get("date"),
                "type": "weak_structure_with_high_offensive_budget",
                "severity": "high",
                "evidence": {
                    "structural_state": structural_state,
                    "max_offensive_beta_budget": max_offensive,
                },
            }
        )
    if theme_risk in {"medium", "high"} and constraints.get("requires_crowding_control") is not True:
        items.append(
            {
                "date": row.get("date"),
                "type": "theme_risk_without_crowding_control",
                "severity": "high",
                "evidence": {"theme_risk_level": theme_risk},
            }
        )
    if budget_level_index(defensive_floor) < budget_level_index("medium") and theme_risk == "high":
        items.append(
            {
                "date": row.get("date"),
                "type": "high_theme_risk_without_defensive_floor",
                "severity": "medium",
                "evidence": {
                    "theme_risk_level": theme_risk,
                    "min_defensive_beta_budget": defensive_floor,
                },
            }
        )
    return items


def _period_interpretation(market_return: float | None, rows: Sequence[Mapping[str, object]]) -> str:
    if not rows:
        return "no_replay_rows"
    postures = Counter(str(row.get("risk_posture") or "unknown") for row in rows)
    total = len(rows)
    defensive_share = (postures["defensive"] + postures["risk_off"]) / total
    offensive_share = postures["offensive"] / total
    if market_return is not None and market_return <= -0.1:
        if defensive_share >= 0.45:
            return "risk_reduction_aligned"
        return "risk_reduction_insufficient_review"
    if market_return is not None and market_return >= 0.15:
        if offensive_share >= 0.35:
            return "bull_participation_aligned"
        return "bull_participation_may_be_constrained"
    return "mixed_or_range_validation"


def _period_summary(
    period: Mapping[str, object],
    replay_rows: Sequence[Mapping[str, object]],
    period_attribution: Mapping[str, object],
) -> dict[str, object]:
    start = str(period["start"])
    end = str(period["end"])
    period_rows = [row for row in replay_rows if start <= str(row.get("date") or "") <= end]
    market_return = _period_market_return(period_attribution, str(period["id"]))
    summary = {
        "period": period.get("id"),
        "label": period.get("label"),
        "window": {"start": start, "end": end},
        "signal_count": len(period_rows),
        "market_return": market_return,
        "policy_state_distribution": _distribution(row.get("policy_state") for row in period_rows),
        "risk_posture_distribution": _distribution(row.get("risk_posture") for row in period_rows),
        "max_offensive_budget_distribution": _distribution(
            _section(row, "risk_constraints").get("max_offensive_beta_budget") for row in period_rows
        ),
        "defensive_floor_distribution": _distribution(
            _section(row, "risk_constraints").get("min_defensive_beta_budget") for row in period_rows
        ),
        "contradiction_count": sum(len(row.get("contradictions") or []) for row in period_rows),
        "interpretation": _period_interpretation(market_return, period_rows),
    }
    summary["review_items"] = _period_review_items(summary)
    return summary


def _period_review_items(period_summary: Mapping[str, object]) -> list[dict[str, object]]:
    interpretation = str(period_summary.get("interpretation") or "")
    if interpretation not in {"risk_reduction_insufficient_review", "bull_participation_may_be_constrained"}:
        return []
    review_type = (
        "bear_or_downturn_budget_not_defensive_enough"
        if interpretation == "risk_reduction_insufficient_review"
        else "bull_or_structural_uptrend_budget_may_be_too_constrained"
    )
    return [
        {
            "period": period_summary.get("period"),
            "type": review_type,
            "severity": "review",
            "market_return": period_summary.get("market_return"),
            "risk_posture_distribution": period_summary.get("risk_posture_distribution"),
            "max_offensive_budget_distribution": period_summary.get("max_offensive_budget_distribution"),
            "note": "This is a soft validation review item, not an automatic rule change.",
        }
    ]


def _build_replay_rows(
    signals: Sequence[Mapping[str, object]],
    equity_curve: Sequence[Mapping[str, object]],
    context_rows: Sequence[Mapping[str, object]],
    style_incremental: Mapping[str, object],
    start_date: str,
    end_date: str,
) -> list[dict[str, object]]:
    filtered_signals = [
        signal
        for signal in signals
        if start_date <= str(signal.get("date") or signal.get("as_of") or "") <= end_date
    ]
    rows = []
    for index, signal in enumerate(filtered_signals):
        signal_date = str(signal.get("date") or signal.get("as_of") or "")
        next_date = (
            str(filtered_signals[index + 1].get("date") or filtered_signals[index + 1].get("as_of") or "")
            if index + 1 < len(filtered_signals)
            else None
        )
        context_row = _latest_context(context_rows, signal_date)
        inputs = _historical_inputs(signal, context_row, style_incremental)
        result = build_style_constraints(inputs)
        policy = {
            "policy_state": result.get("policy_state"),
            "allocation_environment": result.get("allocation_environment"),
            "risk_constraints": result.get("risk_constraints"),
            "rule_trace": result.get("rule_trace"),
        }
        forward_market_return = _market_return_between(equity_curve, signal_date, next_date)
        row = {
            "date": signal_date,
            "next_signal_date": next_date,
            "policy_state": result.get("policy_state"),
            "risk_posture": _risk_posture(policy),
            "allocation_environment": result.get("allocation_environment"),
            "risk_constraints": result.get("risk_constraints"),
            "dominant_style": _section(inputs, "style_preference").get("dominant_style"),
            "controls": _controls_from_policy(policy),
            "rule_trace": result.get("rule_trace"),
            "forward_market_return": forward_market_return,
            "data_quality": {
                "context_date": (context_row or {}).get("date"),
                "context_future_safe": (context_row or {}).get("future_safe"),
                "structural_features_available": _section(context_row or {}, "data_quality").get(
                    "structural_features_available"
                ),
                "missing_fields": _section(context_row or {}, "data_quality").get("missing_fields") or [],
            },
        }
        row["contradictions"] = _signal_contradictions(row)
        rows.append(row)
    return rows


def build_policy_historical_validation(
    data_dir: str | Path = DATA_DIR,
    start_date: str = DEFAULT_START_DATE,
    end_date: str = DEFAULT_END_DATE,
) -> dict[str, object]:
    root = Path(data_dir)
    v2_backtest = _read_json(root / "v2_full_cycle_backtest.json")
    context_payload = _read_json(root / "historical_style_context.json")
    incremental_payload = _read_json(root / "style_incremental_analysis.json")
    if not isinstance(v2_backtest, Mapping):
        v2_backtest = {}
    if not isinstance(context_payload, Mapping):
        context_payload = {}
    if not isinstance(incremental_payload, Mapping):
        incremental_payload = {}

    signals_container = _section(v2_backtest, "signals")
    signals = signals_container.get("v2_structural_refined") or []
    if not isinstance(signals, list):
        signals = []
    equity_curve = v2_backtest.get("equity_curve") or []
    if not isinstance(equity_curve, list):
        equity_curve = []
    period_attribution = _section(v2_backtest, "period_attribution")
    style_incremental = _style_incremental_edge(incremental_payload)
    context_rows = _context_rows(context_payload)

    replay_rows = _build_replay_rows(
        [signal for signal in signals if isinstance(signal, Mapping)],
        [row for row in equity_curve if isinstance(row, Mapping)],
        context_rows,
        style_incremental,
        start_date,
        end_date,
    )
    contradictions = [item for row in replay_rows for item in row.get("contradictions", [])]
    missing_context_count = sum(1 for row in replay_rows if row["data_quality"].get("context_date") is None)
    complete_context_count = sum(1 for row in replay_rows if row["data_quality"].get("structural_features_available") is True)

    period_validation = [
        _period_summary(period, replay_rows, period_attribution)
        for period in DEFAULT_PERIODS
    ]
    review_items = [item for period in period_validation for item in period.get("review_items", [])]
    summary = {
        "start": start_date,
        "end": end_date,
        "replay_count": len(replay_rows),
        "policy_state_distribution": _distribution(row.get("policy_state") for row in replay_rows),
        "risk_posture_distribution": _distribution(row.get("risk_posture") for row in replay_rows),
        "offensive_budget_distribution": _distribution(
            _section(row, "risk_constraints").get("max_offensive_beta_budget") for row in replay_rows
        ),
        "defensive_floor_distribution": _distribution(
            _section(row, "risk_constraints").get("min_defensive_beta_budget") for row in replay_rows
        ),
        "contradiction_count": len(contradictions),
        "review_item_count": len(review_items),
        "context_coverage": {
            "context_rows": len(context_rows),
            "missing_context_count": missing_context_count,
            "complete_structural_context_count": complete_context_count,
            "complete_structural_context_share": _share(complete_context_count, len(replay_rows)),
        },
        "key_read": _key_read(replay_rows, contradictions, review_items),
    }
    return {
        "metadata": {
            "engine": "V4.2 Risk Budget Historical Validation",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "window": {"start": start_date, "end": end_date},
            "fixed_policy_engine": "V4.1 Allocation Policy Foundation",
            "purpose": "Replay fixed V4.1 qualitative beta risk-budget rules on historical states and audit contradictions.",
            "validation_only": True,
        },
        "source_artifacts": {
            "signals": "data/v2_full_cycle_backtest.json:signals.v2_structural_refined",
            "market_returns": "data/v2_full_cycle_backtest.json:equity_curve and period_attribution",
            "historical_context": "data/historical_style_context.json",
            "style_incremental_guardrail": "data/style_incremental_analysis.json",
        },
        "summary": summary,
        "period_validation": period_validation,
        "policy_contradiction_audit": {
            "contradiction_count": len(contradictions),
            "contradictions": contradictions[:80],
            "truncated": len(contradictions) > 80,
            "review_item_count": len(review_items),
            "review_items": review_items,
            "checks": [
                "high offensive budget before negative forward validation window",
                "over-defensive budget before positive forward validation window",
                "weak structure with high offensive budget",
                "theme risk without crowding control",
                "high theme risk without defensive floor",
            ],
        },
        "historical_replay": replay_rows,
        "data_quality": {
            "uses_existing_historical_signals": True,
            "uses_future_returns_only_for_validation_labels": True,
            "policy_signal_uses_same_day_or_prior_context": True,
            "context_coverage": summary["context_coverage"],
            "known_limitations": [
                "Historical style context before structural hazard coverage can miss trend/breadth/liquidity fields.",
                "Market return is used only to audit policy contradictions after signal generation.",
                "The V4.1 policy rules are replayed as-is; this artifact does not tune thresholds.",
            ],
        },
        "constraints": {
            "fixed_v4_1_policy_rules": True,
            "no_policy_rule_change": True,
            "no_threshold_tuning": True,
            "no_etf_code": True,
            "no_asset_weight": True,
            "no_portfolio_weight": True,
            "no_position_sizing": True,
            "no_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
            "historical_validation_only": True,
            "not_a_return_optimization_backtest": True,
        },
    }


def _key_read(
    replay_rows: Sequence[Mapping[str, object]],
    contradictions: Sequence[Mapping[str, object]],
    review_items: Sequence[Mapping[str, object]],
) -> str:
    if not replay_rows:
        return "No historical replay rows are available."
    posture = Counter(str(row.get("risk_posture") or "unknown") for row in replay_rows)
    dominant_posture, dominant_count = posture.most_common(1)[0]
    contradiction_rate = len(contradictions) / len(replay_rows)
    if contradiction_rate >= 0.2:
        review = "the contradiction rate is high enough to require rule review before allocation use"
    elif contradiction_rate > 0:
        review = "contradictions exist and should be treated as review samples, not automatic fixes"
    elif review_items:
        review = f"no hard contradictions were found, but {len(review_items)} soft review items need human evaluation"
    else:
        review = "no major contradictions were found under the current audit checks"
    return (
        f"Replay produced {len(replay_rows)} policy states; dominant posture is {dominant_posture} "
        f"({dominant_count}/{len(replay_rows)}). {review}."
    )


def write_policy_historical_validation(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
