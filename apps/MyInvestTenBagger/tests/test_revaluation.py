from __future__ import annotations

import json
from pathlib import Path

from tenbagger.revaluation import REEVALUATION_JSON, REEVALUATION_MARKDOWN, run_universe_revaluation


def _write_reports(root: Path, level: str, universe_size: int, candidate_count: int, rank_ic: float) -> None:
    report_dir = root / "universe" / level
    report_dir.mkdir(parents=True, exist_ok=True)
    candidates = [
        {"ts_code": f"{idx:06d}.SZ", "industry": "tech" if idx % 2 else "health"}
        for idx in range(candidate_count)
    ]
    task3 = {
        "universe": {"level": level, "stock_count": universe_size},
        "stock_count": universe_size,
        "candidate_count": candidate_count,
        "top_candidates": candidates,
        "ic_summary": {
            "tenbagger_score_21d": {
                "ic_mean": rank_ic / 2,
                "ic_std": 0.20,
                "rank_ic_mean": rank_ic,
                "rank_ic_std": 0.25,
                "observations": 120,
            },
            "tenbagger_score_63d": {
                "ic_mean": rank_ic / 3,
                "ic_std": 0.18,
                "rank_ic_mean": rank_ic * 0.8,
                "rank_ic_std": 0.22,
                "observations": 100,
            },
        },
    }
    task7 = {
        "classification": "NO ALPHA",
        "criteria": {"actual_rank_ic_21d": rank_ic},
    }
    task8 = {
        "validation": {
            "regime_autocorrelation": 0.80 + rank_ic,
            "transition_frequency": 0.15 - rank_ic / 2,
        }
    }
    (report_dir / "task3_screener_summary.json").write_text(json.dumps(task3), encoding="utf-8")
    (report_dir / "task7_structural_validation_summary.json").write_text(json.dumps(task7), encoding="utf-8")
    (report_dir / "task8_regime_summary.json").write_text(json.dumps(task8), encoding="utf-8")


def test_universe_revaluation_compares_report_sets(tmp_path: Path) -> None:
    _write_reports(tmp_path, "dev", universe_size=50, candidate_count=5, rank_ic=0.02)
    _write_reports(tmp_path, "research", universe_size=500, candidate_count=12, rank_ic=0.08)

    result = run_universe_revaluation(report_root=tmp_path, output_dir=tmp_path)

    assert result["status"] == "complete"
    assert result["rankic_shift"]["mean_abs_delta"] > 0
    assert result["candidate_density_shift"]["old_density"] == 0.1
    assert result["candidate_density_shift"]["new_density"] == 0.024
    assert 0 <= result["structural_drift_score"] <= 1
    assert (tmp_path / REEVALUATION_JSON).exists()
    assert (tmp_path / REEVALUATION_MARKDOWN).exists()


def test_universe_revaluation_reports_missing_inputs(tmp_path: Path) -> None:
    _write_reports(tmp_path, "dev", universe_size=50, candidate_count=5, rank_ic=0.02)

    result = run_universe_revaluation(report_root=tmp_path, output_dir=tmp_path)

    assert result["status"] == "insufficient_data"
    assert result["structural_drift_score"] == 0.0
    assert "task3_screener_summary.json" in result["target"]["missing_reports"]


def test_revaluation_does_not_import_optimization_code() -> None:
    source = Path("tenbagger/revaluation.py").read_text(encoding="utf-8")

    assert "FactorWeightOptimizer" not in source
    assert "optimize(" not in source
