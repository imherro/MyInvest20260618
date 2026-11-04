from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adaptive_exposure.exposure_simulator import (
    DEFAULT_OUTPUT_PATH,
    build_exposure_simulation,
    write_exposure_simulation,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V5.1 qualitative exposure policy simulation.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_exposure_simulation()
    output = write_exposure_simulation(payload, args.output)
    summary = payload["summary"]
    audit = summary["audit"]
    current = payload["current"]
    print(
        "V5.1 exposure simulation written to "
        f"{output} | current={current['exposure_level']} "
        f"replay_count={summary['replay_count']} "
        f"contradiction_rate={audit['contradiction_rate']} "
        f"opportunity_miss_rate={audit['opportunity_miss_rate']}"
    )


if __name__ == "__main__":
    main()
