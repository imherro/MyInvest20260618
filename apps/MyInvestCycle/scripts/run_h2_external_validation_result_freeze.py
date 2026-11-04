from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from external_validation.validation_result_freeze import (
    DEFAULT_OUTPUT_PATH,
    build_h2_external_validation_result_freeze,
    validate_h2_external_validation_result_freeze,
    write_h2_external_validation_result_freeze,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V11.3 H2 external validation result freeze.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_h2_external_validation_result_freeze()
    audit = validate_h2_external_validation_result_freeze(payload)
    output = write_h2_external_validation_result_freeze(payload, args.output)
    summary = payload["summary"]
    print(
        "V11.3 H2 external validation result freeze written to "
        f"{output} | status={summary['h2_status']} "
        f"decision={payload['final_conclusion']['research_decision']} "
        f"audit={audit['audit_status']}"
    )


if __name__ == "__main__":
    main()
