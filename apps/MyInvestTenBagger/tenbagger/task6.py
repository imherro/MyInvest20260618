"""TASK 6 orchestration."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from tenbagger.config import DEFAULT_DATA_DIR, DEFAULT_REPORT_DIR
from tenbagger.monetization import MonetizationOptimizer
from tenbagger.optimization import load_optimization_inputs
from tenbagger.universe import UniverseManager


def run_task6(
    universe_level: str = "dev",
    data_dir: Path | str = DEFAULT_DATA_DIR,
    report_dir: Path | str = DEFAULT_REPORT_DIR,
) -> dict[str, Any]:
    universe = UniverseManager().resolve(universe_level)
    factors, prices = load_optimization_inputs(data_dir, universe=universe.codes)
    # Use the latest TASK 5 stable IC weights as the signal input.
    weights = {
        "growth_score": 0.0,
        "quality_score": 0.0,
        "value_score": 0.0,
        "industry_score": 0.0,
        "momentum_score": 0.5,
        "risk_score": 0.5,
    }
    result = MonetizationOptimizer(top_k=10).run(factors, prices, weights)
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "task": "TASK 6 - Alpha Monetization Layer",
        "universe": universe.to_api(),
        "model_provenance": {
            "model_version": "v1_optimized",
            "score_column": "tenbagger_score",
            "note": "Monetization layer consumes optimized legacy V1 component scores.",
        },
        "input_weights": weights,
        "best_config": result.best_config,
        "train_metrics": result.train_metrics,
        "test_metrics": result.test_metrics,
        "turnover_sharpe_curve": result.turnover_sharpe_curve,
        "cost_sensitivity": result.cost_sensitivity,
        "alpha_decay": result.alpha_decay,
        "payoff_report": result.payoff_report,
        "ic_pnl_divergence": result.ic_pnl_divergence,
    }

    report_path = Path(report_dir)
    report_path.mkdir(parents=True, exist_ok=True)
    (report_path / "task6_monetization_summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_markdown(report, report_path / "task6_monetization_summary.md")
    return report


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# TASK 6 Monetization Report",
        "",
        f"- Generated at: {report['generated_at']}",
        f"- Best config: {report['best_config']}",
        f"- Test annual return: {report['test_metrics']['annual_return']:.4f}",
        f"- Test Sharpe: {report['test_metrics']['sharpe']:.4f}",
        f"- Test max drawdown: {report['test_metrics']['max_drawdown']:.4f}",
        f"- Divergence: {report['ic_pnl_divergence']['interpretation']}",
        "",
        "## Cost Sensitivity",
        "",
    ]
    for row in report["cost_sensitivity"]:
        lines.append(
            f"- cost={row['transaction_cost_rate']}: sharpe={row['sharpe']:.4f}, annual={row['annual_return']:.4f}, turnover={row['turnover_rate']:.4f}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
