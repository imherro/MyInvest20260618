from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from strategy_rebase import (
    build_v15_late_cycle_overlay_manifest,
    build_v15_point_in_time_phase_rebuild_status,
    write_v15_late_cycle_overlay_manifest,
    write_v15_point_in_time_phase_rebuild_status,
)


def main() -> None:
    status = build_v15_point_in_time_phase_rebuild_status()
    manifest = build_v15_late_cycle_overlay_manifest()
    status_path = write_v15_point_in_time_phase_rebuild_status(status)
    manifest_path = write_v15_late_cycle_overlay_manifest(manifest)
    summary = status["summary"]
    print(
        f"V15.5 status written to {status_path} and {manifest_path} | "
        f"status={summary['status']} phase_rows={summary['phase_row_count']} "
        f"unverified={summary['unverified_date_count']} gaps={summary['gap_count']} "
        f"promotion_ready={summary['promotion_ready']}"
    )


if __name__ == "__main__":
    main()
