from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tenbagger.task1 import run_task1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run TenBagger TASK 1 data loader.")
    parser.add_argument("--universe", default="dev", choices=["dev", "research", "production"])
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument(
        "--request-interval",
        type=float,
        default=None,
        help="Seconds to wait between per-stock TuShare batches. Default is 0.4 or TUSHARE_REQUEST_INTERVAL_SECONDS.",
    )
    parser.add_argument("--data-dir", default=str(ROOT / "data"))
    parser.add_argument("--report-dir", default=str(ROOT / "reports"))
    args = parser.parse_args()

    report = run_task1(
        universe_level=args.universe,
        start_date=args.start_date,
        end_date=args.end_date,
        request_interval=args.request_interval,
        data_dir=Path(args.data_dir),
        report_dir=Path(args.report_dir),
    )
    print(
        json.dumps(
            {
                "stock_count": report["stock_count"],
                "row_count": report["row_count"],
                "date_range": report["date_range"],
                "latest_trading_date": report["latest_trading_date"],
                "missing_rates": report["missing_rates"],
                "universe_level": report["storage"]["universe_level"],
                "universe_count": report["storage"]["universe_count"],
                "request_interval_seconds": report["storage"]["request_interval_seconds"],
                "loaded_codes": report["storage"]["loaded_codes"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
