from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adaptive_exposure.exposure_decision_audit import (
    DEFAULT_OUTPUT_PATH,
    build_exposure_decision_audit,
    write_exposure_decision_audit,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V6.2 adaptive exposure decision context audit.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_exposure_decision_audit()
    output = write_exposure_decision_audit(payload, args.output)
    summary = payload["summary"]
    separation = payload["separation_review"]
    print(
        "V6.2 exposure decision audit written to "
        f"{output} | rows={summary['joined_sample_count']} "
        f"risk_sep={summary['risk_separation']} "
        f"opp_sep={summary['opportunity_separation']} "
        f"risk_lift={separation['caution_vs_participation_risk_lift']}"
    )


if __name__ == "__main__":
    main()
