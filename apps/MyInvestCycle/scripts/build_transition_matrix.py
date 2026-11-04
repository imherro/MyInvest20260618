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

from config import BREADTH_HISTORY_SAMPLE_SIZE, CACHE_DIR, DATA_DIR, DEFAULT_INDEX_CODE
from core.breadth import get_market_daily, get_market_history_sample
from core.data_loader import get_index_daily, normalize_trade_date
from core.liquidity import get_moneyflow_hsgt
from engine.regime_transition_matrix import (
    REGIMES,
    build_daily_regime_sequence,
    count_transitions,
    normalize_transition_counts,
    save_transition_matrix,
    transition_row_sums,
    validate_transition_matrix,
)


def _calendar_shift(date_text: str, days: int) -> str:
    return (pd.to_datetime(date_text, format="%Y%m%d") + pd.Timedelta(days=days)).strftime("%Y%m%d")


def _market_daily_cache_path(trade_date: str) -> Path:
    return CACHE_DIR / f"market_daily_{trade_date}.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a regime transition probability matrix.")
    parser.add_argument("--start", required=True, help="Start trade date, YYYYMMDD.")
    parser.add_argument("--end", default=date.today().strftime("%Y%m%d"), help="End trade date, YYYYMMDD.")
    parser.add_argument("--ts-code", default=DEFAULT_INDEX_CODE)
    parser.add_argument("--output", default=str(DATA_DIR / "transition_matrix.json"))
    parser.add_argument("--diagnostics-output", default="", help="Optional path for counts and run diagnostics.")
    parser.add_argument("--refresh", action="store_true", help="Refresh index and market cache from Tushare.")
    parser.add_argument(
        "--cache-only",
        action="store_true",
        help="Use local market_daily cache only; missing dates are skipped.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on the first missing or invalid daily input instead of skipping it.",
    )
    parser.add_argument(
        "--include-hsgt",
        action="store_true",
        help="Include northbound-flow data in liquidity scoring.",
    )
    parser.add_argument(
        "--history-sample-size",
        type=int,
        default=0,
        help="Optional 52-week breadth sample size. Defaults to 0 for a lightweight build.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    start = normalize_trade_date(args.start)
    end = normalize_trade_date(args.end)
    if start > end:
        raise ValueError("--start must be earlier than or equal to --end")

    warmup_start = _calendar_shift(start, -540)
    index_df = get_index_daily(args.ts_code, warmup_start, end, refresh=args.refresh)
    if index_df.empty:
        raise RuntimeError("No index rows available for transition matrix build.")

    hsgt_df = None
    if args.include_hsgt:
        hsgt_df = get_moneyflow_hsgt(_calendar_shift(start, -60), end, refresh=args.refresh)

    def market_daily_loader(trade_date: str) -> pd.DataFrame:
        if args.cache_only and not _market_daily_cache_path(trade_date).exists():
            raise FileNotFoundError(f"market_daily cache missing for {trade_date}")
        return get_market_daily(trade_date, refresh=args.refresh)

    market_history_loader = None
    if args.history_sample_size > 0:
        sample_size = args.history_sample_size or BREADTH_HISTORY_SAMPLE_SIZE

        def load_market_history(trade_date: str, market_daily: pd.DataFrame) -> pd.DataFrame:
            return get_market_history_sample(
                market_daily,
                _calendar_shift(trade_date, -370),
                trade_date,
                sample_size=sample_size,
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
    if len(sequence.items) < 2:
        raise RuntimeError("At least two valid regime observations are required.")

    counts = count_transitions(sequence.regimes, regimes=REGIMES)
    matrix = normalize_transition_counts(counts, regimes=REGIMES)
    validate_transition_matrix(matrix, counts=counts, regimes=REGIMES)
    output_path = save_transition_matrix(matrix, args.output)

    diagnostics = {
        "start": start,
        "end": end,
        "ts_code": args.ts_code,
        "output": str(output_path),
        "observations": len(sequence.items),
        "transitions": max(0, len(sequence.items) - 1),
        "skipped": len(sequence.skipped),
        "skipped_sample": sequence.skipped[:10],
        "regime_counts": {regime: sequence.regimes.count(regime) for regime in REGIMES},
        "transition_counts": counts,
        "row_sums": transition_row_sums(matrix),
        "cache_only": bool(args.cache_only),
        "include_hsgt": bool(args.include_hsgt),
        "history_sample_size": int(args.history_sample_size),
    }
    if args.diagnostics_output:
        diagnostics_path = Path(args.diagnostics_output)
        diagnostics_path.parent.mkdir(parents=True, exist_ok=True)
        diagnostics_path.write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(diagnostics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
