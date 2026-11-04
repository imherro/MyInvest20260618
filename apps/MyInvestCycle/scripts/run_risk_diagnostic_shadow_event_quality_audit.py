from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from risk_diagnostic_shadow import (
    build_risk_diagnostic_shadow_event_quality_audit,
    write_risk_diagnostic_shadow_event_quality_audit,
)


def main() -> None:
    payload = build_risk_diagnostic_shadow_event_quality_audit()
    output = write_risk_diagnostic_shadow_event_quality_audit(payload)
    summary = payload["summary"]
    print(
        "V14.6 risk diagnostic shadow event quality audit written to "
        f"{output} | component={summary['component_id']} "
        f"audit={summary['quality_audit_status']} "
        f"events={summary['event_count']} "
        f"checked={summary['quality_checked_events']} "
        f"auto_decision={summary['auto_decision_enabled']} "
        f"trade={summary['trade_enabled']} "
        f"ready={summary['implementation_ready']} "
        f"validator={payload['audit']['audit_status']}"
    )


if __name__ == "__main__":
    main()
