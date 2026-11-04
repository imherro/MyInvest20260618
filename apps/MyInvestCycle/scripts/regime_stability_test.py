from __future__ import annotations

import argparse
import json
import math

from _regime_validation_common import load_live_context, load_sample_context, perturb_context, run_context
from engine.consistency_guard import confidence_std, regime_stability, score_drift


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic regime consistency checks.")
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--history-sample-size", type=int, default=0)
    parser.add_argument("--perturb-bps", type=float, default=5.0)
    args = parser.parse_args()

    if args.runs <= 0:
        raise ValueError("--runs must be positive")

    context = (
        load_live_context(history_sample_size=args.history_sample_size)
        if args.live
        else load_sample_context()
    )

    results = [run_context(context) for _ in range(args.runs)]
    regimes = [str(result["regime"]) for result in results]
    confidences = [float(result["confidence"]) for result in results]
    scores = [float(result["regime_score"]) for result in results]

    baseline = results[0]
    perturb_results = []
    for run_index in range(args.runs):
        direction = -1 if run_index % 2 else 1
        multiplier = 1.0 + direction * args.perturb_bps / 10000.0 * (1 + math.sin(run_index))
        perturb_results.append(run_context(perturb_context(context, multiplier)))

    output = {
        "runs": args.runs,
        "baseline_regime": baseline["regime"],
        "regime_stability": regime_stability(regimes),
        "confidence_std": confidence_std(confidences),
        "score_drift": score_drift(scores),
        "deterministic": len(set(regimes)) == 1 and score_drift(scores) == 0.0,
        "robustness_regime_changes": sum(
            1 for result in perturb_results if result["regime"] != baseline["regime"]
        ),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
