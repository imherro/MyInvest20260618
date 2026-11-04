from __future__ import annotations

import argparse
import json
from statistics import pstdev

from _regime_validation_common import load_sample_context, run_context
from engine.consistency_guard import dominant_regime, drift_level, regime_flip_count


def _windowed_sample_results(window: int) -> list[dict]:
    context = load_sample_context()
    index_df = context.index_df.tail(window + 140).reset_index(drop=True)
    results = []
    for offset in range(140, len(index_df)):
        local_context = load_sample_context()
        local_context.index_df = index_df.iloc[: offset + 1].copy()
        local_context.market_daily_df["trade_date"] = str(local_context.index_df["trade_date"].iloc[-1])
        results.append(run_context(local_context))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect regime drift over a recent window.")
    parser.add_argument("--window", type=int, default=30)
    args = parser.parse_args()

    if args.window <= 1:
        raise ValueError("--window must be greater than 1")

    results = _windowed_sample_results(args.window)
    regimes = [str(result["regime"]) for result in results]
    trend_scores = [float(result["trend_score"]) for result in results]
    breadth_scores = [float(result["breadth_score"]) for result in results]
    flip_count = regime_flip_count(regimes)
    trend_std = pstdev(trend_scores) if len(trend_scores) > 1 else 0.0
    breadth_std = pstdev(breadth_scores) if len(breadth_scores) > 1 else 0.0

    output = {
        "window": args.window,
        "drift_level": drift_level(flip_count, trend_std, breadth_std),
        "flip_count": flip_count,
        "dominant_regime": dominant_regime(regimes),
        "trend_std": round(trend_std, 4),
        "breadth_std": round(breadth_std, 4),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
