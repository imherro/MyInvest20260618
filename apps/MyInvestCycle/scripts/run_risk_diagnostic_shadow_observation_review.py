from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from risk_diagnostic_shadow import (
    build_risk_diagnostic_shadow_observation_review,
    write_risk_diagnostic_shadow_observation_review,
)


def main() -> None:
    payload = build_risk_diagnostic_shadow_observation_review()
    output = write_risk_diagnostic_shadow_observation_review(payload)
    summary = payload["summary"]
    print(
        "V14.4 risk diagnostic shadow observation review written to "
        f"{output} | component={summary['component_id']} "
        f"review={summary['review_status']} "
        f"events={summary['event_count']} "
        f"reviewed={summary['reviewed_event_count']} "
        f"trade={summary['trade_enabled']} "
        f"ready={summary['implementation_ready']} "
        f"audit={payload['audit']['audit_status']}"
    )


if __name__ == "__main__":
    main()
