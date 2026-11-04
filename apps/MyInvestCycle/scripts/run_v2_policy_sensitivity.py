from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backtest.exposure_sensitivity import run_exposure_sensitivity
from backtest.walk_forward_validator import build_walk_forward_coverage_audit
from config import DATA_DIR


DEFAULT_OUTPUT = DATA_DIR / "v2_policy_sensitivity.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run V2 allocation policy sensitivity validation.")
    parser.add_argument("--start", default="20240101", help="Sensitivity start date, YYYYMMDD.")
    parser.add_argument("--end", default="20991231", help="Sensitivity end date, YYYYMMDD.")
    parser.add_argument("--desired-history-start", default="20150101", help="Desired long-history validation start.")
    parser.add_argument("--rebalance-every-sessions", type=int, default=20)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sensitivity = run_exposure_sensitivity(
        start_date=args.start,
        end_date=args.end,
        rebalance_every_sessions=args.rebalance_every_sessions,
    )
    coverage = build_walk_forward_coverage_audit(
        desired_start=args.desired_history_start,
        desired_end=args.end,
    )
    payload = {
        "engine": "V2.5.2 Allocation Policy Calibration & Walk-forward Validation Extension",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sensitivity": sensitivity,
        "coverage_audit": coverage,
        "conclusion": [
            "Sensitivity compares risk-budget-to-exposure mappings on the same walk-forward V2 signal history.",
            "Long-history extension is blocked until industry opportunity and proxy price coverage are available for the desired window.",
            "No ETF selection, single-stock selection, trade execution, order generation or new alpha factor is introduced.",
        ],
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output_path),
                "best_by": sensitivity["best_by"],
                "coverage_audit": coverage,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
