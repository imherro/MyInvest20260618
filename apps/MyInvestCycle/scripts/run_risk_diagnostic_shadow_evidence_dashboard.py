from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from risk_diagnostic_shadow import (
    build_risk_diagnostic_shadow_evidence_dashboard,
    write_risk_diagnostic_shadow_evidence_dashboard,
)


def main() -> None:
    payload = build_risk_diagnostic_shadow_evidence_dashboard()
    output = write_risk_diagnostic_shadow_evidence_dashboard(payload)
    summary = payload["summary"]
    stats = payload["event_statistics"]
    print(
        "V14.9 risk diagnostic shadow evidence dashboard written to "
        f"{output} | component={summary['component_id']} "
        f"dashboard={summary['dashboard_status']} "
        f"events={stats['event_count']} "
        f"pending={stats['pending_review_count']} "
        f"reviewed={stats['reviewed_count']} "
        f"quality_queue={stats['quality_queue_count']} "
        f"trade={summary['trade_enabled']} "
        f"ready={summary['implementation_ready']} "
        f"audit={payload['audit']['audit_status']}"
    )


if __name__ == "__main__":
    main()
