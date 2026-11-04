from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tenbagger.task4 import run_task4


def main() -> int:
    parser = argparse.ArgumentParser(description="Run TenBagger TASK 4 portfolio backtest.")
    parser.add_argument("--universe", default="dev", choices=["dev", "research", "production"])
    parser.add_argument("--data-dir", default=str(ROOT / "data"))
    parser.add_argument("--report-dir", default=str(ROOT / "reports"))
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--weight-mode", default="score", choices=["equal", "score", "volatility_adjusted"])
    args = parser.parse_args()

    report = run_task4(
        universe_level=args.universe,
        data_dir=Path(args.data_dir),
        report_dir=Path(args.report_dir),
        top_k=args.top_k,
        weight_mode=args.weight_mode,
    )
    print(
        json.dumps(
            {
                "date_range": report["date_range"],
                "nav_rows": report["nav_rows"],
                "rebalance_count": report["rebalance_count"],
                "final_nav": report["final_nav"],
                "metrics": report["metrics"],
                "dominant_factor": report["factor_attribution"]["dominant_factor"],
                "latest_holdings": report["latest_holdings"][:5],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
