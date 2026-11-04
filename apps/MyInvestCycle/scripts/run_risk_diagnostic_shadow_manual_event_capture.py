from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from risk_diagnostic_shadow import (
    build_risk_diagnostic_shadow_manual_event_capture_status,
    capture_manual_shadow_event_from_file,
    write_risk_diagnostic_shadow_manual_event_capture_status,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create V14.5 manual no-trade shadow event capture status, or append one explicit manual event file.",
    )
    parser.add_argument(
        "--event-file",
        help="Optional JSON file containing one manually prepared no-trade shadow event. If omitted, no event is appended.",
    )
    args = parser.parse_args()

    if args.event_file:
        payload = capture_manual_shadow_event_from_file(args.event_file)
        output = Path("data/risk_diagnostic_shadow_manual_event_capture.json").resolve()
    else:
        payload = build_risk_diagnostic_shadow_manual_event_capture_status()
        output = write_risk_diagnostic_shadow_manual_event_capture_status(payload)

    summary = payload["summary"]
    print(
        "V14.5 risk diagnostic shadow manual event capture written to "
        f"{output} | component={summary['component_id']} "
        f"capture={summary['manual_capture_status']} "
        f"source_events={summary['source_event_count']} "
        f"submitted={summary['submitted_event_count']} "
        f"auto_trigger={summary['auto_trigger_enabled']} "
        f"trade={summary['trade_enabled']} "
        f"ready={summary['implementation_ready']} "
        f"audit={payload['audit']['audit_status']}"
    )


if __name__ == "__main__":
    main()
