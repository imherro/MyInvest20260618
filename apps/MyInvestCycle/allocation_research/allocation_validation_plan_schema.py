from __future__ import annotations


def build_allocation_validation_plan_schema() -> dict[str, object]:
    return {
        "schema_version": "V9.3",
        "purpose": "Define how to validate V9.2 allocation research hypotheses without executing validation.",
        "allowed_input": {
            "field": "allocation_research_hypotheses",
            "source": "V9.2 Allocation Research Hypothesis Framework",
            "description": "Use only hypothesis identifiers, research questions, required validation items, and unvalidated status.",
        },
        "plan_fields": [
            "hypothesis_id",
            "validation_objective",
            "required_evidence",
            "failure_criteria",
            "anti_overfitting_rules",
            "execution_status",
            "forbidden_interpretation",
        ],
        "required_evidence": [
            "out_of_sample_test_design",
            "walk_forward_design",
            "drawdown_audit_design",
            "contradiction_audit_design",
            "regime_stability_design",
            "time_safety_audit_design",
            "research_only_report_design",
        ],
        "required_anti_overfitting_rules": [
            "no_parameter_search",
            "no_best_period_selection",
            "no_threshold_optimization",
            "no_result_based_candidate_promotion",
            "predeclare_failure_criteria",
        ],
        "required_execution_status": "planned_not_executed",
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
            "validation_result",
        ],
    }
