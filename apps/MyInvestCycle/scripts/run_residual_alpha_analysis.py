from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backtest.factor_neutral_attribution import (
    DEFAULT_OUTPUT_PATH,
    build_residual_alpha_analysis,
    write_residual_alpha_analysis,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run V3.4.5 residual alpha attribution analysis.")
    parser.add_argument("--start", default="20150105")
    parser.add_argument("--end", default="20260708")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_residual_alpha_analysis(start_date=args.start, end_date=args.end)
    output = write_residual_alpha_analysis(payload, args.output)
    print(
        json.dumps(
            {
                "output": str(output),
                "metadata": payload["metadata"],
                "summary": payload["summary"],
                "periods": [
                    {
                        "label": period["label"],
                        "portfolio": period["portfolio_metrics"],
                        "r_squared": period["factor_model"].get("r_squared"),
                        "intercept_annualized_linear": period["factor_model"].get("intercept_annualized_linear"),
                        "neutralized_residual": period["factor_neutral_residual_metrics"],
                        "betas": period["factor_model"].get("betas"),
                    }
                    for period in payload["periods"]
                ],
                "constraints": payload["constraints"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
