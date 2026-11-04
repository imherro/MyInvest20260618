from __future__ import annotations

import argparse
from datetime import date

from config import DEFAULT_INDEX_CODE
from core.data_loader import get_index_daily


def main() -> None:
    parser = argparse.ArgumentParser(description="Update cached Tushare index daily data.")
    parser.add_argument("--ts-code", default=DEFAULT_INDEX_CODE)
    parser.add_argument("--start-date", default="20150101")
    parser.add_argument("--end-date", default=date.today().strftime("%Y%m%d"))
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    df = get_index_daily(
        args.ts_code,
        args.start_date,
        args.end_date,
        refresh=args.refresh,
    )
    print(f"rows: {len(df)}")
    if not df.empty:
        print(f"range: {df['trade_date'].min()} -> {df['trade_date'].max()}")


if __name__ == "__main__":
    main()
