from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from allocation_research.allocation_experiment_audit import (
    DEFAULT_OUTPUT_PATH,
    build_allocation_experiment_templates,
    validate_allocation_experiment_templates,
    write_allocation_experiment_templates,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and audit V9.4 allocation experiment templates.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_allocation_experiment_templates()
    audit = validate_allocation_experiment_templates(payload)
    output = write_allocation_experiment_templates(payload, args.output)
    summary = payload["summary"]
    print(
        "V9.4 allocation experiment templates written to "
        f"{output} | templates={summary['experiment_template_count']} "
        f"executed={summary['executed_experiment_count']} "
        f"audit={audit['audit_status']}"
    )


if __name__ == "__main__":
    main()
