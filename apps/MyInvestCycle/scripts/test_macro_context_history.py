from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from macro.historical_macro_context import build_macro_context_history


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _macro_record(
    indicator: str,
    value: float,
    observation_date: str,
    release_date: str,
    *,
    effective_date: str | None = None,
) -> dict[str, object]:
    return {
        "indicator": indicator,
        "value": value,
        "observation_date": observation_date,
        "release_date": release_date,
        "effective_date": effective_date or release_date,
        "frequency": "monthly",
        "source": "fixture",
        "quality_status": "valid",
    }


def test_macro_context_history_blocks_future_release() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        data_dir = root / "data"
        macro_dir = data_dir / "macro"
        _write_json(
            data_dir / "exposure_simulation.json",
            {
                "historical_replay": [
                    {"date": "20240110", "exposure_level": "BALANCED"},
                    {"date": "20240220", "exposure_level": "BALANCED"},
                ]
            },
        )
        _write_json(
            macro_dir / "M2_growth.json",
            {
                "records": [
                    _macro_record("M2_growth", 7.0, "20231231", "20240115"),
                    _macro_record("M2_growth", 99.0, "20240131", "20240225"),
                ]
            },
        )
        _write_json(
            macro_dir / "M1_growth.json",
            {"records": [_macro_record("M1_growth", 3.0, "20231231", "20240115")]},
        )

        payload = build_macro_context_history(data_dir, macro_data_dir=macro_dir, start_date="20231201")

    first, second = payload["rows"]
    assert first["macro_context"]["M2_growth"] is None
    assert first["source_trace"]["M2_growth"]["reason"] == "no_time_safe_record"
    assert second["macro_context"]["M2_growth"] == 7.0
    assert second["source_trace"]["M2_growth"]["release_date"] == "20240115"
    assert second["macro_context"]["M1_M2_spread"] == -4.0
    assert payload["summary"]["time_safety"]["violation_count"] == 0
    assert payload["constraints"]["does_not_modify_exposure_mapper"] is True


def test_macro_context_history_blocks_future_effective_date() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        data_dir = root / "data"
        macro_dir = data_dir / "macro"
        _write_json(data_dir / "exposure_simulation.json", {"historical_replay": [{"date": "20240120"}]})
        _write_json(
            macro_dir / "PMI.json",
            {
                "records": [
                    _macro_record("PMI", 52.0, "20231231", "20240101", effective_date="20240125"),
                ]
            },
        )

        payload = build_macro_context_history(data_dir, macro_data_dir=macro_dir, start_date="20231201")

    row = payload["rows"][0]
    assert row["macro_context"]["PMI"] is None
    assert row["source_trace"]["PMI"]["reason"] == "no_time_safe_record"
    assert row["data_quality"]["release_date_lte_signal_date"] is True
    assert payload["summary"]["time_safety"]["violation_count"] == 0


def test_real_macro_context_history_payload() -> None:
    payload = build_macro_context_history()
    assert payload["metadata"]["engine"] == "V5.7 Historical Macro Context Enrichment"
    assert payload["summary"]["row_count"] >= 100
    assert payload["summary"]["time_safety"]["violation_count"] == 0
    assert payload["summary"]["macro_score_coverage"]["available_count"] > 0
    assert payload["summary"]["field_coverage"]["M2_growth"]["available_count"] > 0
    assert payload["summary"]["field_coverage"]["PE_percentile"]["available_count"] == 0
    assert payload["data_quality"]["missing_values_are_null"] is True
    assert payload["constraints"]["no_trade_signal"] is True


if __name__ == "__main__":
    test_macro_context_history_blocks_future_release()
    test_macro_context_history_blocks_future_effective_date()
    test_real_macro_context_history_payload()
    print("test_macro_context_history ok")
