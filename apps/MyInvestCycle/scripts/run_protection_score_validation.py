from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adaptive_exposure.protection_score_validation import (
    DEFAULT_OUTPUT_PATH,
    build_protection_score_validation,
    write_protection_score_validation,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V6.4 protection score robustness and conditional validation.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_protection_score_validation()
    output = write_protection_score_validation(payload, args.output)
    summary = payload["summary"]
    comparison = payload["model_comparison"]["comparison_summary"]
    print(
        "V6.4 protection score validation written to "
        f"{output} | rows={summary['joined_sample_count']} "
        f"risk_lift={summary['model_a_high_risk_lift']} "
        f"protection_lift={summary['model_b_protection_high_risk_lift']} "
        f"combined_lift={summary['model_c_both_high_risk_lift']} "
        f"phase_consistency={summary['protection_phase_consistency']} "
        f"protection_capture={comparison['protection_capture_rate']}"
    )


if __name__ == "__main__":
    main()
