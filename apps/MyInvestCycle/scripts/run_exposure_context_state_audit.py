from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adaptive_exposure.exposure_context_state_audit import (
    DEFAULT_OUTPUT_PATH,
    build_exposure_context_state_audit,
    write_exposure_context_state_audit,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V5.9 exposure context state design audit.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_exposure_context_state_audit()
    output = write_exposure_context_state_audit(payload, args.output)
    summary = payload["summary"]
    time_safety = summary["time_safety"]
    print(
        "V5.9 exposure context state audit written to "
        f"{output} | rows={summary['balanced_usable_rows']} "
        f"status={summary['candidate_quality_status']} "
        f"violations={time_safety['violation_count']}"
    )


if __name__ == "__main__":
    main()
