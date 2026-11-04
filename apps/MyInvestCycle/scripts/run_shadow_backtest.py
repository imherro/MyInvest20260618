from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import DATA_DIR
from core.benchmark_loader import DEFAULT_BENCHMARK_CODE, load_benchmark_daily
from core.data_loader import normalize_trade_date
from core.shadow_portfolio_engine import load_structural_survival_rows, run_shadow_backtest


DEFAULT_OUTPUT = DATA_DIR / "shadow_equity_curve.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run S1.1 shadow portfolio backtest against 510500.")
    parser.add_argument("--start", default=None, help="Start date, YYYYMMDD. Defaults to first survival row.")
    parser.add_argument("--end", default=None, help="End date, YYYYMMDD. Defaults to last survival row.")
    parser.add_argument("--benchmark-code", default=DEFAULT_BENCHMARK_CODE)
    parser.add_argument("--dataset", default=str(DATA_DIR / "structural_survival_dataset.json"))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--regime-field", default="raw_regime")
    parser.add_argument("--execution-lag-sessions", type=int, default=1)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    return parser.parse_args()


def _date_window(rows: list[dict[str, object]], start: str | None, end: str | None) -> tuple[str, str]:
    dates = sorted(str(row["date"]) for row in rows if isinstance(row, dict) and row.get("date"))
    if not dates:
        raise ValueError("dataset has no date rows")
    start_date = normalize_trade_date(start) if start else dates[0]
    end_date = normalize_trade_date(end) if end else dates[-1]
    if start_date > end_date:
        raise ValueError("start must be earlier than or equal to end")
    return start_date, end_date


def main() -> None:
    args = parse_args()
    rows = load_structural_survival_rows(args.dataset)
    start_date, end_date = _date_window(rows, args.start, args.end)
    benchmark = load_benchmark_daily(
        args.benchmark_code,
        start_date,
        end_date,
        refresh=args.refresh,
        cache_only=args.cache_only,
    )
    result = run_shadow_backtest(
        rows,
        benchmark,
        start_date=start_date,
        end_date=end_date,
        benchmark_code=args.benchmark_code,
        regime_field=args.regime_field,
        execution_lag_sessions=args.execution_lag_sessions,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output_path),
                "summary": result["summary"],
                "metadata": result["metadata"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
