from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from structural_bull.structural_bull_engine import (
    DEFAULT_OUTPUT_PATH,
    build_structural_bull_snapshot,
    write_structural_bull_snapshot,
)


def parse_args() -> argparse.Namespace:
    today = date.today().strftime("%Y%m%d")
    parser = argparse.ArgumentParser(description="Run V2.3.3 structural bull rotation snapshot.")
    parser.add_argument("--date", default=today, help="Decision date, YYYYMMDD.")
    parser.add_argument("--macro-start-date", default="20240101")
    parser.add_argument("--structure-start-date", default="20150101")
    parser.add_argument("--industry-start-date", default="20240101")
    parser.add_argument("--history-sample-size", type=int, default=30)
    parser.add_argument("--cache-only", action="store_true", default=True)
    parser.add_argument("--allow-fetch", action="store_false", dest="cache_only")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--no-write", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_structural_bull_snapshot(
        args.date,
        macro_start_date=args.macro_start_date,
        structure_start_date=args.structure_start_date,
        industry_start_date=args.industry_start_date,
        history_sample_size=args.history_sample_size,
        cache_only=args.cache_only,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not args.no_write:
        write_structural_bull_snapshot(payload, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
