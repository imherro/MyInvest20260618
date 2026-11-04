from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from asset_opportunity.opportunity_score_engine import (
    DEFAULT_OUTPUT_PATH,
    build_asset_opportunity_snapshot,
    write_asset_opportunity_snapshot,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run V3.2.1 asset opportunity scoring snapshot.")
    parser.add_argument("--date", default="20991231", help="Requested as-of date, YYYYMMDD.")
    parser.add_argument("--start", default="20150105", help="Historical start date, YYYYMMDD.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_asset_opportunity_snapshot(args.date, start_date=args.start, cache_only=True)
    output = write_asset_opportunity_snapshot(payload, args.output)
    print(
        json.dumps(
            {
                "output": str(output),
                "as_of": payload["metadata"]["as_of"],
                "asset_count": payload["metadata"]["asset_count"],
                "top_assets": payload["summary"]["top_assets"],
                "constraints": payload["constraints"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
