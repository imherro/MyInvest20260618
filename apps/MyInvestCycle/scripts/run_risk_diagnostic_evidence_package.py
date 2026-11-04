from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from implementation_readiness.risk_diagnostic_evidence_package import (
    build_risk_diagnostic_evidence_package,
    write_risk_diagnostic_evidence_package,
)


def main() -> None:
    payload = build_risk_diagnostic_evidence_package()
    output = write_risk_diagnostic_evidence_package(payload)
    summary = payload["summary"]
    validator = payload["v13_2_validator_result"]
    print(
        "V14.1 risk diagnostic evidence package written to "
        f"{output} | component={payload['component_id']} "
        f"evidence={summary['evidence_status']} "
        f"package={validator['package_status']} "
        f"ready={summary['implementation_ready']} "
        f"audit={payload['audit']['audit_status']}"
    )


if __name__ == "__main__":
    main()
