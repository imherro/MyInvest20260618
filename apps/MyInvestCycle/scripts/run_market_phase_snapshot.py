from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from allocation_policy.market_phase_classifier import (
    DEFAULT_OUTPUT_PATH,
    build_market_phase_snapshot,
    write_market_phase_snapshot,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V4.6 market phase classification snapshot.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_market_phase_snapshot()
    output = write_market_phase_snapshot(payload, args.output)
    current = payload["current"]
    summary = payload["historical_summary"]
    validation = summary["future_validation"]
    print(
        "V4.6 market phase snapshot written to "
        f"{output} | current={current['phase']} "
        f"replay_count={summary['replay_count']} "
        f"phase_spread={validation.get('phase_high_risk_rate_spread')}"
    )


if __name__ == "__main__":
    main()
