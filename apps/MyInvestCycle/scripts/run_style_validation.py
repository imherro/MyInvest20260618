from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backtest.style_attribution_validation import (
    DEFAULT_OUTPUT_PATH,
    build_style_validation,
    write_style_validation,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run V3.5.2 style preference validation.")
    parser.add_argument("--start", default="20150105")
    parser.add_argument("--end", default="20260708")
    parser.add_argument("--step", type=int, default=20)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_style_validation(
        start_date=args.start,
        end_date=args.end,
        step_sessions=args.step,
    )
    output = write_style_validation(payload, args.output)
    print(
        json.dumps(
            {
                "output": str(output),
                "metadata": payload["metadata"],
                "edge_read": payload["summary"]["edge_read"],
                "research_proxy_summary": payload["summary"]["research_proxy"],
                "tradable_etf_summary": payload["summary"]["tradable_etf"],
                "sample_preferences": payload["sample_preferences"],
                "constraints": payload["constraints"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
