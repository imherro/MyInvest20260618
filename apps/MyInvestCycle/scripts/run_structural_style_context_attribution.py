from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from style_allocation.structural_style_context_attribution import (
    DEFAULT_OUTPUT_PATH,
    build_structural_style_context_attribution,
    write_structural_style_context_attribution,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run V3.5.6 structural bull style context re-attribution.")
    parser.add_argument("--style-validation", default="data/style_validation.json")
    parser.add_argument("--context", default="data/historical_style_context.json")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_structural_style_context_attribution(
        style_validation_path=args.style_validation,
        context_path=args.context,
    )
    output = write_structural_style_context_attribution(payload, args.output)
    print(
        json.dumps(
            {
                "output": str(output),
                "metadata": payload["metadata"],
                "summary": payload["summary"],
                "constraints": payload["constraints"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
