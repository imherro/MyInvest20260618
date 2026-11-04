from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adaptive_exposure.macro_enhanced_context_analysis import (
    DEFAULT_OUTPUT_PATH,
    build_macro_enhanced_context_analysis,
    write_macro_enhanced_context_analysis,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V5.8 macro-enhanced BALANCED candidate attribution.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_macro_enhanced_context_analysis()
    output = write_macro_enhanced_context_analysis(payload, args.output)
    summary = payload["summary"]
    time_safety = summary["time_safety"]
    print(
        "V5.8 macro-enhanced context analysis written to "
        f"{output} | rows={summary['balanced_usable_rows']} "
        f"macro_value={summary['macro_added_explanatory_value']} "
        f"violations={time_safety['violation_count']}"
    )


if __name__ == "__main__":
    main()
