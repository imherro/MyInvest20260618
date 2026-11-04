from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from asset_opportunity.opportunity_context_features import (
    DEFAULT_OUTPUT_PATH,
    build_opportunity_context_features,
    write_opportunity_context_features,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V7.2 structural opportunity context feature audit.")
    parser.add_argument("--as-of", default="20991231", help="Requested as-of date; resolved to common safe date.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_opportunity_context_features(as_of=args.as_of)
    output = write_opportunity_context_features(payload, args.output)
    summary = payload["summary"]
    print(
        "V7.2 opportunity context features written to "
        f"{output} | assets={summary['asset_count']} "
        f"as_of={summary['resolved_as_of']} "
        f"sources={summary['source_counts']} "
        f"groups={','.join(summary['feature_groups'])}"
    )


if __name__ == "__main__":
    main()
