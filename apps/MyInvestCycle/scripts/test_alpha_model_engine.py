from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from asset_opportunity.alpha_model_engine import build_alpha_model_snapshot


def test_alpha_model_engine() -> None:
    payload = build_alpha_model_snapshot("20260708", start_date="20150105")
    assert payload["metadata"]["engine"] == "V3.3.2 Regime-Specific Alpha Model Foundation"
    assert payload["metadata"]["asset_count"] == 17
    assert payload["metadata"]["as_of"] <= payload["metadata"]["requested_as_of"]
    assert payload["metadata"]["model"] in {"trend_following", "rotation_alpha", "mean_reversion", "defensive_quality"}
    assert payload["constraints"]["router_driven_model"] is True
    assert payload["constraints"]["does_not_change_v3_2_score"] is True
    assert payload["constraints"]["no_allocation"] is True
    assert payload["constraints"]["no_trade_signal"] is True
    assert payload["constraints"]["no_backtest"] is True

    rows = payload["assets"]
    assert len(rows) == 17
    assert [row["rank"] for row in rows] == list(range(1, 18))
    for row in rows:
        assert 0.0 <= float(row["model_score"]) <= 100.0
        assert row["model"] == payload["metadata"]["model"]
        assert "components" in row
        assert "feature_snapshot" in row
        assert "weight" not in row
        assert "allocation" not in row


if __name__ == "__main__":
    test_alpha_model_engine()
    print("test_alpha_model_engine ok")
