"""TASK 10 orchestration."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from tenbagger.config import DEFAULT_DATA_DIR, DEFAULT_REPORT_DIR
from tenbagger.structure import StructureRunResult, run_structure_pipeline


def run_task10(
    universe_level: str = "dev",
    data_dir: Path | str = DEFAULT_DATA_DIR,
    report_dir: Path | str = DEFAULT_REPORT_DIR,
) -> dict[str, Any]:
    result = run_structure_pipeline(data_dir=data_dir, universe_level=universe_level)
    report = _build_report(result)

    data_path = Path(data_dir) / "structure"
    data_path.mkdir(parents=True, exist_ok=True)
    result.daily.to_parquet(data_path / f"market_structure_daily_{universe_level}.parquet", index=False)
    result.daily.to_parquet(data_path / "market_structure_daily.parquet", index=False)

    report_path = Path(report_dir)
    report_path.mkdir(parents=True, exist_ok=True)
    (report_path / "task10_structure_summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_markdown(report, report_path / "TASK10_STRUCTURE_REPORT.md")
    return report


def _build_report(result: StructureRunResult) -> dict[str, Any]:
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "task": "TASK 10 - Market Structure Decomposition Engine",
        "universe": result.source.get("universe", {}),
        "latest": result.latest,
        "api_response": _api_response(result.latest),
        "validation": result.validation,
        "history": result.history,
        "source": result.source,
        "row_count": int(len(result.daily)),
        "date_range": {
            "start": str(result.daily["date"].min().date()) if not result.daily.empty else None,
            "end": str(result.daily["date"].max().date()) if not result.daily.empty else None,
        },
    }


def _api_response(latest: dict[str, Any]) -> dict[str, Any]:
    return {
        "date": latest.get("date"),
        "trend_component": latest.get("trend_component"),
        "flow_component": latest.get("flow_component"),
        "volatility_component": latest.get("volatility_component"),
        "noise_component": latest.get("noise_component"),
        "market_dispersion": latest.get("market_dispersion"),
        "correlation_regime": latest.get("correlation_regime"),
        "cross_sectional_correlation": latest.get("cross_sectional_correlation"),
        "structure_state": latest.get("structure_state"),
        "structural_shock_probability": latest.get("structural_shock_probability"),
        "structural_shock_type": latest.get("structural_shock_type"),
        "regime_behavior_structure": latest.get("regime_behavior_structure"),
    }


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    latest = report["latest"]
    validation = report["validation"]
    lines = [
        "# TASK 10 Market Structure Report",
        "",
        f"- Generated at: {report['generated_at']}",
        f"- Source: {report['source'].get('source')}",
        f"- Date range: {report['date_range']['start']} to {report['date_range']['end']}",
        f"- Row count: {report['row_count']}",
        "",
        "## Current Structure State",
        "",
        f"- Date: {latest.get('date')}",
        f"- Structure state: {latest.get('structure_state')}",
        f"- Correlation regime: {latest.get('correlation_regime')}",
        f"- Market dispersion: {latest.get('market_dispersion')}",
        f"- Structural shock probability: {latest.get('structural_shock_probability')}",
        f"- Structural shock type: {latest.get('structural_shock_type')}",
        f"- Regime behavior structure: {latest.get('regime_behavior_structure')}",
        "",
        "## Return Decomposition",
        "",
        f"- Trend component: {latest.get('trend_component')}",
        f"- Flow component: {latest.get('flow_component')}",
        f"- Volatility component: {latest.get('volatility_component')}",
        f"- Noise component: {latest.get('noise_component')}",
        "",
        "## Validation",
        "",
        f"- Walk-forward features only: {validation.get('walk_forward_features_only')}",
        f"- Uses future return labels: {validation.get('uses_future_return_labels')}",
        f"- Uses alpha factors: {validation.get('uses_alpha_factors')}",
        f"- Purely observational: {validation.get('purely_observational')}",
        f"- Components sum to one: {validation.get('components_sum_to_one')}",
        f"- All scores bounded 0-1: {validation.get('all_scores_bounded_0_1')}",
        f"- Structure autocorrelation: {validation.get('structure_autocorrelation')}",
        f"- Structure transition frequency: {validation.get('structure_transition_frequency')}",
        f"- Shock event frequency: {validation.get('shock_event_frequency')}",
        "",
        "## Distribution",
        "",
    ]
    for key, values in report["history"].get("distribution", {}).items():
        lines.append(f"- {key}: {values}")
    lines.extend(["", "## Structural Shocks", ""])
    shocks = report["history"].get("structural_shocks", [])
    if not shocks:
        lines.append("- No structural shock event in the latest 120 observations.")
    for row in shocks[-10:]:
        lines.append(
            "- {date}: type={structural_shock_type}, probability={structural_shock_probability}, state={structure_state}".format(
                **row
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
