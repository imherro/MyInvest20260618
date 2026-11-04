from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backtest.alpha_portfolio_risk_validation import (
    DEFAULT_OUTPUT_PATH,
    build_alpha_portfolio_risk_validation,
    write_alpha_portfolio_risk_validation,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run V3.4.3 alpha portfolio risk-control validation.")
    parser.add_argument("--start", default="20150105")
    parser.add_argument("--end", default="20991231")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_alpha_portfolio_risk_validation(start_date=args.start, end_date=args.end)
    output = write_alpha_portfolio_risk_validation(payload, args.output)
    print(
        json.dumps(
            {
                "output": str(output),
                "scenario_count": payload["metadata"]["scenario_count"],
                "primary_series": payload["summary"]["primary_series"],
                "rebalance_sensitivity": payload["summary"]["rebalance_sensitivity"],
                "cost_sensitivity": payload["summary"]["cost_sensitivity"],
                "minimum_holding_sensitivity": payload["summary"]["minimum_holding_sensitivity"],
                "constraints": payload["constraints"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
