from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from industry_structure.opportunity_engine import (
    DEFAULT_OUTPUT_PATH,
    build_industry_opportunity_snapshot,
    write_industry_opportunity_snapshot,
)


def parse_args() -> argparse.Namespace:
    today = date.today().strftime("%Y%m%d")
    parser = argparse.ArgumentParser(description="Run V2.3.2 industry/theme opportunity snapshot.")
    parser.add_argument("--date", default=today, help="Decision date, YYYYMMDD.")
    parser.add_argument("--start-date", default="20240101", help="Industry history start date, YYYYMMDD.")
    parser.add_argument("--refresh-universe", action="store_true")
    parser.add_argument("--refresh-prices", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--no-write", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_industry_opportunity_snapshot(
        args.date,
        start_date=args.start_date,
        refresh_universe=args.refresh_universe,
        refresh_prices=args.refresh_prices,
        cache_only=args.cache_only,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not args.no_write:
        write_industry_opportunity_snapshot(payload, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
