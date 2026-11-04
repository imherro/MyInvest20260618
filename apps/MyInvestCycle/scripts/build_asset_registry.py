from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from asset_opportunity.asset_registry import DEFAULT_REGISTRY_PATH, build_asset_registry, write_asset_registry


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build V3.1.1 ETF-only asset registry.")
    parser.add_argument("--output", default=str(DEFAULT_REGISTRY_PATH))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_asset_registry()
    output = write_asset_registry(payload, args.output)
    print(
        json.dumps(
            {
                "output": str(output),
                "asset_count": payload["metadata"]["asset_count"],
                "category_counts": payload["metadata"]["category_counts"],
                "constraints": payload["constraints"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
