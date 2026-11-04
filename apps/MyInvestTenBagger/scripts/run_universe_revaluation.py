from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tenbagger.revaluation import run_universe_revaluation


def main() -> int:
    parser = argparse.ArgumentParser(description="Run TASK U2 universe re-evaluation.")
    parser.add_argument("--baseline", default="dev", choices=["dev", "research", "production"])
    parser.add_argument("--target", default="research", choices=["dev", "research", "production"])
    parser.add_argument("--report-root", default=str(ROOT / "reports"))
    parser.add_argument("--output-dir", default=str(ROOT / "reports"))
    parser.add_argument("--baseline-report-dir", default=None)
    parser.add_argument("--target-report-dir", default=None)
    args = parser.parse_args()

    result = run_universe_revaluation(
        report_root=Path(args.report_root),
        output_dir=Path(args.output_dir),
        baseline_level=args.baseline,
        target_level=args.target,
        baseline_report_dir=Path(args.baseline_report_dir) if args.baseline_report_dir else None,
        target_report_dir=Path(args.target_report_dir) if args.target_report_dir else None,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "baseline": result["baseline_level"],
                "target": result["target_level"],
                "structural_drift_score": result["structural_drift_score"],
                "structural_drift_conclusion": result["structural_drift_conclusion"],
                "rankic_mean_abs_delta": result["rankic_shift"]["mean_abs_delta"],
                "candidate_density_delta": result["candidate_density_shift"]["delta"],
                "regime_transition_delta": result["regime_stability_shift"]["transition_frequency_delta"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
