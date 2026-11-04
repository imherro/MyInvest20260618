from __future__ import annotations


def build_allocation_experiment_schema() -> dict[str, object]:
    return {
        "schema_version": "V9.4",
        "purpose": "Define predefined allocation research experiment templates without running experiments.",
        "allowed_input": {
            "field": "allocation_validation_plan",
            "source": "V9.3 Allocation Research Validation Plan Framework",
            "description": "Use only hypothesis references, validation objectives, evidence requirements, and failure criteria.",
        },
        "template_fields": [
            "hypothesis_id",
            "experiment_question",
            "predefined_comparison",
            "evaluation_criteria",
            "failure_criteria",
            "anti_overfitting_rules",
            "execution_status",
            "forbidden_interpretation",
        ],
        "allowed_comparison_labels": [
            "baseline_research_posture",
            "alternative_research_posture",
        ],
        "required_evaluation_criteria": [
            "out_of_sample_design",
            "drawdown_audit_design",
            "contradiction_audit_design",
            "regime_stability_design",
            "time_safety_design",
        ],
        "required_execution_status": "template_only_not_executed",
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
            "validation_result",
            "experiment_result",
            "optimization",
        ],
    }
