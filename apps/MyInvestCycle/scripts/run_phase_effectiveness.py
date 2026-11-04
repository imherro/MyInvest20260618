from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from allocation_policy.phase_effectiveness_audit import (
    DEFAULT_OUTPUT_PATH,
    build_phase_effectiveness_audit,
    write_phase_effectiveness_audit,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V4.7 market phase effectiveness audit.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_phase_effectiveness_audit()
    output = write_phase_effectiveness_audit(payload, args.output)
    summary = payload["summary"]
    model = summary["model_comparison"]
    print(
        "V4.7 phase effectiveness audit written to "
        f"{output} | usable_rows={summary['usable_rows']} "
        f"phase_spread={model['phase_high_risk_rate_spread']} "
        f"phase_vs_structural={model['phase_vs_structural']}"
    )


if __name__ == "__main__":
    main()
