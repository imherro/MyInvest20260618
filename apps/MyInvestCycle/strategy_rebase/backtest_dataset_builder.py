from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from config import DATA_DIR
from implementation_readiness.evidence_package_validator import FORBIDDEN_OUTPUT_KEYS


V15_0_COMMIT = "94499052273969bd4b122253afe4eef5276f9cf2"
DEFAULT_DIRECTION_REBASE_PATH = DATA_DIR / "v15_strategy_direction_rebase.json"
DEFAULT_OUTPUT_PATH = DATA_DIR / "v15_backtest_dataset_manifest.json"


def _read_json(path: str | Path) -> dict[str, object]:
    target = Path(path)
    if not target.exists():
        return {}
    payload = json.loads(target.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else []


def _walk_keys(value: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            keys.append(str(key))
            keys.extend(_walk_keys(item))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            keys.extend(_walk_keys(item))
    return keys


def _field(name: str, purpose: str, frequency: str = "daily", source: str = "tushare_or_local_cache") -> dict[str, str]:
    return {
        "name": name,
        "purpose": purpose,
        "frequency": frequency,
        "preferred_source": source,
    }


def validate_v15_backtest_dataset_manifest(payload: Mapping[str, object]) -> dict[str, object]:
    metadata = _mapping(payload.get("metadata"))
    summary = _mapping(payload.get("summary"))
    dataset_groups = _mapping(payload.get("dataset_groups"))
    targets = _mapping(payload.get("future_backtest_targets"))
    quality = _mapping(payload.get("data_quality_requirements"))
    constraints = _mapping(payload.get("constraints"))

    if metadata.get("engine") != "V15.1 Outcome-Oriented Backtest Dataset Builder":
        raise AssertionError("unexpected engine")
    if metadata.get("v15_0_commit") != V15_0_COMMIT:
        raise AssertionError("V15.1 must reference the passed V15.0 commit")
    if payload.get("phase") != "V15.1" or summary.get("phase") != "V15.1":
        raise AssertionError("phase must be V15.1")
    if payload.get("dataset_status") != "manifest_ready" or summary.get("dataset_status") != "manifest_ready":
        raise AssertionError("dataset status must be manifest_ready")
    for key in ("does_not_run_strategy", "does_not_generate_position", "does_not_generate_trade_signal"):
        if payload.get(key) is not True or summary.get(key) is not True:
            raise AssertionError(f"{key} must be true")
    if payload.get("no_backtest_result") is not True or summary.get("no_backtest_result") is not True:
        raise AssertionError("no_backtest_result must be true")
    if payload.get("production_trade_enabled") is not False:
        raise AssertionError("top-level production trading must be disabled")
    for key in ("production_trade_enabled", "broker_connection_enabled", "real_order_generation_enabled"):
        if summary.get(key) is not False:
            raise AssertionError(f"summary.{key} must be false")

    required_groups = {"broad_indices", "sector_indices", "macro_cycle", "drawdown_context", "structural_bull"}
    if set(dataset_groups.keys()) != required_groups:
        raise AssertionError("dataset groups mismatch")
    for key in required_groups:
        group = _mapping(dataset_groups.get(key))
        fields = _sequence(group.get("fields"))
        if not fields:
            raise AssertionError(f"{key} must define fields")
        if group.get("dataset_group_status") != "manifest_defined":
            raise AssertionError(f"{key} must be manifest_defined")

    for key in ("macro_drawdown_strategy", "structural_bull_rotation_strategy", "old_strategy_baseline"):
        if targets.get(key) is not True:
            raise AssertionError(f"future backtest target missing: {key}")

    for key in (
        "point_in_time_required",
        "release_date_safe_required",
        "survivorship_bias_check_required",
        "cache_consistency_check_required",
    ):
        if quality.get(key) is not True:
            raise AssertionError(f"data_quality_requirements.{key} must be true")

    required_constraints = [
        "dataset_builder_only",
        "does_not_fetch_full_dataset",
        "does_not_run_strategy",
        "no_backtest_result",
        "does_not_generate_position",
        "does_not_generate_fund_mapping",
        "does_not_generate_portfolio_weight",
        "no_allocation",
        "does_not_generate_trade_signal",
        "no_trade",
        "no_broker_connection",
    ]
    for key in required_constraints:
        if constraints.get(key) is not True:
            raise AssertionError(f"constraints.{key} must be true")
    if constraints.get("production_trade_enabled") is not False:
        raise AssertionError("production trading must be disabled")

    disallowed_payload_keys = FORBIDDEN_OUTPUT_KEYS.intersection(
        key for key in _walk_keys(payload) if key != "forbidden_outputs"
    )
    if disallowed_payload_keys:
        raise AssertionError(f"forbidden output keys found: {sorted(disallowed_payload_keys)}")

    return {
        "audit_status": "passed",
        "checked_phase": payload.get("phase"),
        "checked_dataset_status": payload.get("dataset_status"),
        "checked_dataset_group_count": len(dataset_groups),
        "checked_future_targets": sorted(targets.keys()),
        "checked_no_strategy": payload.get("does_not_run_strategy"),
        "checked_no_position": payload.get("does_not_generate_position"),
        "checked_no_trade_signal": payload.get("does_not_generate_trade_signal"),
        "checked_trade_enabled": summary.get("production_trade_enabled"),
        "checked_constraints": required_constraints,
        "checked_forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }


def build_v15_backtest_dataset_manifest(
    *,
    direction_rebase_path: str | Path = DEFAULT_DIRECTION_REBASE_PATH,
) -> dict[str, object]:
    direction = _read_json(direction_rebase_path)
    direction_summary = _mapping(direction.get("summary"))
    if direction_summary.get("mainline_direction") != "outcome_oriented_strategy_rebase":
        raise RuntimeError("V15.1 requires V15.0 direction rebase artifact first.")
    if direction_summary.get("production_trade_enabled") is not False:
        raise RuntimeError("V15.0 production trade boundary must remain disabled.")

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    as_of = datetime.now(timezone.utc).strftime("%Y%m%d")
    payload: dict[str, object] = {
        "metadata": {
            "engine": "V15.1 Outcome-Oriented Backtest Dataset Builder",
            "generated_at": generated_at,
            "as_of": as_of,
            "v15_0_commit": V15_0_COMMIT,
            "source_direction_artifact": "data/v15_strategy_direction_rebase.json",
            "purpose": "Define the point-in-time data manifest required for V15+ outcome-oriented backtests without fetching full datasets or running strategies.",
        },
        "phase": "V15.1",
        "dataset_status": "manifest_ready",
        "does_not_run_strategy": True,
        "does_not_generate_position": True,
        "does_not_generate_trade_signal": True,
        "no_backtest_result": True,
        "production_trade_enabled": False,
        "summary": {
            "phase": "V15.1",
            "dataset_status": "manifest_ready",
            "mainline_direction": direction_summary.get("mainline_direction"),
            "primary_objective": direction_summary.get("primary_objective"),
            "secondary_objective": direction_summary.get("secondary_objective"),
            "does_not_run_strategy": True,
            "does_not_generate_position": True,
            "does_not_generate_trade_signal": True,
            "no_backtest_result": True,
            "production_trade_enabled": False,
            "broker_connection_enabled": False,
            "real_order_generation_enabled": False,
            "next_task": "V15.2 macro plus drawdown regime strategy backtest",
            "conclusion": "v15_1_backtest_dataset_manifest_ready_no_strategy_no_trade",
        },
        "dataset_groups": {
            "broad_indices": {
                "dataset_group_status": "manifest_defined",
                "purpose": "Build broad-market baselines and long-cycle drawdown context.",
                "required_instruments": [
                    "shanghai_composite",
                    "csi_300",
                    "csi_500",
                    "csi_1000",
                    "chinext_index",
                    "star_50",
                    "csi_all_share",
                ],
                "fields": [
                    _field("trade_date", "point-in-time trading date"),
                    _field("close", "close level for return and drawdown calculations"),
                    _field("total_return_close", "dividend-adjusted benchmark level when available"),
                    _field("turnover_amount", "market liquidity and activity proxy"),
                    _field("moving_average_distance", "distance to long trend anchors"),
                    _field("valuation_percentile", "late-cycle high-level risk context", frequency="weekly_or_monthly"),
                ],
            },
            "sector_indices": {
                "dataset_group_status": "manifest_defined",
                "purpose": "Measure sector/theme strength and structural bull rotation breadth.",
                "required_universe": [
                    "sw_first_level_industries",
                    "major_sector_indices",
                    "theme_fund_proxy_universe",
                    "strong_mainline_candidate_pool",
                ],
                "fields": [
                    _field("trade_date", "point-in-time trading date"),
                    _field("sector_name", "sector or theme label"),
                    _field("close", "sector index close level"),
                    _field("relative_strength", "sector strength versus broad baseline"),
                    _field("momentum_20d", "short-cycle mainline persistence"),
                    _field("momentum_60d", "medium-cycle mainline persistence"),
                    _field("breadth_score", "participation within sector/theme proxy"),
                    _field("turnover_share", "activity concentration proxy"),
                ],
            },
            "macro_cycle": {
                "dataset_group_status": "manifest_defined",
                "purpose": "Classify long-term macro and valuation context before interpreting drawdowns.",
                "fields": [
                    _field("release_date", "macro release date for point-in-time safety", frequency="monthly"),
                    _field("effective_date", "date from which the macro value is usable", frequency="monthly"),
                    _field("m1", "money supply growth proxy", frequency="monthly"),
                    _field("m2", "broad liquidity proxy", frequency="monthly"),
                    _field("social_financing", "credit impulse proxy", frequency="monthly"),
                    _field("pmi", "economic activity proxy", frequency="monthly"),
                    _field("interest_rate", "discount-rate context", frequency="daily_or_monthly"),
                    _field("credit_cycle_bucket", "derived long-cycle credit state", frequency="monthly"),
                    _field("equity_bond_value_spread", "stock-bond relative value proxy", frequency="daily_or_weekly"),
                ],
            },
            "drawdown_context": {
                "dataset_group_status": "manifest_defined",
                "purpose": "Distinguish bull-market pullbacks from late-cycle or bear-market risk.",
                "fields": [
                    _field("trade_date", "point-in-time trading date"),
                    _field("drawdown_20d", "short pullback depth"),
                    _field("drawdown_60d", "medium pullback depth"),
                    _field("drawdown_120d", "cycle pullback depth"),
                    _field("rolling_max_drawdown", "largest drawdown from trailing peak"),
                    _field("realized_volatility", "volatility pressure"),
                    _field("trend_distance", "distance from moving-average trend anchor"),
                    _field("market_breadth", "market participation"),
                    _field("turnover_change", "liquidity stress or recovery"),
                ],
            },
            "structural_bull": {
                "dataset_group_status": "manifest_defined",
                "purpose": "Detect broad-index stagnation with strong sector/theme mainlines.",
                "fields": [
                    _field("trade_date", "point-in-time trading date"),
                    _field("sector_strength_distribution", "cross-sectional sector strength"),
                    _field("sector_dispersion", "industry return dispersion"),
                    _field("mainline_concentration", "activity and return concentration among leaders"),
                    _field("mainline_persistence", "duration of leading sector strength"),
                    _field("rising_sector_ratio", "percentage of sectors in uptrend"),
                    _field("leader_diffusion", "whether leaders broaden beyond first movers"),
                    _field("broad_vs_sector_divergence", "broad-index weakness versus sector strength"),
                ],
            },
        },
        "future_backtest_targets": {
            "macro_drawdown_strategy": True,
            "structural_bull_rotation_strategy": True,
            "old_strategy_baseline": True,
        },
        "data_quality_requirements": {
            "point_in_time_required": True,
            "release_date_safe_required": True,
            "survivorship_bias_check_required": True,
            "cache_consistency_check_required": True,
            "minimum_start_date": "20150101",
            "preferred_latest_complete_trading_day": "latest_a_share_complete_trading_day",
            "source_priority": [
                "local_verified_cache",
                "tushare_structured_data",
                "documented_manual_cache_with_explicit_gap_disclosure",
            ],
        },
        "time_safety": {
            "manifest_only": True,
            "does_not_fetch_full_dataset": True,
            "does_not_use_future_data": True,
            "requires_release_date_alignment": True,
            "requires_t_plus_one_execution_assumption_for_future_backtests": True,
        },
        "constraints": {
            "dataset_builder_only": True,
            "does_not_fetch_full_dataset": True,
            "does_not_run_strategy": True,
            "no_backtest_result": True,
            "does_not_generate_position": True,
            "does_not_generate_fund_mapping": True,
            "does_not_generate_portfolio_weight": True,
            "no_allocation": True,
            "does_not_generate_trade_signal": True,
            "no_trade": True,
            "no_broker_connection": True,
            "production_trade_enabled": False,
        },
        "forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }
    payload["audit"] = validate_v15_backtest_dataset_manifest(payload)
    return payload


def write_v15_backtest_dataset_manifest(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
