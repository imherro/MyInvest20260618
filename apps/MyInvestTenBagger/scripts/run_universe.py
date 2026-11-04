from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tenbagger.universe import UniverseManager


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect TenBagger universe selection.")
    parser.add_argument("--level", default="dev", choices=["dev", "research", "production"])
    args = parser.parse_args()

    details = UniverseManager.get_details(args.level)
    print(
        json.dumps(
            {
                "level": details["level"],
                "stock_count": details["stock_count"],
                "source": details["source"],
                "filter_stats": details["filter_stats"],
                "sample": details["sample"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
