from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backtest.rolling_validation import (
    DEFAULT_OUTPUT_PATH,
    build_alpha_robustness_validation,
    write_alpha_robustness_validation,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run V3.4.4 alpha robustness and style attribution validation.")
    parser.add_argument("--start", default="20150105")
    parser.add_argument("--end", default="20260708")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_alpha_robustness_validation(start_date=args.start, end_date=args.end)
    output = write_alpha_robustness_validation(payload, args.output)
    print(
        json.dumps(
            {
                "output": str(output),
                "metadata": payload["metadata"],
                "summary": payload["summary"],
                "periods": [
                    {
                        "label": period["label"],
                        "portfolio": period["portfolio"],
                        "dominant_style": (period.get("style_exposure") or {}).get("dominant_style"),
                        "spread_vs_510500": period["spreads"].get("vs_510500.SH"),
                        "spread_vs_growth": period["spreads"].get("vs_159915.SZ"),
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
