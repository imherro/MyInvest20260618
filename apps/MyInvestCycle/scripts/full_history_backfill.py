from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import CACHE_DIR, DATA_DIR, DEFAULT_INDEX_CODE
from core.breadth import get_market_daily
from core.data_loader import get_index_daily, normalize_trade_date
from engine.regime_coverage_analyzer import expected_trade_dates, market_daily_cache_coverage


def _market_daily_cache_path(trade_date: str) -> Path:
    return CACHE_DIR / f"market_daily_{trade_date}.csv"


def _display_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(ROOT_DIR).as_posix()
    except ValueError:
        return resolved.as_posix()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill historical market_daily cache with resume support.")
    parser.add_argument("--start", required=True, help="Start trade date, YYYYMMDD.")
    parser.add_argument("--end", default=date.today().strftime("%Y%m%d"), help="End trade date, YYYYMMDD.")
    parser.add_argument("--ts-code", default=DEFAULT_INDEX_CODE)
    parser.add_argument("--execute", action="store_true", help="Actually fetch missing market_daily rows.")
    parser.add_argument("--refresh", action="store_true", help="Refetch existing cache files too.")
    parser.add_argument("--limit", type=int, default=0, help="Maximum missing dates to fetch in this run.")
    parser.add_argument("--batch-size", type=int, default=20, help="Progress report cadence.")
    parser.add_argument("--retries", type=int, default=2, help="Retries per failed trade date.")
    parser.add_argument("--sleep-seconds", type=float, default=0.0, help="Pause between Tushare calls.")
    parser.add_argument(
        "--progress-output",
        default=str(ROOT_DIR / "temp" / "full_history_backfill_progress.json"),
    )
    parser.add_argument("--log-output", default=str(DATA_DIR / "backfill_log.json"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    start = normalize_trade_date(args.start)
    end = normalize_trade_date(args.end)
    if start > end:
        raise ValueError("--start must be earlier than or equal to --end")
    if args.limit < 0:
        raise ValueError("--limit cannot be negative")
    if args.batch_size <= 0:
        raise ValueError("--batch-size must be positive")
    if args.retries < 0:
        raise ValueError("--retries cannot be negative")

    index_df = get_index_daily(args.ts_code, start, end)
    dates = expected_trade_dates(index_df, start_date=start, end_date=end)
    initial_coverage = market_daily_cache_coverage(dates, cache_dir=CACHE_DIR)
    missing = [
        trade_date
        for trade_date in dates
        if args.refresh or not _market_daily_cache_path(trade_date).exists()
    ]
    if args.limit:
        missing = missing[: args.limit]

    fetched: list[str] = []
    failed: list[dict[str, str]] = []
    log_entries: list[dict[str, object]] = []
    if args.execute:
        for index, trade_date in enumerate(missing, start=1):
            entry = _fetch_with_retry(trade_date, refresh=args.refresh, retries=args.retries)
            log_entries.append(entry)
            if entry["status"] == "success":
                fetched.append(trade_date)
            else:
                failed.append({"trade_date": trade_date, "reason": str(entry["error"])})
            if index % args.batch_size == 0:
                _write_progress(args.progress_output, start, end, fetched, failed, index, len(missing))
                _write_backfill_log(args.log_output, start, end, log_entries, args)
            if args.sleep_seconds > 0:
                time.sleep(args.sleep_seconds)
        _write_progress(args.progress_output, start, end, fetched, failed, len(missing), len(missing))
        _write_backfill_log(args.log_output, start, end, log_entries, args)

    final_coverage = market_daily_cache_coverage(dates, cache_dir=CACHE_DIR)
    output = {
        "metadata": {
            "start": start,
            "end": end,
            "ts_code": args.ts_code,
            "execute": bool(args.execute),
            "refresh": bool(args.refresh),
            "limit": int(args.limit),
            "batch_size": int(args.batch_size),
            "retries": int(args.retries),
            "progress_output": _display_path(args.progress_output),
            "log_output": _display_path(args.log_output),
        },
        "initial_coverage": initial_coverage,
        "planned_missing": len(missing),
        "planned_missing_sample": missing[:10],
        "fetched": len(fetched),
        "fetched_sample": fetched[:10],
        "failed": failed,
        "final_coverage": final_coverage,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def _fetch_with_retry(trade_date: str, *, refresh: bool, retries: int) -> dict[str, object]:
    started = time.perf_counter()
    attempts = 0
    last_error = ""
    rows = 0
    for attempt in range(1, retries + 2):
        attempts = attempt
        try:
            df = get_market_daily(trade_date, refresh=refresh)
            rows = int(len(df))
            return {
                "trade_date": trade_date,
                "status": "success",
                "attempts": attempts,
                "elapsed_seconds": round(time.perf_counter() - started, 4),
                "rows": rows,
                "error": "",
            }
        except Exception as exc:
            last_error = str(exc)
    return {
        "trade_date": trade_date,
        "status": "failed",
        "attempts": attempts,
        "elapsed_seconds": round(time.perf_counter() - started, 4),
        "rows": rows,
        "error": last_error,
    }


def _write_progress(
    output_path: str | Path,
    start: str,
    end: str,
    fetched: list[str],
    failed: list[dict[str, str]],
    processed: int,
    total: int,
) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    progress = {
        "start": start,
        "end": end,
        "processed": processed,
        "total": total,
        "fetched": len(fetched),
        "failed": len(failed),
        "last_fetched": fetched[-5:],
        "failed_sample": failed[:10],
    }
    path.write_text(json.dumps(progress, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_backfill_log(
    output_path: str | Path,
    start: str,
    end: str,
    entries: list[dict[str, object]],
    args: argparse.Namespace,
) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    succeeded = [entry for entry in entries if entry["status"] == "success"]
    failed = [entry for entry in entries if entry["status"] != "success"]
    payload = {
        "metadata": {
            "start": start,
            "end": end,
            "ts_code": args.ts_code,
            "refresh": bool(args.refresh),
            "limit": int(args.limit),
            "batch_size": int(args.batch_size),
            "retries": int(args.retries),
        },
        "summary": {
            "attempted": len(entries),
            "succeeded": len(succeeded),
            "failed": len(failed),
            "total_elapsed_seconds": round(sum(float(entry["elapsed_seconds"]) for entry in entries), 4),
        },
        "successful_dates": [str(entry["trade_date"]) for entry in succeeded],
        "failed_dates": [
            {
                "trade_date": str(entry["trade_date"]),
                "attempts": int(entry["attempts"]),
                "error": str(entry["error"]),
            }
            for entry in failed
        ],
        "entries": entries,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
