from __future__ import annotations


def build_allocation_research_schema() -> dict[str, object]:
    return {
        "schema_version": "V9.1",
        "purpose": "Define the future allocation research boundary without producing allocation outputs.",
        "allowed_inputs": [
            {
                "field": "risk_context",
                "source": "Frozen V6 risk architecture",
                "description": "Risk gradient, protection pressure, and two-axis context are allowed as explanatory inputs.",
            },
            {
                "field": "opportunity_research_status",
                "source": "Frozen V7 opportunity research",
                "description": "Feature attribution status is allowed only as research readiness evidence.",
            },
            {
                "field": "research_decision_context",
                "source": "Frozen V8 research interpretation",
                "description": "Research context and contradiction attribution are allowed as interpretation evidence.",
            },
        ],
        "required_future_evidence": [
            "allocation hypothesis definition",
            "predefined non-optimized allocation candidates",
            "out-of-sample validation plan",
            "drawdown and contradiction audit",
            "research-only reporting boundary",
        ],
        "forbidden_outputs": [
            "portfolio_weight",
            "asset_selection",
            "etf_mapping",
            "top_n",
            "trade_signal",
            "rebalance_instruction",
            "broker_order",
            "backtest_optimization",
        ],
    }
