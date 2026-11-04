"""TASK 8 orchestration."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from tenbagger.config import DEFAULT_DATA_DIR, DEFAULT_REPORT_DIR
from tenbagger.regime import RegimeRunResult, run_market_regime_pipeline


def run_task8(
    universe_level: str = "dev",
    data_dir: Path | str = DEFAULT_DATA_DIR,
    report_dir: Path | str = DEFAULT_REPORT_DIR,
    refresh_index: bool = False,
) -> dict[str, Any]:
    result = run_market_regime_pipeline(
        data_dir=data_dir,
        refresh_index=refresh_index,
        universe_level=universe_level,
    )
    report = _build_report(result)

    data_path = Path(data_dir) / "regime"
    data_path.mkdir(parents=True, exist_ok=True)
    result.daily.to_parquet(data_path / f"market_regime_daily_{universe_level}.parquet", index=False)
    result.daily.to_parquet(data_path / "market_regime_daily.parquet", index=False)

    report_path = Path(report_dir)
    report_path.mkdir(parents=True, exist_ok=True)
    (report_path / "task8_regime_summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_markdown(report, report_path / "TASK8_REGIME_REPORT.md")
    return report


def _build_report(result: RegimeRunResult) -> dict[str, Any]:
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "task": "TASK 8 - Market Regime & Behavioral State Engine",
        "universe": result.data_source.get("universe", {}),
        "latest": result.latest,
        "api_response": _api_response(result.latest),
        "validation": result.validation,
        "history": result.history,
        "data_source": result.data_source,
        "row_count": int(len(result.daily)),
        "date_range": {
            "start": str(result.daily["date"].min().date()) if not result.daily.empty else None,
            "end": str(result.daily["date"].max().date()) if not result.daily.empty else None,
        },
    }


def _api_response(latest: dict[str, Any]) -> dict[str, Any]:
    return {
        "date": latest.get("date"),
        "trend_regime": latest.get("trend_regime"),
        "volatility_regime": latest.get("volatility_regime"),
        "liquidity_regime": latest.get("liquidity_regime"),
        "behavior_state": latest.get("behavior_state"),
        "regime_change_probability": latest.get("regime_change_probability"),
        "stability_score": latest.get("stability_score"),
        "trend_strength": latest.get("trend_strength"),
        "volatility_percentile": latest.get("volatility_percentile"),
        "liquidity_score": latest.get("liquidity_score"),
    }


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    latest = report["latest"]
    validation = report["validation"]
    lines = [
        "# TASK 8 Market Regime Report",
        "",
        f"- Generated at: {report['generated_at']}",
        f"- Data source: {report['data_source'].get('source')}",
        f"- Date range: {report['date_range']['start']} to {report['date_range']['end']}",
        f"- Row count: {report['row_count']}",
        "",
        "## Current Regime",
        "",
        f"- Date: {latest.get('date')}",
        f"- Trend regime: {latest.get('trend_regime')}",
        f"- Volatility regime: {latest.get('volatility_regime')}",
        f"- Liquidity regime: {latest.get('liquidity_regime')}",
        f"- Behavior state: {latest.get('behavior_state')}",
        f"- Regime change probability: {latest.get('regime_change_probability')}",
        f"- Stability score: {latest.get('stability_score')}",
        "",
        "## Validation",
        "",
        f"- Walk-forward features only: {validation.get('walk_forward_features_only')}",
        f"- Uses future return labels: {validation.get('uses_future_return_labels')}",
        f"- Regime autocorrelation: {validation.get('regime_autocorrelation')}",
        f"- Transition frequency: {validation.get('transition_frequency')}",
        f"- Recent 30D transition frequency: {validation.get('recent_30d_transition_frequency')}",
        f"- Mean duration days: {validation.get('mean_duration_days')}",
        f"- Transition not overfit: {validation.get('transition_not_overfit')}",
        f"- Regime has continuity: {validation.get('regime_has_continuity')}",
        "",
        "## Historical Distribution",
        "",
    ]
    for key, values in report["history"].get("distribution", {}).items():
        lines.append(f"- {key}: {values}")
    lines.extend(["", "## Recent 30D Changes", ""])
    changes = report["history"].get("recent_30_changes", [])
    if not changes:
        lines.append("- No regime changes in the latest 30 observations.")
    for row in changes:
        lines.append(
            "- {date}: trend={trend_regime}, vol={volatility_regime}, liquidity={liquidity_regime}, behavior={behavior_state}".format(
                **row
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
