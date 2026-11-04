from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tenbagger.task7 import run_task7


def main() -> int:
    parser = argparse.ArgumentParser(description="Run TenBagger TASK 7 structural alpha validation.")
    parser.add_argument("--universe", default="dev", choices=["dev", "research", "production"])
    parser.add_argument("--data-dir", default=str(ROOT / "data"))
    parser.add_argument("--report-dir", default=str(ROOT / "reports"))
    args = parser.parse_args()

    report = run_task7(
        universe_level=args.universe,
        data_dir=Path(args.data_dir),
        report_dir=Path(args.report_dir),
    )
    print(
        json.dumps(
            {
                "classification": report["classification"],
                "split_date": report["split_date"],
                "criteria": report["criteria"],
                "stability_report": report["stability_report"],
                "randomization_test": report["randomization_test"],
                "failure_mode_diagnosis": report["failure_mode_diagnosis"],
                "oos_metrics": report["oos_metrics"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
