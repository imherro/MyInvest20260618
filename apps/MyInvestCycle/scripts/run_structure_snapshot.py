from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from market_structure.structure_engine import build_structure_snapshot, write_structure_snapshot


def parse_args() -> argparse.Namespace:
    today = date.today().strftime("%Y%m%d")
    parser = argparse.ArgumentParser(description="Run V2.3.1 market structure snapshot.")
    parser.add_argument("--date", default=today, help="Decision date, YYYYMMDD.")
    parser.add_argument("--start-date", default="20150101", help="Index history start date, YYYYMMDD.")
    parser.add_argument("--history-sample-size", type=int, default=30)
    parser.add_argument("--cache-only", action="store_true", help="Do not fetch missing market breadth cache.")
    parser.add_argument("--output", default=str(ROOT_DIR / "data" / "structure_snapshot.json"))
    parser.add_argument("--no-write", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_structure_snapshot(
        args.date,
        start_date=args.start_date,
        history_sample_size=args.history_sample_size,
        cache_only=args.cache_only,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not args.no_write:
        write_structure_snapshot(payload, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
