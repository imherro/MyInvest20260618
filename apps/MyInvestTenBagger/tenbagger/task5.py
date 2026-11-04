"""TASK 5 orchestration."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from tenbagger.config import DEFAULT_DATA_DIR, DEFAULT_REPORT_DIR
from tenbagger.optimization import FactorWeightOptimizer, load_optimization_inputs
from tenbagger.universe import UniverseManager


def run_task5(
    universe_level: str = "dev",
    data_dir: Path | str = DEFAULT_DATA_DIR,
    report_dir: Path | str = DEFAULT_REPORT_DIR,
) -> dict[str, Any]:
    universe = UniverseManager().resolve(universe_level)
    factors, prices = load_optimization_inputs(data_dir, universe=universe.codes)
    result = FactorWeightOptimizer(step=0.25, top_k=10).optimize(factors, prices)

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "task": "TASK 5 - Factor Optimization and Alpha Improvement",
        "universe": universe.to_api(),
        "model_provenance": {
            "model_version": "v1_optimized",
            "score_column": "tenbagger_score",
            "note": "Optimization rewrites the legacy V1 score from component scores.",
        },
        "candidates_evaluated": result.candidates_evaluated,
        "best_weights": result.best_weights,
        "train_metrics": result.train_metrics,
        "test_metrics": result.test_metrics,
        "baseline_test_metrics": result.baseline_test_metrics,
        "optimized_full_metrics": result.optimized_full_metrics,
        "baseline_full_metrics": result.baseline_full_metrics,
        "ic_comparison": result.ic_comparison,
        "regime_analysis": result.regime_analysis,
    }

    report_path = Path(report_dir)
    report_path.mkdir(parents=True, exist_ok=True)
    (report_path / "task5_optimization_summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_markdown(report, report_path / "task5_optimization_summary.md")
    return report


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# TASK 5 Optimization Report",
        "",
        f"- Generated at: {report['generated_at']}",
        f"- Candidates evaluated: {report['candidates_evaluated']}",
        f"- Best weights: {report['best_weights']}",
        "",
        "## Test Metrics",
        "",
    ]
    for label, metrics in [
        ("baseline", report["baseline_test_metrics"]),
        ("optimized", report["test_metrics"]),
    ]:
        lines.append(
            f"- {label}: annual_return={metrics['annual_return']:.4f}, sharpe={metrics['sharpe']:.4f}, max_drawdown={metrics['max_drawdown']:.4f}"
        )
    lines.extend(["", "## IC Comparison", ""])
    for key, value in report["ic_comparison"].items():
        lines.append(
            f"- {key}: baseline_rank_ic={value['baseline_rank_ic']:.4f}, optimized_rank_ic={value['optimized_rank_ic']:.4f}, delta={value['delta']:.4f}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
