from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from risk_diagnostic_shadow import (
    build_risk_diagnostic_shadow_framework,
    write_risk_diagnostic_shadow_framework,
)


def main() -> None:
    payload = build_risk_diagnostic_shadow_framework()
    output = write_risk_diagnostic_shadow_framework(payload)
    summary = payload["summary"]
    print(
        "V14.2 risk diagnostic shadow framework written to "
        f"{output} | component={summary['component_id']} "
        f"shadow={summary['shadow_status']} "
        f"events={summary['live_event_count']} "
        f"trade={summary['trade_enabled']} "
        f"ready={summary['implementation_ready']} "
        f"audit={payload['audit']['audit_status']}"
    )


if __name__ == "__main__":
    main()
