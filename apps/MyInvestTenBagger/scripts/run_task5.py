from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tenbagger.task5 import run_task5


def main() -> int:
    parser = argparse.ArgumentParser(description="Run TenBagger TASK 5 factor optimization.")
    parser.add_argument("--universe", default="dev", choices=["dev", "research", "production"])
    parser.add_argument("--data-dir", default=str(ROOT / "data"))
    parser.add_argument("--report-dir", default=str(ROOT / "reports"))
    args = parser.parse_args()

    report = run_task5(
        universe_level=args.universe,
        data_dir=Path(args.data_dir),
        report_dir=Path(args.report_dir),
    )
    print(
        json.dumps(
            {
                "candidates_evaluated": report["candidates_evaluated"],
                "best_weights": report["best_weights"],
                "baseline_test_metrics": report["baseline_test_metrics"],
                "optimized_test_metrics": report["test_metrics"],
                "ic_comparison": report["ic_comparison"],
                "latest_dynamic_weights": report["regime_analysis"].get("latest_dynamic_weights", {}),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
