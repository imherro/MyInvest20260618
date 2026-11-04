from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from strategy_rebase import build_v15_daily_snapshot_capture, write_v15_daily_snapshot_capture


def main() -> None:
    manifest, status, decision = build_v15_daily_snapshot_capture()
    status_path, decision_path = write_v15_daily_snapshot_capture(status, decision)
    print(
        f"V15.7 snapshot={status['snapshot_directory']} manifest={manifest['manifest_sha256']} "
        f"available={manifest['available_source_count']} missing={manifest['missing_source_count']} "
        f"decision={status['paper_decision_status']} status={status_path} output={decision_path}"
    )


if __name__ == "__main__":
    main()
