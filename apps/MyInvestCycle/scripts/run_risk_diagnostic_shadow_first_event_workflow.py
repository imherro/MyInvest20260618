from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from risk_diagnostic_shadow import (
    build_risk_diagnostic_shadow_first_event_workflow,
    write_risk_diagnostic_shadow_first_event_workflow,
)


def main() -> None:
    payload = build_risk_diagnostic_shadow_first_event_workflow()
    output = write_risk_diagnostic_shadow_first_event_workflow(payload)
    summary = payload["summary"]
    workflow = payload["first_event_workflow"]
    print(
        "V14.7 risk diagnostic shadow first event workflow written to "
        f"{output} | component={summary['component_id']} "
        f"workflow={summary['workflow_status']} "
        f"events={summary['event_count']} "
        f"queue={summary['quality_queue_count']} "
        f"steps={workflow['workflow_step_count']} "
        f"auto_event={summary['auto_event_generation_enabled']} "
        f"trade={summary['trade_enabled']} "
        f"ready={summary['implementation_ready']} "
        f"audit={payload['audit']['audit_status']}"
    )


if __name__ == "__main__":
    main()
