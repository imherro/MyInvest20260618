"""TASK 7 orchestration."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from tenbagger.config import DEFAULT_DATA_DIR, DEFAULT_REPORT_DIR
from tenbagger.optimization import load_optimization_inputs
from tenbagger.structural_validation import StructuralAlphaValidator
from tenbagger.universe import UniverseManager


def run_task7(
    universe_level: str = "dev",
    data_dir: Path | str = DEFAULT_DATA_DIR,
    report_dir: Path | str = DEFAULT_REPORT_DIR,
) -> dict[str, Any]:
    universe = UniverseManager().resolve(universe_level)
    factors, prices = load_optimization_inputs(data_dir, universe=universe.codes)
    result = StructuralAlphaValidator(top_k=10).run(factors, prices)
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "task": "TASK 7 - Structural Alpha Validation Layer",
        "universe": universe.to_api(),
        "model_provenance": {
            "model_version": "v1",
            "score_column": "tenbagger_score",
            "note": "Structural validation currently validates the legacy V1 score column.",
        },
        **asdict(result),
    }

    report_path = Path(report_dir)
    report_path.mkdir(parents=True, exist_ok=True)
    (report_path / "task7_structural_validation_summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_markdown(report, report_path / "task7_structural_validation_summary.md")
    return report


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    criteria = report["criteria"]
    failure = report["failure_mode_diagnosis"]
    metrics = report["oos_metrics"]
    lines = [
        "# TASK 7 Structural Alpha Validation Report",
        "",
        f"- Generated at: {report['generated_at']}",
        f"- OOS split date: {report['split_date']}",
        f"- Alpha classification: {report['classification']}",
        f"- OOS Sharpe: {metrics['sharpe']:.4f}",
        f"- OOS annual return: {metrics['annual_return']:.4f}",
        f"- OOS max drawdown: {metrics['max_drawdown']:.4f}",
        f"- Actual 21D RankIC: {criteria['actual_rank_ic_21d']:.4f}",
        f"- Primary failure: {failure['primary_failure']}",
        "",
        "## Real Alpha Criteria",
        "",
    ]
    for key, value in criteria.items():
        lines.append(f"- {key}: {value}")

    lines.extend(["", "## Randomization Test", ""])
    randomization = report["randomization_test"]
    for key in ["label_shuffle", "feature_permutation"]:
        summary = randomization[key]
        lines.append(
            f"- {key}: mean={summary['mean']:.4f}, p95={summary['p95']:.4f}, p_value={summary['p_value']:.4f}, significant={summary['significant']}"
        )

    lines.extend(["", "## Stability", ""])
    stability = report["stability_report"]
    for key in ["score", "ic_variance", "sharpe_variance", "positive_sharpe_ratio", "decay_slow"]:
        lines.append(f"- {key}: {stability[key]}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
