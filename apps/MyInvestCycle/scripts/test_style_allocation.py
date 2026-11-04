from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from style_allocation.style_allocator import build_style_allocation_snapshot
from style_allocation.style_schema import STYLE_IDS


def test_style_allocation_snapshot() -> None:
    payload = build_style_allocation_snapshot()
    assert payload["metadata"]["engine"] == "V3.5.1 Style Allocation Engine Foundation"
    assert payload["metadata"]["not_an_etf_weight_model"] is True
    assert payload["constraints"]["analysis_only"] is True
    assert payload["constraints"]["style_preference_only"] is True
    assert payload["constraints"]["no_asset_weight"] is True
    assert payload["constraints"]["no_etf_allocation"] is True
    assert payload["constraints"]["no_trade_signal"] is True
    assert payload["constraints"]["no_backtest"] is True
    assert payload["constraints"]["alpha_model_unchanged"] is True
    assert payload["constraints"]["router_unchanged"] is True

    assert {item["style_id"] for item in payload["style_universe"]} == set(STYLE_IDS)
    environment = payload["preference"]["style_environment"]
    assert set(environment) == set(STYLE_IDS)
    for style_id, row in environment.items():
        assert 0 <= row["preference_score"] <= 100
        assert 0 <= row["relative_signal_share"] <= 1
        assert "weight" not in row
        assert isinstance(row["evidence"], list)

    signal_share_sum = sum(row["relative_signal_share"] for row in environment.values())
    assert abs(signal_share_sum - 1.0) <= 0.00001
    assert payload["preference"]["dominant_style"] in STYLE_IDS
    assert payload["preference"]["top_styles"]
    assert payload["preference"]["interpretation"]


if __name__ == "__main__":
    test_style_allocation_snapshot()
    print("test_style_allocation ok")
