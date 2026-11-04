from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from external_validation.research_phase_closure import (
    DEFAULT_OUTPUT_PATH,
    build_research_phase_closure,
    validate_research_phase_closure,
    write_research_phase_closure,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V11.4 research phase closure.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_research_phase_closure()
    audit = validate_research_phase_closure(payload)
    output = write_research_phase_closure(payload, args.output)
    summary = payload["summary"]
    print(
        "V11.4 research phase closure written to "
        f"{output} | phase={summary['research_phase']} "
        f"risk={summary['risk_research_status']} "
        f"allocation={summary['allocation_status']} "
        f"trading={summary['trading_status']} "
        f"audit={audit['audit_status']}"
    )


if __name__ == "__main__":
    main()
