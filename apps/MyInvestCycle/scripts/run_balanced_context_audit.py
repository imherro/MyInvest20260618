from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adaptive_exposure.balanced_context_audit import (
    DEFAULT_OUTPUT_PATH,
    build_balanced_context_audit,
    write_balanced_context_audit,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V5.4 balanced context candidate state audit.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_balanced_context_audit()
    output = write_balanced_context_audit(payload, args.output)
    quality = payload["summary"]["candidate_quality"]
    print(
        "V5.4 balanced context audit written to "
        f"{output} | balanced_usable_rows={payload['summary']['balanced_usable_rows']} "
        f"status={quality['status']} "
        f"ready_for_formal_rule={quality['ready_for_formal_rule']}"
    )


if __name__ == "__main__":
    main()
