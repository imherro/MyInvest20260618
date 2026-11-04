from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tenbagger.task3 import run_task3


def main() -> int:
    parser = argparse.ArgumentParser(description="Run TenBagger TASK 3 screener.")
    parser.add_argument("--universe", default="dev", choices=["dev", "research", "production"])
    parser.add_argument("--data-dir", default=str(ROOT / "data"))
    parser.add_argument("--report-dir", default=str(ROOT / "reports"))
    args = parser.parse_args()

    report = run_task3(
        universe_level=args.universe,
        data_dir=Path(args.data_dir),
        report_dir=Path(args.report_dir),
    )
    print(
        json.dumps(
            {
                "stock_count": report["stock_count"],
                "row_count": report["row_count"],
                "latest_trading_date": report["latest_trading_date"],
                "candidate_count": report["candidate_count"],
                "model_v2_summary": report.get("model_v2_summary", {}),
                "v2_top_candidates": report.get("v2_top_candidates", [])[:5],
                "v2_ic_decay_curve": report.get("v2_ic_decay_curve", []),
                "v2_backtest_preview": report.get("v2_backtest_preview", {}),
                "top_candidates": report["top_candidates"][:5],
                "ic_decay_curve": report["ic_decay_curve"],
                "backtest_preview": report["backtest_preview"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
