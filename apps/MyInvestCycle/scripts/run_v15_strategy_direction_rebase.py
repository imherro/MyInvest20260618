from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from strategy_rebase import build_v15_strategy_direction_rebase, write_v15_strategy_direction_rebase


def main() -> None:
    payload = build_v15_strategy_direction_rebase()
    output = write_v15_strategy_direction_rebase(payload)
    summary = payload["summary"]
    frozen = payload["frozen_tracks"]["v12_v14_governance_shadow"]
    print(
        "V15.0 strategy direction rebase written to "
        f"{output} | phase={summary['phase']} "
        f"direction={summary['mainline_direction']} "
        f"primary={summary['primary_objective']} "
        f"secondary={summary['secondary_objective']} "
        f"v12_v14={frozen['status']} "
        f"trade={summary['production_trade_enabled']} "
        f"audit={payload['audit']['audit_status']}"
    )


if __name__ == "__main__":
    main()
