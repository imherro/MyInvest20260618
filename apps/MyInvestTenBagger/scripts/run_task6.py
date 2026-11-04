from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tenbagger.task6 import run_task6


def main() -> int:
    parser = argparse.ArgumentParser(description="Run TenBagger TASK 6 alpha monetization.")
    parser.add_argument("--universe", default="dev", choices=["dev", "research", "production"])
    parser.add_argument("--data-dir", default=str(ROOT / "data"))
    parser.add_argument("--report-dir", default=str(ROOT / "reports"))
    args = parser.parse_args()

    report = run_task6(
        universe_level=args.universe,
        data_dir=Path(args.data_dir),
        report_dir=Path(args.report_dir),
    )
    print(
        json.dumps(
            {
                "best_config": report["best_config"],
                "train_metrics": report["train_metrics"],
                "test_metrics": report["test_metrics"],
                "ic_pnl_divergence": report["ic_pnl_divergence"],
                "alpha_decay": report["alpha_decay"],
                "cost_sensitivity": report["cost_sensitivity"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
