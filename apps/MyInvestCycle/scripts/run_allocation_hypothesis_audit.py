from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from allocation_research.allocation_hypothesis_audit import (
    DEFAULT_OUTPUT_PATH,
    build_allocation_hypothesis_framework,
    validate_allocation_hypothesis_framework,
    write_allocation_hypothesis_framework,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and audit V9.2 allocation research hypotheses.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_allocation_hypothesis_framework()
    audit = validate_allocation_hypothesis_framework(payload)
    output = write_allocation_hypothesis_framework(payload, args.output)
    summary = payload["summary"]
    print(
        "V9.2 allocation hypothesis framework written to "
        f"{output} | hypotheses={summary['hypothesis_count']} "
        f"validated={summary['validated_count']} "
        f"audit={audit['audit_status']}"
    )


if __name__ == "__main__":
    main()
