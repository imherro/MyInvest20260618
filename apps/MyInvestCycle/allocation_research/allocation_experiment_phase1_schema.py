from __future__ import annotations


def build_allocation_experiment_phase1_schema() -> dict[str, object]:
    return {
        "schema_version": "V9.6",
        "purpose": "Validate predeclared allocation research experiments with frozen research artifacts only.",
        "allowed_inputs": [
            "v6_two_axis_context_validation",
            "v7_opportunity_feature_attribution",
            "v8_research_decision_context",
            "v8_research_decision_scenario_audit",
            "v8_research_decision_contradiction",
            "v9_5_phase0_experiment_results",
        ],
        "result_fields": [
            "experiment_id",
            "validation_status",
            "out_of_sample_status",
            "drawdown_audit_status",
            "contradiction_audit_status",
            "regime_stability_status",
            "time_safety_status",
            "promotion_allowed",
            "investable_output",
        ],
        "allowed_validation_status": [
            "supported",
            "unsupported",
            "inconclusive",
        ],
        "required_hash_algorithm": "sha256",
        "forbidden_outputs": [
            "asset_selection",
            "etf_mapping",
            "portfolio_weight",
            "top_n",
            "exposure_percent",
            "buy_signal",
            "sell_signal",
            "rebalance_instruction",
            "broker_order",
            "optimization",
        ],
    }
