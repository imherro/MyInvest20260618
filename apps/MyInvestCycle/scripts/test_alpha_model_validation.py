from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from asset_opportunity.alpha_model_validation import MODEL_NAMES, build_alpha_model_validation


def test_alpha_model_validation() -> None:
    payload = build_alpha_model_validation(start_date="20150105", end_date="20260708", step_sessions=60)
    assert payload["metadata"]["engine"] == "V3.3.3 Regime Alpha Model Validation Engine"
    assert payload["metadata"]["score_date_count"] > 0
    assert tuple(payload["metadata"]["models"]) == MODEL_NAMES
    assert payload["constraints"]["walk_forward"] is True
    assert payload["constraints"]["model_formulas_frozen"] is True
    assert payload["constraints"]["no_parameter_optimization"] is True
    assert payload["constraints"]["no_allocation"] is True
    assert payload["constraints"]["no_trade_signal"] is True
    assert payload["constraints"]["no_backtest_portfolio"] is True

    for section in ("research_proxy_validation", "tradable_etf_validation"):
        by_model = payload[section]["by_model"]
        assert set(by_model) == set(MODEL_NAMES)
        for model_name in MODEL_NAMES:
            assert set(by_model[model_name]) == {"5d", "20d", "60d"}
            assert by_model[model_name]["20d"]
        assert payload[section]["router_selected"]


if __name__ == "__main__":
    test_alpha_model_validation()
    print("test_alpha_model_validation ok")
