from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import DATA_DIR
from core.benchmark_loader import load_benchmark_daily, read_benchmark_cache
from core.data_loader import normalize_trade_date
from core.etf_rotation_backtest_engine import run_etf_rotation_backtest
from core.etf_universe_builder import ETF_UNIVERSE
from core.shadow_portfolio_engine import load_structural_survival_rows


DEFAULT_OUTPUT = DATA_DIR / "etf_rotation_backtest.json"


def _calendar_shift(date_text: str, days: int) -> str:
    return (pd.to_datetime(date_text, format="%Y%m%d") + pd.Timedelta(days=days)).strftime("%Y%m%d")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run A1.3 ETF rotation backtest and alpha validation.")
    parser.add_argument("--start", default="20200101", help="Start date, YYYYMMDD.")
    parser.add_argument("--end", default="20260625", help="End date, YYYYMMDD.")
    parser.add_argument("--dataset", default=str(DATA_DIR / "structural_survival_dataset.json"))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--regime-field", default="raw_regime")
    parser.add_argument("--rebalance-every-sessions", type=int, default=20)
    parser.add_argument("--lookback-sessions", type=int, default=260)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    return parser.parse_args()


def _date_window(rows: list[dict[str, object]], start: str, end: str) -> tuple[str, str]:
    dates = sorted(str(row["date"]) for row in rows if isinstance(row, dict) and row.get("date"))
    if not dates:
        raise ValueError("dataset has no date rows")
    start_date = max(normalize_trade_date(start), dates[0])
    end_date = min(normalize_trade_date(end), dates[-1])
    if start_date > end_date:
        raise ValueError("start must be earlier than or equal to end")
    return start_date, end_date


def _load_price_history(
    start_date: str,
    end_date: str,
    *,
    refresh: bool,
    cache_only: bool,
) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    price_history: dict[str, pd.DataFrame] = {}
    errors: dict[str, str] = {}
    warmup_start = _calendar_shift(start_date, -430)
    for etf in ETF_UNIVERSE:
        code = str(etf["code"])
        try:
            if cache_only:
                frame = read_benchmark_cache(code, warmup_start, end_date)
            else:
                frame = load_benchmark_daily(
                    code,
                    warmup_start,
                    end_date,
                    refresh=refresh,
                    cache_only=False,
                )
        except Exception as exc:
            errors[code] = str(exc)
            continue
        if frame.empty:
            errors[code] = "empty fund_daily history"
            continue
        price_history[code] = frame
    return price_history, errors


def main() -> None:
    args = parse_args()
    rows = load_structural_survival_rows(args.dataset)
    start_date, end_date = _date_window(rows, args.start, args.end)
    price_history, price_errors = _load_price_history(
        start_date,
        end_date,
        refresh=args.refresh,
        cache_only=args.cache_only,
    )
    result = run_etf_rotation_backtest(
        rows,
        price_history,
        start_date=start_date,
        end_date=end_date,
        regime_field=args.regime_field,
        rebalance_every_sessions=args.rebalance_every_sessions,
        lookback_sessions=args.lookback_sessions,
    )
    result["price_history"] = {
        "loaded_etfs": sorted(price_history),
        "errors": price_errors,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "output": str(output_path),
                "summary": result["summary"],
                "validation": result["validation"],
                "price_history_errors": price_errors,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
