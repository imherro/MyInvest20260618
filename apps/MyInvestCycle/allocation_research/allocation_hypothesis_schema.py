from __future__ import annotations


def build_allocation_hypothesis_schema() -> dict[str, object]:
    return {
        "schema_version": "V9.2",
        "purpose": "Define unvalidated allocation research hypotheses without producing investable outputs.",
        "allowed_input": {
            "field": "allocation_research_architecture",
            "source": "V9.1 Allocation Research Architecture Foundation",
            "description": "Use only V9.1 boundary, frozen V6/V7/V8 source evidence, readiness flags, and forbidden outputs.",
        },
        "hypothesis_fields": [
            "id",
            "name",
            "research_question",
            "hypothesis",
            "source_context",
            "required_validation",
            "invalidation_conditions",
            "status",
            "forbidden_interpretation",
        ],
        "required_status": "unvalidated",
        "required_validation": [
            "out_of_sample_test",
            "drawdown_audit",
            "contradiction_audit",
            "time_safety_audit",
            "research_only_report",
        ],
        "forbidden_outputs": [
            "portfolio_weight",
            "asset_selection",
            "etf_mapping",
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
