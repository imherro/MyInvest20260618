from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from risk_diagnostic_shadow import (
    build_risk_diagnostic_shadow_event_input_package,
    write_risk_diagnostic_shadow_event_input_package,
)


def main() -> None:
    payload = build_risk_diagnostic_shadow_event_input_package()
    output, template = write_risk_diagnostic_shadow_event_input_package(payload)
    summary = payload["summary"]
    print(
        "V14.8 risk diagnostic shadow event input package written to "
        f"{output} | template={template} "
        f"component={summary['component_id']} "
        f"template_status={summary['template_status']} "
        f"event_submitted={summary['event_submitted']} "
        f"validated={summary['validated_event_count']} "
        f"auto_event={summary['auto_event_generation_enabled']} "
        f"trade={summary['trade_enabled']} "
        f"ready={summary['implementation_ready']} "
        f"audit={payload['audit']['audit_status']}"
    )


if __name__ == "__main__":
    main()
