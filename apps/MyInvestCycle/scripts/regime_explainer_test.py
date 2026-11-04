from __future__ import annotations

import json

from _regime_validation_common import load_live_context, load_sample_context, run_context
from engine.regime_explainer import explain_regime


def main() -> None:
    sample_payload = run_context(load_sample_context())
    live_payload = run_context(load_live_context(history_sample_size=5))
    sample_explanation = explain_regime(sample_payload)
    live_explanation = explain_regime(live_payload)

    for explanation in (sample_explanation, live_explanation):
        assert explanation["regime"]
        assert explanation["primary_drivers"]
        assert set(explanation["sub_scores"]) == {"trend", "breadth", "liquidity", "volatility"}
        assert explanation == explain_regime(
            {
                "regime": explanation["regime"],
                "sub_scores": explanation["sub_scores"],
            }
        )

    print(
        json.dumps(
            {
                "sample": sample_explanation,
                "live": live_explanation,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
