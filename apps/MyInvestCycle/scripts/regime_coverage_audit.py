from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import CACHE_DIR, DATA_DIR, DEFAULT_INDEX_CODE
from core.breadth import get_market_daily, get_market_history_sample
from core.data_loader import get_index_daily, normalize_trade_date
from core.liquidity import get_moneyflow_hsgt
from engine.regime_coverage_analyzer import (
    build_coverage_audit,
    expected_trade_dates,
    market_daily_cache_coverage,
    save_coverage_audit,
)
from engine.regime_transition_matrix import build_daily_regime_sequence


def _calendar_shift(date_text: str, days: int) -> str:
    return (pd.to_datetime(date_text, format="%Y%m%d") + pd.Timedelta(days=days)).strftime("%Y%m%d")


def _display_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(ROOT_DIR).as_posix()
    except ValueError:
        return resolved.as_posix()


def _market_daily_cache_path(trade_date: str) -> Path:
    return CACHE_DIR / f"market_daily_{trade_date}.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit historical cache coverage and regime label balance.")
    parser.add_argument("--start", required=True, help="Start trade date, YYYYMMDD.")
    parser.add_argument("--end", default=date.today().strftime("%Y%m%d"), help="End trade date, YYYYMMDD.")
    parser.add_argument("--ts-code", default=DEFAULT_INDEX_CODE)
    parser.add_argument("--output", default=str(DATA_DIR / "regime_coverage_audit.json"))
    parser.add_argument("--coverage-threshold", type=float, default=0.90)
    parser.add_argument("--refresh-index", action="store_true")
    parser.add_argument(
        "--fetch-missing",
        action="store_true",
        help="Fetch missing market_daily cache while auditing. Default only reads local cache.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on the first missing or invalid daily input instead of recording skipped dates.",
    )
    parser.add_argument("--include-hsgt", action="store_true")
    parser.add_argument("--history-sample-size", type=int, default=0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    start = normalize_trade_date(args.start)
    end = normalize_trade_date(args.end)
    if start > end:
        raise ValueError("--start must be earlier than or equal to --end")

    warmup_start = _calendar_shift(start, -540)
    index_df = get_index_daily(args.ts_code, warmup_start, end, refresh=args.refresh_index)
    dates = expected_trade_dates(index_df, start_date=start, end_date=end)
    cache_coverage = market_daily_cache_coverage(dates, cache_dir=CACHE_DIR)

    hsgt_df = None
    if args.include_hsgt:
        hsgt_df = get_moneyflow_hsgt(_calendar_shift(start, -60), end)

    def market_daily_loader(trade_date: str) -> pd.DataFrame:
        if not args.fetch_missing and not _market_daily_cache_path(trade_date).exists():
            raise FileNotFoundError(f"market_daily cache missing for {trade_date}")
        return get_market_daily(trade_date)

    market_history_loader = None
    if args.history_sample_size > 0:

        def load_market_history(trade_date: str, market_daily: pd.DataFrame) -> pd.DataFrame:
            return get_market_history_sample(
                market_daily,
                _calendar_shift(trade_date, -370),
                trade_date,
                sample_size=args.history_sample_size,
            )

        market_history_loader = load_market_history

    sequence = build_daily_regime_sequence(
        index_df,
        start_date=start,
        end_date=end,
        market_daily_loader=market_daily_loader,
        hsgt_df=hsgt_df,
        market_history_loader=market_history_loader,
        skip_errors=not args.strict,
    )
    audit = build_coverage_audit(
        expected_dates=dates,
        cache_coverage=cache_coverage,
        regime_items=sequence.items,
        skipped=sequence.skipped,
        coverage_threshold=args.coverage_threshold,
    )
    audit["metadata"] = {
        "start": start,
        "end": end,
        "ts_code": args.ts_code,
        "fetch_missing": bool(args.fetch_missing),
        "include_hsgt": bool(args.include_hsgt),
        "history_sample_size": int(args.history_sample_size),
    }
    output_path = save_coverage_audit(audit, args.output)
    audit["metadata"]["output"] = _display_path(output_path)
    output_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
