from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from allocation_policy.allocation_policy_engine import (
    DEFAULT_OUTPUT_PATH,
    build_allocation_policy_snapshot,
    write_allocation_policy_snapshot,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run V4.1 allocation policy foundation snapshot.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_allocation_policy_snapshot()
    output = write_allocation_policy_snapshot(payload, args.output)
    policy = payload["policy"]
    print(
        json.dumps(
            {
                "output": str(output),
                "metadata": payload["metadata"],
                "policy_state": policy["policy_state"],
                "allocation_environment": policy["allocation_environment"],
                "risk_constraints": policy["risk_constraints"],
                "constraints": payload["constraints"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
