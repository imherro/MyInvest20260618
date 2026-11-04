from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adaptive_exposure.exposure_context_score_audit import (
    DEFAULT_OUTPUT_PATH,
    build_exposure_context_score_audit,
    write_exposure_context_score_audit,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V6.3 continuous exposure context score audit.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_exposure_context_score_audit()
    output = write_exposure_context_score_audit(payload, args.output)
    summary = payload["summary"]
    separation = payload["separation_review"]
    print(
        "V6.3 exposure context score audit written to "
        f"{output} | rows={summary['joined_sample_count']} "
        f"protection_sep={summary['protection_separation']} "
        f"participation_sep={summary['participation_separation']} "
        f"risk_lift={separation['high_protection_risk_lift']} "
        f"opp_lift={separation['high_participation_opportunity_lift']}"
    )


if __name__ == "__main__":
    main()
