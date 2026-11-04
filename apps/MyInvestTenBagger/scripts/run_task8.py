from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tenbagger.task8 import run_task8


def main() -> int:
    parser = argparse.ArgumentParser(description="Run TenBagger TASK 8 market regime engine.")
    parser.add_argument("--universe", default="dev", choices=["dev", "research", "production"])
    parser.add_argument("--data-dir", default=str(ROOT / "data"))
    parser.add_argument("--report-dir", default=str(ROOT / "reports"))
    parser.add_argument("--refresh-index", action="store_true")
    args = parser.parse_args()

    report = run_task8(
        universe_level=args.universe,
        data_dir=Path(args.data_dir),
        report_dir=Path(args.report_dir),
        refresh_index=args.refresh_index,
    )
    print(
        json.dumps(
            {
                "api_response": report["api_response"],
                "validation": report["validation"],
                "recent_30_changes": report["history"]["recent_30_changes"],
                "data_source": report["data_source"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
