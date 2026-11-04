from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from asset_opportunity.asset_proxy_registry import (
    DEFAULT_PROXY_REGISTRY_PATH,
    build_asset_proxy_registry,
    write_asset_proxy_registry,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build V3.1.2 research proxy registry.")
    parser.add_argument("--asset-registry", default=str(ROOT_DIR / "data" / "asset_registry.json"))
    parser.add_argument("--output", default=str(DEFAULT_PROXY_REGISTRY_PATH))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_asset_proxy_registry(asset_registry_path=args.asset_registry)
    output = write_asset_proxy_registry(payload, args.output)
    print(
        json.dumps(
            {
                "output": str(output),
                "metadata": payload["metadata"],
                "constraints": payload["constraints"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
