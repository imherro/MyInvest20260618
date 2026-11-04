from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backtest.alpha_portfolio_backtest import (
    DEFAULT_OUTPUT_PATH,
    build_alpha_portfolio_backtest,
    write_alpha_portfolio_backtest,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run V3.4.2 alpha portfolio simulation backtest.")
    parser.add_argument("--start", default="20150105")
    parser.add_argument("--end", default="20991231")
    parser.add_argument("--step", type=int, default=20)
    parser.add_argument("--cost", type=float, default=0.001)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_alpha_portfolio_backtest(
        start_date=args.start,
        end_date=args.end,
        step_sessions=args.step,
        transaction_cost=args.cost,
    )
    output = write_alpha_portfolio_backtest(payload, args.output)
    tradable = payload["strategies"]["tradable_etf"]
    print(
        json.dumps(
            {
                "output": str(output),
                "transaction_cost": payload["metadata"]["transaction_cost"],
                "tradable_router_top3": tradable["router_selected_model_top3"]["metrics"],
                "tradable_baseline_top3": tradable["opportunity_score_top3"]["metrics"],
                "benchmarks": {code: item["metrics"] for code, item in payload["benchmarks"].items()},
                "constraints": payload["constraints"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
