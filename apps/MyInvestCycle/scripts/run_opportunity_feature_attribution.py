from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from asset_opportunity.opportunity_feature_attribution import (
    DEFAULT_OUTPUT_PATH,
    build_opportunity_feature_attribution,
    write_opportunity_feature_attribution,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V7.4 opportunity feature attribution and stability audit.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_opportunity_feature_attribution()
    output = write_opportunity_feature_attribution(payload, args.output)
    summary = payload["summary"]
    print(
        "V7.4 opportunity feature attribution written to "
        f"{output} | rows={summary['attribution_count']} "
        f"retention={summary['retention_counts']} "
        f"conclusion={summary['conclusion']}"
    )


if __name__ == "__main__":
    main()
