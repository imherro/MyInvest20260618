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
from macro.indicator_registry import get_all_indicators, registry_as_dict
from macro.macro_cache_writer import DEFAULT_MACRO_DATA_DIR, write_macro_records
from macro.macro_loader import load_macro_indicators
from macro.tushare_macro_adapter import fetch_macro_indicator_from_tushare


def parse_args() -> argparse.Namespace:
    today = date.today().strftime("%Y%m%d")
    parser = argparse.ArgumentParser(description="Fetch V2 macro data into the local cache.")
    parser.add_argument("--start-date", default="20200101", help="Observation start date, YYYYMMDD.")
    parser.add_argument("--end-date", default=today, help="Observation end date, YYYYMMDD.")
    parser.add_argument("--indicator", action="append", dest="indicators", help="Indicator to fetch; repeatable.")
    parser.add_argument("--data-dir", default=str(DEFAULT_MACRO_DATA_DIR), help="Local macro cache directory.")
    parser.add_argument("--no-merge", action="store_true", help="Rewrite indicator cache instead of merging records.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero if any requested indicator fails.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    indicators = tuple(args.indicators) if args.indicators else get_all_indicators()
    fetch_results: list[dict[str, object]] = []
    output_files: dict[str, str] = {}

    for indicator in indicators:
        result = fetch_macro_indicator_from_tushare(indicator, args.start_date, args.end_date)
        fetch_results.append(result.to_dict())
        if result.records:
            path = write_macro_records(
                indicator,
                result.records,
                data_dir=args.data_dir,
                merge=not args.no_merge,
            )
            output_files[indicator] = str(path.resolve())

    records_by_indicator = load_macro_indicators(
        indicators,
        args.start_date,
        args.end_date,
        data_dir=args.data_dir,
    )
    audit = audit_macro_records(records_by_indicator, required_indicators=indicators, decision_date=args.end_date)
    failed = [item for item in fetch_results if item["status"] not in {"ok", "no_records"}]
    report = {
        "requested_range": {
            "start_date": args.start_date,
            "end_date": args.end_date,
        },
        "data_dir": str(Path(args.data_dir).resolve()),
        "registry": registry_as_dict(),
        "fetch_results": fetch_results,
        "output_files": output_files,
        "audit": audit,
        "status": "fail" if (args.strict and (failed or audit["status"] == "fail")) else "pass",
        "constraints": {
            "no_macro_score": True,
            "no_macro_state": True,
            "no_bull_bear_judgement": True,
            "no_position_sizing": True,
            "no_etf_allocation": True,
            "no_backtest": True,
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
