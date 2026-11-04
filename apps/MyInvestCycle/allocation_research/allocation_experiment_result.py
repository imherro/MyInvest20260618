from __future__ import annotations


def build_allocation_experiment_result_schema() -> dict[str, object]:
    return {
        "schema_version": "V9.5",
        "purpose": "Execute predeclared experiment templates as Phase 0 research discipline checks without producing investable outputs.",
        "allowed_input": {
            "field": "allocation_experiment_templates",
            "source": "V9.4 Allocation Research Experiment Template Framework",
            "description": "Use only predeclared template fields; do not read market data to search rules or optimize outcomes.",
        },
        "result_fields": [
            "experiment_id",
            "execution_status",
            "validation_result",
            "out_of_sample_status",
            "drawdown_audit_status",
            "contradiction_audit_status",
            "regime_stability_status",
            "time_safety_status",
            "promotion_status",
            "investable_output",
        ],
        "allowed_validation_results": [
            "design_pass_market_not_evaluated",
            "design_fail",
        ],
        "required_execution_status": "completed",
        "required_promotion_status": "not_promoted",
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
            "backtest_result",
            "optimization",
        ],
    }
