from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import DATA_DIR
from style_allocation.historical_style_context import (
    DEFAULT_COVERAGE_OUTPUT_PATH,
    audit_style_context_coverage,
    write_style_context_coverage,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit V3.5.5 historical style context coverage.")
    parser.add_argument("--input", default=str(DATA_DIR / "historical_style_context.json"))
    parser.add_argument("--output", default=str(DEFAULT_COVERAGE_OUTPUT_PATH))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    coverage = audit_style_context_coverage(payload)
    output = write_style_context_coverage(coverage, args.output)
    print(json.dumps({"output": str(output), **coverage}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
