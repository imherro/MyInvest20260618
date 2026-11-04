from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from macro.macro_cycle_engine import build_macro_cycle_snapshot


def parse_args() -> argparse.Namespace:
    today = date.today().strftime("%Y%m%d")
    parser = argparse.ArgumentParser(description="Run V2.2.1 macro cycle snapshot from cached macro data.")
    parser.add_argument("--date", default=today, help="Decision date, YYYYMMDD.")
    parser.add_argument("--start-date", default="20200101", help="Cache observation start date, YYYYMMDD.")
    parser.add_argument("--data-dir", default=str(ROOT_DIR / "data" / "macro"), help="Local macro cache directory.")
    parser.add_argument("--output", default=str(ROOT_DIR / "data" / "macro_cycle_snapshot.json"))
    parser.add_argument("--no-write", action="store_true", help="Print only; do not write the snapshot artifact.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_macro_cycle_snapshot(args.date, start_date=args.start_date, data_dir=args.data_dir)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not args.no_write:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
