from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adaptive_exposure.exposure_context_score import exposure_context_scores, score_bucket
from adaptive_exposure.exposure_context_score_audit import (
    build_exposure_context_score_audit,
    write_exposure_context_score_audit,
)


def main() -> None:
    payload = build_exposure_context_score_audit()
    summary = payload["summary"]
    separation = payload["separation_review"]
    time_safety = payload["time_safety"]
    data_quality = payload["data_quality"]
    constraints = payload["constraints"]

    assert payload["metadata"]["engine"] == "V6.3 Continuous Exposure Context Score Audit"
    assert summary["joined_sample_count"] == 115
    assert summary["score_coverage"]["participation_score"]["available_count"] == 115
    assert summary["score_coverage"]["protection_score"]["available_count"] == 115
    assert summary["ready_for_mapper_change"] is False
    assert summary["ready_for_exposure_change"] is False
    assert summary["conclusion"] == "continuous_context_scores_not_validated"
    assert separation["protection_separation"] in {"weak", "visible"}
    assert separation["participation_separation"] in {"weak", "visible"}

    sample = exposure_context_scores(
        {
            "risk_gradient_score": 70,
            "analysis_context": {
                "opportunity_state": "BULL_EXPANSION",
                "market_phase": "EXPANSION",
                "risk_state": "CROWDED",
                "macro_score": 70,
                "trend_score": 65,
                "breadth_score": 62,
                "liquidity_score": 60,
                "industry_breadth": 55,
                "theme_persistence": 50,
                "price_extension_proxy": 70,
            },
        }
    )
    assert sample["research_only"] is True
    assert score_bucket(sample["participation_score"]) in {"high", "medium", "low"}
    assert score_bucket(sample["protection_score"]) in {"high", "medium", "low"}

    assert time_safety["feature_release_or_source_lte_signal_date"] is True
    assert time_safety["violation_count"] == 0
    assert data_quality["continuous_scores_are_research_only"] is True
    assert data_quality["no_parameter_optimization"] is True
    assert constraints["does_not_modify_mapper"] is True
    assert constraints["does_not_modify_exposure_level"] is True
    assert constraints["does_not_generate_position"] is True
    assert constraints["no_etf_code"] is True
    assert constraints["no_trade_signal"] is True

    with tempfile.TemporaryDirectory() as tmpdir:
        output = write_exposure_context_score_audit(payload, Path(tmpdir) / "exposure_context_score_audit.json")
        assert output.exists()

    print("test_exposure_context_score ok")


if __name__ == "__main__":
    main()
