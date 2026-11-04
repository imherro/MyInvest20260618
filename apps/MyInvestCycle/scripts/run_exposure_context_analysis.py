from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adaptive_exposure.exposure_context_analysis import (
    DEFAULT_OUTPUT_PATH,
    build_exposure_context_analysis,
    write_exposure_context_analysis,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V5.3 exposure context decomposition audit.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_exposure_context_analysis()
    output = write_exposure_context_analysis(payload, args.output)
    summary = payload["summary"]
    print(
        "V5.3 exposure context analysis written to "
        f"{output} | balanced_count={summary['balanced_count']} "
        f"failure_share={summary['balanced_failure_rate']} "
        f"missed_opportunity_share={summary['balanced_missed_opportunity_rate']} "
        f"recommendation={summary['split_candidates']['recommendation']}"
    )


if __name__ == "__main__":
    main()
