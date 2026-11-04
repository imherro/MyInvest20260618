from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adaptive_exposure.exposure_effectiveness import (
    DEFAULT_OUTPUT_PATH,
    build_exposure_effectiveness,
    write_exposure_effectiveness,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V5.2 exposure level effectiveness audit.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_exposure_effectiveness()
    output = write_exposure_effectiveness(payload, args.output)
    summary = payload["summary"]
    distribution = summary["distribution_review"]
    ordering = summary["ordering_review"]
    print(
        "V5.2 exposure effectiveness audit written to "
        f"{output} | usable_rows={summary['usable_rows']} "
        f"dominant={distribution['dominant_level']} "
        f"ordering={ordering['status']} "
        f"review_items={summary['review_item_count']}"
    )


if __name__ == "__main__":
    main()
