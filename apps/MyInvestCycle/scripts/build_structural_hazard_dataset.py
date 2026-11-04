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
from engine.regime_hazard_labeler import build_hazard_dataset, hazard_label_distribution
from engine.regime_hazard_labeler_v2 import (
    build_structural_hazard_dataset,
    detect_structural_break_indices,
    save_hazard_dataset,
    smooth_regime_sequence,
    structural_hazard_diagnostics,
    validate_structural_hazard_dataset,
)
from engine.regime_transition_matrix import REGIMES, build_daily_regime_sequence


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
    parser = argparse.ArgumentParser(description="Build the structural regime hazard dataset.")
    parser.add_argument("--start", required=True, help="Start trade date, YYYYMMDD.")
    parser.add_argument("--end", default=date.today().strftime("%Y%m%d"), help="End trade date, YYYYMMDD.")
    parser.add_argument("--ts-code", default=DEFAULT_INDEX_CODE)
    parser.add_argument("--output", default=str(DATA_DIR / "structural_hazard_dataset.json"))
    parser.add_argument("--smooth-radius", type=int, default=3)
    parser.add_argument("--persistence-days", type=int, default=3)
    parser.add_argument("--forward-window", type=int, default=5)
    parser.add_argument("--min-break-gap", type=int, default=20)
    parser.add_argument("--max-hazard-rate", type=float, default=0.15)
    parser.add_argument("--refresh", action="store_true")
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
    index_df = get_index_daily(args.ts_code, warmup_start, end, refresh=args.refresh)
    if index_df.empty:
        raise RuntimeError("No index rows available for structural hazard dataset build.")

    hsgt_df = None
    if args.include_hsgt:
        hsgt_df = get_moneyflow_hsgt(_calendar_shift(start, -60), end, refresh=args.refresh)

    def market_daily_loader(trade_date: str) -> pd.DataFrame:
        if args.cache_only and not _market_daily_cache_path(trade_date).exists():
            raise FileNotFoundError(f"market_daily cache missing for {trade_date}")
        return get_market_daily(trade_date, refresh=args.refresh)

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
    raw_dataset = build_hazard_dataset(sequence.items)
    structural_dataset = build_structural_hazard_dataset(
        sequence.items,
        smooth_radius=args.smooth_radius,
        persistence_days=args.persistence_days,
        forward_window=args.forward_window,
        min_break_gap=args.min_break_gap,
    )
    validate_structural_hazard_dataset(structural_dataset, max_hazard_rate=args.max_hazard_rate)
    output_path = save_hazard_dataset(structural_dataset, args.output)

    raw_regimes = [str(item["regime"]) for item in sequence.items]
    smoothed_regimes = smooth_regime_sequence(raw_regimes, radius=args.smooth_radius)
    break_indices = detect_structural_break_indices(
        smoothed_regimes,
        persistence_days=args.persistence_days,
        min_break_gap=args.min_break_gap,
    )
    break_dates = [str(sequence.items[index]["trade_date"]) for index in break_indices]
    diagnostics = {
        "start": start,
        "end": end,
        "ts_code": args.ts_code,
        "output": _display_path(output_path),
        "sequence_observations": int(len(sequence.items)),
        "dataset_observations": int(len(structural_dataset)),
        "skipped": int(len(sequence.skipped)),
        "skipped_sample": sequence.skipped[:10],
        "raw_micro_label_distribution": hazard_label_distribution(raw_dataset),
        "structural_diagnostics": structural_hazard_diagnostics(
            structural_dataset,
            smoothed_regimes=smoothed_regimes,
            break_indices=break_indices,
            max_hazard_rate=args.max_hazard_rate,
        ),
        "structural_break_dates_sample": break_dates[:20],
        "parameters": {
            "smooth_radius": int(args.smooth_radius),
            "persistence_days": int(args.persistence_days),
            "forward_window": int(args.forward_window),
            "min_break_gap": int(args.min_break_gap),
            "max_hazard_rate": float(args.max_hazard_rate),
        },
        "regime_counts": {regime: sequence.regimes.count(regime) for regime in REGIMES},
        "cache_only": bool(args.cache_only),
        "include_hsgt": bool(args.include_hsgt),
        "history_sample_size": int(args.history_sample_size),
        "leakage_guard": "features use only t and earlier rows; structural label uses future regime outcomes only as target construction",
    }
    print(json.dumps(diagnostics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
