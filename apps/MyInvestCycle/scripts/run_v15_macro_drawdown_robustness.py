from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from strategy_rebase import (
    build_v15_macro_drawdown_robustness_result,
    write_v15_macro_drawdown_robustness_result,
)


def _percent(value: object) -> str:
    return "--" if not isinstance(value, (int, float)) else f"{value * 100:.2f}%"


def main() -> None:
    payload = build_v15_macro_drawdown_robustness_result()
    output = write_v15_macro_drawdown_robustness_result(payload)
    summary = payload["summary"]
    print(
        "V15.4 macro drawdown robustness result written to "
        f"{output} | variants={summary['parameter_variants']} "
        f"default_rank={summary['default_variant_rank']} "
        f"CAGR_range={_percent(summary['CAGR_range'])} "
        f"walk_forward_CAGR={_percent(summary['walk_forward_CAGR'])} "
        f"walk_forward_max_drawdown={_percent(summary['walk_forward_max_drawdown'])} "
        f"beats_csi300={summary['walk_forward_beats_csi_300']} "
        f"stable={summary['parameter_neighborhood_stable']} "
        f"point_in_time={summary['strict_point_in_time_status']} "
        f"audit={payload['audit']['audit_status']}"
    )


if __name__ == "__main__":
    main()
