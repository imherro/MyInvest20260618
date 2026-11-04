from __future__ import annotations

from typing import Mapping

from core.macro_cycle_layer import build_macro_cycle_decision
from core.macro_style_etf_allocator import build_macro_style_etf_allocation
from core.style_allocation_engine import build_style_allocation


def build_hierarchical_portfolio(signal: Mapping[str, object]) -> dict[str, object]:
    """Build Macro -> Style -> ETF allocation without cross-layer leakage."""

    macro = build_macro_cycle_decision(signal)
    style = build_style_allocation(signal, macro)
    etf = build_macro_style_etf_allocation(
        style["style_allocation"],
        target_exposure=float(macro["target_exposure"]),
    )

    return {
        "engine": "Hierarchical Portfolio Engine M2.1",
        "as_of": signal.get("as_of"),
        "macro_regime": macro["macro_regime"],
        "exposure_ceiling": macro["exposure_ceiling"],
        "target_exposure": macro["target_exposure"],
        "risk_overlay": macro["risk_overlay"],
        "style_allocation": style["style_allocation"],
        "etf_allocation": etf["etf_allocation"],
        "layers": {
            "macro": macro,
            "style": style,
            "etf": etf,
        },
        "constraints": {
            "macro_only_controls_exposure": True,
            "style_only_controls_weights": True,
            "etf_only_implements_mapping": True,
            "no_lookahead_bias": True,
            "simulation_only": True,
            "no_stock_selection": True,
            "no_trade_execution": True,
            "no_order_generation": True,
        },
        "method": {
            "macro": "Slow trend/regime/liquidity/breadth composite sets exposure ceiling and risk overlay.",
            "style": "Macro-aware style allocation tilts growth, value, small-cap, dividend, and low-vol buckets.",
            "etf": "Style buckets map to the current ETF universe; cash proxy receives residual non-equity exposure.",
        },
    }
