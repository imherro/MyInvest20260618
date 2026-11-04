from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from macro.data_quality import audit_macro_records
from macro.macro_loader import DEFAULT_MACRO_DATA_DIR, DEFAULT_MACRO_INDICATORS, load_macro_indicators


def parse_args() -> argparse.Namespace:
    today = date.today().strftime("%Y%m%d")
    parser = argparse.ArgumentParser(description="Audit V2 macro data foundation.")
    parser.add_argument("--start-date", default="19900101", help="Observation start date, YYYYMMDD.")
    parser.add_argument("--end-date", default=today, help="Observation end date, YYYYMMDD.")
    parser.add_argument("--decision-date", default=None, help="Decision date for future-leakage checks, YYYYMMDD.")
    parser.add_argument("--data-dir", default=str(DEFAULT_MACRO_DATA_DIR), help="Local macro cache directory.")
    parser.add_argument(
        "--indicator",
        action="append",
        dest="indicators",
        help="Required indicator to audit. Repeat to override the default indicator set.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    indicators = tuple(args.indicators) if args.indicators else DEFAULT_MACRO_INDICATORS
    records_by_indicator = load_macro_indicators(
        indicators,
        args.start_date,
        args.end_date,
        data_dir=args.data_dir,
    )
    report = audit_macro_records(
        records_by_indicator,
        required_indicators=indicators,
        decision_date=args.decision_date,
    )
    report["data_dir"] = str(Path(args.data_dir).resolve())
    report["requested_range"] = {
        "start_date": args.start_date,
        "end_date": args.end_date,
        "decision_date": args.decision_date,
    }
    report["supported_indicators"] = list(indicators)
    report["constraints"] = {
        "no_macro_score": True,
        "no_macro_state": True,
        "no_bull_bear_judgement": True,
        "no_position_sizing": True,
        "no_etf_allocation": True,
        "no_backtest": True,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
