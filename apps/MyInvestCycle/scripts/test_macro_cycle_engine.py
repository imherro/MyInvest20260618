from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from macro.macro_cycle_engine import build_macro_cycle_snapshot


def write_records(path: Path, indicator: str, records: list[dict[str, object]]) -> None:
    path.write_text(
        json.dumps({"metadata": {"indicator": indicator}, "records": records}, ensure_ascii=False),
        encoding="utf-8",
    )


def test_macro_cycle_ignores_unreleased_records() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        write_records(
            root / "M2_growth.json",
            "M2_growth",
            [
                {
                    "indicator": "M2_growth",
                    "value": 8.0,
                    "observation_date": "20260531",
                    "release_date": "20260620",
                    "effective_date": "20260620",
                    "frequency": "monthly",
                    "source": "fixture",
                    "quality_status": "valid",
                }
            ],
        )
        payload = build_macro_cycle_snapshot("20260619", start_date="20260501", data_dir=root)
        assert payload["indicator_scores"]["M2_growth"]["score"] is None
        assert "M2_growth" in payload["data_quality"]["missing_indicators"]


def test_macro_cycle_uses_available_records() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        write_records(
            root / "M2_growth.json",
            "M2_growth",
            [
                {
                    "indicator": "M2_growth",
                    "value": 8.0,
                    "observation_date": "20260531",
                    "release_date": "20260618",
                    "effective_date": "20260618",
                    "frequency": "monthly",
                    "source": "fixture",
                    "quality_status": "valid",
                }
            ],
        )
        payload = build_macro_cycle_snapshot("20260619", start_date="20260501", data_dir=root)
        assert payload["indicator_scores"]["M2_growth"]["score"] is not None
        assert payload["constraints"]["no_position_sizing"] is True


def main() -> None:
    test_macro_cycle_ignores_unreleased_records()
    test_macro_cycle_uses_available_records()


if __name__ == "__main__":
    main()
