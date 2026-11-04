from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tenbagger.task2 import run_task2


def main() -> int:
    parser = argparse.ArgumentParser(description="Run TenBagger TASK 2 factor engine.")
    parser.add_argument("--universe", default="dev", choices=["dev", "research", "production"])
    parser.add_argument("--data-dir", default=str(ROOT / "data"))
    parser.add_argument("--report-dir", default=str(ROOT / "reports"))
    args = parser.parse_args()

    report = run_task2(
        universe_level=args.universe,
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
                "validation": report["validation"],
                "model_v2_summary": report.get("model_v2_summary", {}),
                "top_scores_v2": report.get("latest_top_scores_v2", [])[:5],
                "top_scores": report["latest_top_scores"][:5],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
