from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from asset_opportunity.opportunity_research_foundation import (
    DEFAULT_OUTPUT_PATH,
    build_opportunity_research_foundation,
    write_opportunity_research_foundation,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V7.1 opportunity research foundation snapshot.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    payload = build_opportunity_research_foundation()
    output = write_opportunity_research_foundation(payload, args.output)
    summary = payload["summary"]
    coverage = payload["coverage"]
    print(
        "V7.1 opportunity research foundation written to "
        f"{output} | assets={summary['asset_count']} "
        f"enabled={summary['enabled_assets']} "
        f"research_proxy_assets={summary['research_proxy_assets']} "
        f"research_full={coverage['research_proxy_history']['target_window_fully_covered']} "
        f"tradable_full={coverage['tradable_history']['target_window_fully_covered']} "
        f"readiness={summary['readiness']}"
    )


if __name__ == "__main__":
    main()
