from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from asset_opportunity.opportunity_feature_validation import (
    DEFAULT_OUTPUT_PATH,
    build_opportunity_feature_validation,
    write_opportunity_feature_validation,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V7.3 opportunity feature effectiveness audit.")
    parser.add_argument("--as-of", default="20991231", help="Requested as-of date for validation labels.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_opportunity_feature_validation(as_of=args.as_of)
    output = write_opportunity_feature_validation(payload, args.output)
    summary = payload["summary"]
    print(
        "V7.3 opportunity feature validation written to "
        f"{output} | features={summary['feature_count']} "
        f"horizons={summary['horizons']} "
        f"results={summary['result_count']} "
        f"context_dates={summary['context_observation_count']}"
    )


if __name__ == "__main__":
    main()
