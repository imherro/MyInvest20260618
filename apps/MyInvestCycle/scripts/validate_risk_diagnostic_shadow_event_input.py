from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from risk_diagnostic_shadow import validate_risk_diagnostic_shadow_event_input_file


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate one manual no-trade shadow event JSON without submitting it.",
    )
    parser.add_argument("--event-file", required=True, help="Path to a manually prepared shadow event JSON file.")
    args = parser.parse_args()
    result = validate_risk_diagnostic_shadow_event_input_file(args.event_file)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("validation_status") != "valid_not_submitted":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
