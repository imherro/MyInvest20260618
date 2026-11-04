from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from macro.data_quality import audit_macro_records
from macro.indicator_registry import get_all_indicators, get_indicator_definition
from macro.macro_loader import load_macro_indicator
from macro.release_calendar import is_available, is_record_available
from macro.schema import MacroIndicatorRecord


def test_release_calendar_blocks_future_release() -> None:
    assert not is_available("20260620", "20260619")
    assert is_available("20260618", "20260619")


def test_record_availability_uses_effective_date() -> None:
    record = MacroIndicatorRecord(
        indicator="M2_growth",
        value=6.8,
        observation_date="20260531",
        release_date="20260618",
        effective_date="20260620",
        frequency="monthly",
        source="fixture",
        quality_status="valid",
    )
    assert not is_record_available(record, "20260619")
    assert is_record_available(record, "20260620")


def test_loader_and_audit_detect_future_leakage() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "M2_growth.json"
        path.write_text(
            """
[
  {
    "indicator": "M2_growth",
    "value": 6.8,
    "observation_date": "20260531",
    "release_date": "20260620",
    "effective_date": "20260620",
    "frequency": "monthly",
    "source": "fixture",
    "quality_status": "valid"
  }
]
""".strip(),
            encoding="utf-8",
        )
        records = load_macro_indicator("M2_growth", "20260501", "20260630", data_dir=temp_dir)
        assert len(records) == 1
        report = audit_macro_records(
            {"M2_growth": records},
            required_indicators=("M2_growth",),
            decision_date="20260619",
        )
        assert report["status"] == "fail"
        assert report["future_leakage"] is True


def test_indicator_registry_has_required_definitions() -> None:
    indicators = get_all_indicators()
    assert "M2_growth" in indicators
    assert "new_loans" in indicators
    definition = get_indicator_definition("M2_growth")
    assert definition.category == "credit"
    assert definition.source == "tushare"
    assert definition.release_lag_days >= 0


def main() -> None:
    test_release_calendar_blocks_future_release()
    test_record_availability_uses_effective_date()
    test_loader_and_audit_detect_future_leakage()
    test_indicator_registry_has_required_definitions()


if __name__ == "__main__":
    main()
