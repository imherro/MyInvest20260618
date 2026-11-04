from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from macro.historical_macro_context import (
    DEFAULT_OUTPUT_PATH,
    build_macro_context_history,
    write_macro_context_history,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build V5.7 historical macro context enrichment.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    parser.add_argument("--data-dir", default=str(ROOT_DIR / "data"), help="Project data directory.")
    parser.add_argument("--macro-data-dir", default=str(ROOT_DIR / "data" / "macro"), help="Macro cache directory.")
    parser.add_argument("--start-date", default="20140101", help="Macro observation start date.")
    args = parser.parse_args()

    payload = build_macro_context_history(
        args.data_dir,
        macro_data_dir=args.macro_data_dir,
        start_date=args.start_date,
    )
    output = write_macro_context_history(payload, args.output)
    summary = payload["summary"]
    time_safety = summary["time_safety"]
    print(
        "V5.7 macro context history written to "
        f"{output} | rows={summary['row_count']} "
        f"macro_score={summary['macro_score_coverage']['available_count']} "
        f"violations={time_safety['violation_count']}"
    )


if __name__ == "__main__":
    main()
