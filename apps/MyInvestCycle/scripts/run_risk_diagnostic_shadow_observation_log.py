from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from risk_diagnostic_shadow import (
    build_risk_diagnostic_shadow_observation_log,
    write_risk_diagnostic_shadow_observation_log,
)


def main() -> None:
    payload = build_risk_diagnostic_shadow_observation_log()
    output = write_risk_diagnostic_shadow_observation_log(payload)
    summary = payload["summary"]
    print(
        "V14.3 risk diagnostic shadow observation log written to "
        f"{output} | component={summary['component_id']} "
        f"status={summary['observation_status']} "
        f"events={summary['event_count']} "
        f"auto_trigger={summary['auto_trigger_enabled']} "
        f"trade={summary['trade_enabled']} "
        f"ready={summary['implementation_ready']} "
        f"audit={payload['audit']['audit_status']}"
    )


if __name__ == "__main__":
    main()
