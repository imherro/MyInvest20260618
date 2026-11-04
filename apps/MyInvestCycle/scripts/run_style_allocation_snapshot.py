from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from style_allocation.style_allocator import (
    DEFAULT_OUTPUT_PATH,
    build_style_allocation_snapshot,
    write_style_allocation_snapshot,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run V3.5.1 style allocation preference snapshot.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_style_allocation_snapshot()
    output = write_style_allocation_snapshot(payload, args.output)
    print(
        json.dumps(
            {
                "output": str(output),
                "metadata": payload["metadata"],
                "dominant_style": payload["preference"]["dominant_style"],
                "top_styles": payload["preference"]["top_styles"],
                "reason_codes": payload["preference"]["reason_codes"],
                "constraints": payload["constraints"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
