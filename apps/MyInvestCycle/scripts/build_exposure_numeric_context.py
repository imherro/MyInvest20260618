from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adaptive_exposure.exposure_numeric_context import (
    DEFAULT_OUTPUT_PATH,
    build_exposure_numeric_context,
    write_exposure_numeric_context,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build V5.6 exposure numeric context enrichment.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_exposure_numeric_context()
    output = write_exposure_numeric_context(payload, args.output)
    summary = payload["summary"]
    time_safety = summary["time_safety"]
    print(
        "V5.6 exposure numeric context written to "
        f"{output} | rows={summary['row_count']} "
        f"fully_populated={summary['fully_populated_rows']} "
        f"non_macro_full={summary['fully_populated_non_macro_rows']} "
        f"time_safe={time_safety['feature_date_lte_signal_date']} "
        f"violations={time_safety['violation_count']}"
    )


if __name__ == "__main__":
    main()
