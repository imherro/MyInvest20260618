from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from external_validation.validation_protocol_audit import (
    DEFAULT_OUTPUT_PATH,
    build_external_validation_protocol,
    validate_external_validation_protocol,
    write_external_validation_protocol,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V11.1 external validation research protocol.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_external_validation_protocol()
    audit = validate_external_validation_protocol(payload)
    output = write_external_validation_protocol(payload, args.output)
    summary = payload["summary"]
    print(
        "V11.1 external validation protocol written to "
        f"{output} | target={summary['target_hypothesis']} "
        f"excluded={summary['excluded_direction_count']} "
        f"audit={audit['audit_status']}"
    )


if __name__ == "__main__":
    main()
