from __future__ import annotations


def build_validation_protocol_schema() -> dict[str, object]:
    return {
        "schema_version": "V11.1",
        "name": "External Validation Research Protocol Schema",
        "allowed_protocol_status": [
            "pre_registered",
            "paused",
            "failed_boundary_check",
        ],
        "allowed_target_status": [
            "continue_external_validation",
        ],
        "required_sections": [
            "target_hypothesis",
            "validation_scope",
            "validation_windows",
            "pre_registered_methods",
            "failure_standards",
            "stop_conditions",
            "time_safety",
            "constraints",
        ],
        "forbidden_outputs": [
            "asset_selection",
            "etf_mapping",
            "portfolio_weight",
            "allocation_output",
            "optimization_result",
            "trade_signal",
            "broker_order",
        ],
        "readiness_flags_required_false": [
            "promotion_allowed",
            "strategy_promotion",
            "allocation_ready",
            "investable_output",
            "ready_for_asset_selection",
            "ready_for_etf_mapping",
            "ready_for_weight_generation",
            "ready_for_optimization",
            "ready_for_trade",
        ],
    }
