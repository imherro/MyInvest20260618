from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adaptive_exposure.context_information_attribution import (
    DEFAULT_OUTPUT_PATH,
    build_context_information_attribution,
    write_context_information_attribution,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V6.6 adaptive context information attribution audit.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_context_information_attribution()
    output = write_context_information_attribution(payload, args.output)
    summary = payload["summary"]
    print(
        "V6.6 context information attribution written to "
        f"{output} | rows={summary['joined_sample_count']} "
        f"risk_leader={summary['risk_leader']} "
        f"risk_spread={summary['risk_leader_spread']} "
        f"opportunity_leader={summary['opportunity_leader']} "
        f"opportunity_spread={summary['opportunity_leader_spread']} "
        f"retained={summary['retained_layer_count']}"
    )


if __name__ == "__main__":
    main()
