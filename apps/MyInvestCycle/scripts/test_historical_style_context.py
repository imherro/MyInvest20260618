from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from style_allocation.historical_style_context import (
    STYLE_CONTEXT_FIELDS,
    audit_style_context_coverage,
    build_historical_style_context,
)


def test_historical_style_context_payload() -> None:
    payload = build_historical_style_context(start_date="20240101", end_date="20240731", step_sessions=40)
    assert payload["metadata"]["engine"] == "V3.5.5 Historical Style Context Feature Expansion"
    assert payload["constraints"]["historical_context_only"] is True
    assert payload["constraints"]["does_not_modify_style_preference"] is True
    assert payload["constraints"]["no_etf_allocation"] is True
    assert payload["rows"]
    row = payload["rows"][0]
    assert row["future_safe"] is True
    assert set(STYLE_CONTEXT_FIELDS).issubset(set(row["style_context"]))
    assert "industry_breadth" in row["style_context"]
    assert "theme_persistence" in row["style_context"]
    assert "crowding_score" in row["style_context"]
    assert "price_extension" in row["style_context"]
    assert row["data_quality"]["no_future_data"] is True


def test_style_context_coverage_audit() -> None:
    payload = {
        "metadata": {
            "engine": "sample",
            "requested_window": {"start": "20240101", "end": "20240131"},
        },
        "rows": [
            {
                "date": "20240101",
                "style_context": {field: 1 for field in STYLE_CONTEXT_FIELDS},
                "data_quality": {"missing_fields": []},
            },
            {
                "date": "20240102",
                "style_context": {field: None for field in STYLE_CONTEXT_FIELDS},
                "data_quality": {"missing_fields": list(STYLE_CONTEXT_FIELDS)},
            },
        ],
    }
    coverage = audit_style_context_coverage(payload)
    assert coverage["metadata"]["row_count"] == 2
    assert coverage["summary"]["fully_populated_rows"] == 1
    assert coverage["summary"]["field_coverage"]["industry_breadth"]["coverage_rate"] == 0.5
    assert coverage["constraints"]["no_future_data"] is True


if __name__ == "__main__":
    test_historical_style_context_payload()
    test_style_context_coverage_audit()
    print("test_historical_style_context ok")
