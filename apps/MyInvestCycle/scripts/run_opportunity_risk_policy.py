from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from allocation_policy.policy_transition_matrix import (
    DEFAULT_OUTPUT_PATH,
    build_opportunity_risk_policy_snapshot,
    write_opportunity_risk_policy_snapshot,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V4.4 opportunity/risk policy mapping validation.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_opportunity_risk_policy_snapshot()
    output = write_opportunity_risk_policy_snapshot(payload, args.output)
    current = payload["current"]
    summary = payload["summary"]
    print(
        "V4.4 opportunity/risk policy written to "
        f"{output} | current={current['policy_mode']} "
        f"replay_count={summary['replay_count']}"
    )


if __name__ == "__main__":
    main()
