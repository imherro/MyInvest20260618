from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from config import DATA_DIR
from implementation_readiness.evidence_package_validator import FORBIDDEN_OUTPUT_KEYS


BASE_COMMIT = "58b5ab83398b0f6ed2adf5b4027f782fbd4b5303"
DEFAULT_OUTPUT_PATH = DATA_DIR / "v15_strategy_direction_rebase.json"


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


def validate_v15_strategy_direction_rebase(payload: Mapping[str, object]) -> dict[str, object]:
    metadata = _mapping(payload.get("metadata"))
    summary = _mapping(payload.get("summary"))
    frozen = _mapping(_mapping(payload.get("frozen_tracks")).get("v12_v14_governance_shadow"))
    hypotheses = _mapping(payload.get("new_strategy_hypotheses"))
    requirements = _mapping(payload.get("future_backtest_requirements"))
    constraints = _mapping(payload.get("constraints"))

    if metadata.get("engine") != "V15.0 Mainline Outcome-Oriented Strategy Rebase":
        raise AssertionError("unexpected engine")
    if metadata.get("base_commit") != BASE_COMMIT:
        raise AssertionError("base commit must reference the latest passed V14.9 commit")
    if summary.get("phase") != "V15":
        raise AssertionError("phase must be V15")
    if summary.get("mainline_direction") != "outcome_oriented_strategy_rebase":
        raise AssertionError("mainline direction mismatch")
    if summary.get("direction_status") != "rebase_declared":
        raise AssertionError("direction status must be rebase_declared")
    if summary.get("primary_objective") != "maximize_return_and_alpha":
        raise AssertionError("primary objective must be return and alpha")
    if summary.get("secondary_objective") != "control_max_drawdown":
        raise AssertionError("secondary objective must control max drawdown")
    if summary.get("must_backtest_before_strategy_claim") is not True:
        raise AssertionError("must require backtest before strategy claim")
    for key in ("production_trade_enabled", "broker_connection_enabled", "real_order_generation_enabled"):
        if summary.get(key) is not False:
            raise AssertionError(f"summary.{key} must be false")

    if frozen.get("status") != "frozen_as_infrastructure":
        raise AssertionError("V12-V14 must be frozen as infrastructure")
    for key in ("not_main_alpha_strategy", "not_portfolio_engine", "not_trade_engine"):
        if frozen.get(key) is not True:
            raise AssertionError(f"frozen_tracks.v12_v14_governance_shadow.{key} must be true")

    required_hypotheses = {"macro_cycle", "drawdown_context", "structural_bull", "mainline_rotation"}
    if set(hypotheses.keys()) != required_hypotheses:
        raise AssertionError("strategy hypotheses mismatch")
    for key in required_hypotheses:
        if _mapping(hypotheses.get(key)).get("must_backtest") is not True:
            raise AssertionError(f"{key} must require backtest")

    required_metrics = set(_sequence(requirements.get("required_metrics")))
    for metric in ("CAGR", "annual_alpha", "max_drawdown", "calmar", "sharpe", "turnover"):
        if metric not in required_metrics:
            raise AssertionError(f"future backtest metric missing: {metric}")

    required_constraints = [
        "direction_rebase_only",
        "does_not_run_backtest",
        "does_not_generate_position",
        "does_not_generate_etf_mapping",
        "does_not_generate_portfolio_weight",
        "does_not_generate_allocation",
        "does_not_generate_trade_signal",
        "does_not_create_order",
        "does_not_connect_broker",
    ]
    for key in required_constraints:
        if constraints.get(key) is not True:
            raise AssertionError(f"constraints.{key} must be true")
    if constraints.get("production_trade_enabled") is not False:
        raise AssertionError("constraints.production_trade_enabled must be false")

    disallowed_payload_keys = FORBIDDEN_OUTPUT_KEYS.intersection(
        key for key in _walk_keys(payload) if key != "forbidden_outputs"
    )
    if disallowed_payload_keys:
        raise AssertionError(f"forbidden output keys found: {sorted(disallowed_payload_keys)}")

    return {
        "audit_status": "passed",
        "checked_direction_rebase_only": True,
        "checked_v12_v14_frozen": True,
        "checked_primary_objective": summary.get("primary_objective"),
        "checked_secondary_objective": summary.get("secondary_objective"),
        "checked_trade_enabled": summary.get("production_trade_enabled"),
        "checked_broker_connection_enabled": summary.get("broker_connection_enabled"),
        "checked_real_order_generation_enabled": summary.get("real_order_generation_enabled"),
        "checked_constraints": required_constraints,
        "checked_forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }


def build_v15_strategy_direction_rebase() -> dict[str, object]:
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    as_of = datetime.now(timezone.utc).strftime("%Y%m%d")
    payload: dict[str, object] = {
        "metadata": {
            "engine": "V15.0 Mainline Outcome-Oriented Strategy Rebase",
            "generated_at": generated_at,
            "as_of": as_of,
            "base_commit": BASE_COMMIT,
            "purpose": "Freeze V12-V14 as governance/evidence/shadow infrastructure and redirect mainline development toward outcome-oriented strategy backtesting.",
        },
        "summary": {
            "phase": "V15",
            "mainline_direction": "outcome_oriented_strategy_rebase",
            "direction_status": "rebase_declared",
            "primary_objective": "maximize_return_and_alpha",
            "secondary_objective": "control_max_drawdown",
            "tertiary_objective": "improve_explainability",
            "must_backtest_before_strategy_claim": True,
            "production_trade_enabled": False,
            "broker_connection_enabled": False,
            "real_order_generation_enabled": False,
            "conclusion": "v15_mainline_rebased_to_return_first_strategy_development",
        },
        "frozen_tracks": {
            "v12_v14_governance_shadow": {
                "status": "frozen_as_infrastructure",
                "not_main_alpha_strategy": True,
                "not_portfolio_engine": True,
                "not_trade_engine": True,
                "allowed_future_use": [
                    "research_governance",
                    "implementation_readiness_checks",
                    "evidence_audit",
                    "shadow_observation_recording",
                ],
                "disallowed_future_use": [
                    "main_alpha_claim",
                    "portfolio_allocation_driver",
                    "automatic_trade_signal",
                    "production_risk_control_without_backtest",
                ],
            }
        },
        "reason_for_rebase": {
            "old_strategy_issue_summary": [
                "Prior risk/diagnostic visualizations did not provide enough market guidance.",
                "Prior alpha result was unacceptable and must not be treated as successful.",
                "Governance infrastructure expanded faster than outcome-oriented strategy validation.",
                "The system must refocus on return, drawdown, and robust backtest evidence.",
            ],
            "user_original_goal_restated": "Build an A-share strategy system that improves return and controls drawdown, with practical guidance for market regime, drawdown opportunities, and structural bull markets.",
        },
        "new_strategy_hypotheses": {
            "macro_cycle": {
                "hypothesis": "Long-term macro and valuation regime determines whether equity risk should be embraced or reduced.",
                "must_backtest": True,
            },
            "drawdown_context": {
                "hypothesis": "Large drawdowns during early/mid bull markets may be add-position opportunities, while high-level drawdowns near late-cycle tops may be de-risking signals.",
                "must_backtest": True,
            },
            "structural_bull": {
                "hypothesis": "A-shares may enter structural bull markets where broad indices stagnate but leading sectors/themes rotate upward.",
                "must_backtest": True,
            },
            "mainline_rotation": {
                "hypothesis": "Sector/theme strength, breadth, concentration, and persistence should be tested as allocation signals.",
                "must_backtest": True,
            },
        },
        "v15_roadmap": {
            "v15_0": "mainline outcome-oriented strategy rebase",
            "v15_1": "backtest dataset builder",
            "v15_2": "macro plus drawdown regime strategy backtest",
            "v15_3": "structural bull rotation strategy backtest",
            "v15_4": "strategy comparison and kill criteria",
        },
        "future_backtest_requirements": {
            "required_benchmarks": [
                "deposit_or_cash_baseline",
                "broad_index_baseline",
                "old_strategy_baseline",
                "macro_drawdown_strategy",
                "macro_drawdown_structural_bull_strategy",
            ],
            "required_metrics": [
                "CAGR",
                "annual_return",
                "annual_alpha",
                "max_drawdown",
                "calmar",
                "sharpe",
                "win_rate",
                "turnover",
                "longest_drawdown_recovery",
                "yearly_returns",
                "regime_segment_returns",
            ],
            "required_market_segments": [
                "2015_bubble_and_crash",
                "2018_bear_market",
                "2020_recovery",
                "2021_structural_market",
                "2022_bear_market",
                "2024_2026_recent_market",
            ],
        },
        "constraints": {
            "direction_rebase_only": True,
            "does_not_run_backtest": True,
            "does_not_generate_position": True,
            "does_not_generate_etf_mapping": True,
            "does_not_generate_portfolio_weight": True,
            "does_not_generate_allocation": True,
            "does_not_generate_trade_signal": True,
            "does_not_create_order": True,
            "does_not_connect_broker": True,
            "production_trade_enabled": False,
        },
        "forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }
    payload["audit"] = validate_v15_strategy_direction_rebase(payload)
    return payload


def write_v15_strategy_direction_rebase(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
