from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from theme_risk.opportunity_quality_engine import (
    DEFAULT_OUTPUT_PATH,
    build_theme_risk_snapshot,
    write_theme_risk_snapshot,
)


def parse_args() -> argparse.Namespace:
    today = date.today().strftime("%Y%m%d")
    parser = argparse.ArgumentParser(description="Run V2.3.4 theme valuation and crowding risk snapshot.")
    parser.add_argument("--date", default=today, help="Decision date, YYYYMMDD.")
    parser.add_argument("--start-date", default="20240101")
    parser.add_argument("--cache-only", action="store_true", default=True)
    parser.add_argument("--allow-fetch", action="store_false", dest="cache_only")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--no-write", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_theme_risk_snapshot(args.date, start_date=args.start_date, cache_only=args.cache_only)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not args.no_write:
        write_theme_risk_snapshot(payload, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
