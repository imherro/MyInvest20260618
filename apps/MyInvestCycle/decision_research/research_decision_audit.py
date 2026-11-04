from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


FORBIDDEN_TOP_LEVEL_KEYS = {
    "asset",
    "asset_code",
    "asset_name",
    "etf",
    "etf_code",
    "position",
    "portfolio_weight",
    "rank",
    "top_n",
    "trade",
    "weight",
}


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


def audit_research_decision_context(payload: Mapping[str, object]) -> dict[str, object]:
    summary = payload.get("summary")
    constraints = payload.get("constraints")
    data_quality = payload.get("data_quality")
    if not isinstance(summary, Mapping):
        raise AssertionError("research decision context missing summary")
    if not isinstance(constraints, Mapping):
        raise AssertionError("research decision context missing constraints")
    if not isinstance(data_quality, Mapping):
        raise AssertionError("research decision context missing data_quality")

    required_false = [
        "ready_for_scoring",
        "ready_for_ranking",
        "ready_for_allocation",
        "ready_for_trade",
    ]
    for key in required_false:
        if summary.get(key) is not False:
            raise AssertionError(f"summary.{key} must be false")

    required_true_constraints = [
        "research_only",
        "does_not_create_opportunity_score",
        "does_not_rank_assets",
        "does_not_select_top_assets",
        "does_not_generate_position",
        "no_percentage_exposure",
        "no_etf_code",
        "no_asset_weight",
        "no_portfolio_weight",
        "no_trade_signal",
        "no_order_generation",
        "no_broker_connection",
        "no_parameter_optimization",
    ]
    for key in required_true_constraints:
        if constraints.get(key) is not True:
            raise AssertionError(f"constraints.{key} must be true")

    if data_quality.get("uses_frozen_v6_artifacts_only") is not True:
        raise AssertionError("data_quality.uses_frozen_v6_artifacts_only must be true")
    if data_quality.get("uses_frozen_v7_artifacts_only") is not True:
        raise AssertionError("data_quality.uses_frozen_v7_artifacts_only must be true")
    if data_quality.get("no_new_feature_search") is not True:
        raise AssertionError("data_quality.no_new_feature_search must be true")

    disallowed_found = sorted(FORBIDDEN_TOP_LEVEL_KEYS.intersection(_walk_keys(payload)))
    if disallowed_found:
        raise AssertionError(f"forbidden output keys found: {disallowed_found}")

    return {
        "audit_status": "passed",
        "checked_ready_flags": required_false,
        "checked_constraints": required_true_constraints,
        "forbidden_output_keys": sorted(FORBIDDEN_TOP_LEVEL_KEYS),
    }
