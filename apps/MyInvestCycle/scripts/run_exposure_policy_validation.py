from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adaptive_exposure.exposure_policy_validation import (
    DEFAULT_OUTPUT_PATH,
    build_exposure_policy_validation,
    write_exposure_policy_validation,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V6.1 adaptive exposure policy simulation validation.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_exposure_policy_validation()
    output = write_exposure_policy_validation(payload, args.output)
    summary = payload["summary"]
    model_b = payload["model_comparison"]["model_b_v5_1_plus_risk_gradient_flag"]
    print(
        "V6.1 exposure policy validation written to "
        f"{output} | rows={summary['joined_sample_count']} "
        f"capture={model_b['high_risk_event_capture_rate']} "
        f"false_warning={model_b['false_warning_rate']} "
        f"status={summary['policy_validation_status']}"
    )


if __name__ == "__main__":
    main()
