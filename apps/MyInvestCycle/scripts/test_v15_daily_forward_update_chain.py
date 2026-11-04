from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.run_v15_daily_forward_update import run_daily_forward_update
from strategy_rebase.daily_snapshot_capture import FORBIDDEN_OUTPUT_KEYS, find_forbidden_output_keys
from strategy_rebase.forward_outcome_intake import OUTCOME_FORBIDDEN_KEYS, find_outcome_forbidden_keys


CAPTURED_AT = "2026-07-20T20:00:00+08:00"


def _write(root: Path, relative_path: str, content: str) -> None:
    target = root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _index_csv(rows: list[tuple[str, float]]) -> str:
    return "trade_date,close\n" + "".join(f"{date},{close}\n" for date, close in rows)


def _fixture() -> tempfile.TemporaryDirectory[str]:
    temporary = tempfile.TemporaryDirectory()
    root = Path(temporary.name)
    _write(root, "data/macro_context_history.json", "{}\n")
    _write(
        root,
        "data/market_phase_snapshot.json",
        json.dumps(
            {
                "current": {
                    "phase": "LATE_CYCLE",
                    "metrics": {
                        "macro_state": "RECOVERY",
                        "structural_state": "STRUCTURAL_BULL_ROTATION",
                    },
                }
            }
        ),
    )
    _write(root, "data/historical_style_context.json", "{}\n")
    _write(root, "data/structural_hazard_dataset.json", "[]\n")
    _write(root, "data/cache/index_daily_000300_SH.csv", _index_csv([("20260720", 100.0)]))
    return temporary


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_daily_forward_update_chain_pending_then_completed() -> None:
    with _fixture() as tmp:
        root = Path(tmp)
        first = run_daily_forward_update(
            root_dir=root,
            snapshot_date="20260720",
            captured_at=CAPTURED_AT,
        )
        assert first == {
            "snapshot_date": "20260720",
            "journal_record_count": 1,
            "outcome_record_count": 3,
            "completed_outcome_count": 0,
            "pending_outcome_count": 3,
            "appended": True,
            "backtest_allowed": False,
            "production_trade_enabled": False,
        }
        assert (root / "data/point_in_time_snapshots/20260720/manifest.json").is_file()
        assert _json(root / "data/v15_daily_snapshot_capture_status.json")["immutable_snapshot_created"] is True
        assert _json(root / "data/v15_forward_observation_journal_status.json")["record_count"] == 1
        assert _json(root / "data/v15_forward_outcome_status.json")["pending_outcome_count"] == 3

        journal_path = root / "data/v15_forward_observation_journal.jsonl"
        journal_bytes = journal_path.read_bytes()
        future_rows = [("20260720", 100.0)] + [(f"202608{day:02d}", 100.0 + day) for day in range(1, 21)]
        _write(root, "data/cache/index_daily_000300_SH.csv", _index_csv(future_rows))
        second = run_daily_forward_update(
            root_dir=root,
            snapshot_date="20260720",
            captured_at="2026-07-20T21:00:00+08:00",
        )
        assert second["appended"] is False
        assert second["completed_outcome_count"] == 3
        assert second["pending_outcome_count"] == 0
        assert journal_path.read_bytes() == journal_bytes

        capture = _json(root / "data/v15_forward_paper_decision_latest.json")
        journal = _jsonl(journal_path)
        outcomes = _jsonl(root / "data/v15_forward_outcome_records.jsonl")
        combined = {"capture": capture, "journal": journal, "outcomes": outcomes}
        assert find_forbidden_output_keys(combined) == set()
        assert find_outcome_forbidden_keys(combined) == set()
        serialized = json.dumps(combined, ensure_ascii=False)
        for key in FORBIDDEN_OUTPUT_KEYS | OUTCOME_FORBIDDEN_KEYS:
            assert f'"{key}"' not in serialized


def main() -> None:
    test_daily_forward_update_chain_pending_then_completed()
    print("test_v15_daily_forward_update_chain ok")


if __name__ == "__main__":
    main()
