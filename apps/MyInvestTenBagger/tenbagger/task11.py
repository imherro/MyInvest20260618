"""TASK 11 orchestration."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from tenbagger.anomaly import AnomalyRunResult, run_anomaly_pipeline
from tenbagger.config import DEFAULT_DATA_DIR, DEFAULT_REPORT_DIR


def run_task11(
    universe_level: str = "dev",
    data_dir: Path | str = DEFAULT_DATA_DIR,
    report_dir: Path | str = DEFAULT_REPORT_DIR,
) -> dict[str, Any]:
    result = run_anomaly_pipeline(data_dir=data_dir, universe_level=universe_level)
    report = _build_report(result)

    data_path = Path(data_dir) / "anomaly"
    data_path.mkdir(parents=True, exist_ok=True)
    result.daily.to_parquet(data_path / f"market_anomaly_daily_{universe_level}.parquet", index=False)
    result.daily.to_parquet(data_path / "market_anomaly_daily.parquet", index=False)

    report_path = Path(report_dir)
    report_path.mkdir(parents=True, exist_ok=True)
    (report_path / "task11_anomaly_summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_markdown(report, report_path / "TASK11_ANOMALY_REPORT.md")
    return report


def _build_report(result: AnomalyRunResult) -> dict[str, Any]:
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "task": "TASK 11 - Market Structural Anomaly Engine",
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
        "structural_break_prob": latest.get("structural_break_prob"),
        "correlation_break_prob": latest.get("correlation_break_prob"),
        "flow_shock_prob": latest.get("flow_shock_prob"),
        "behavioral_anomaly_score": latest.get("behavioral_anomaly_score"),
        "anomaly_score": latest.get("anomaly_score"),
        "systemic_risk_level": latest.get("systemic_risk_level"),
        "dominant_anomaly_type": latest.get("dominant_anomaly_type"),
        "anomaly_state": latest.get("anomaly_state"),
        "cross_sector_decoupling_prob": latest.get("cross_sector_decoupling_prob"),
        "liquidity_vacuum_prob": latest.get("liquidity_vacuum_prob"),
    }


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    latest = report["latest"]
    validation = report["validation"]
    lines = [
        "# TASK 11 Structural Anomaly Report",
        "",
        f"- Generated at: {report['generated_at']}",
        f"- Source: {report['source'].get('source')}",
        f"- Date range: {report['date_range']['start']} to {report['date_range']['end']}",
        f"- Row count: {report['row_count']}",
        "",
        "## Current Anomaly State",
        "",
        f"- Date: {latest.get('date')}",
        f"- Systemic risk level: {latest.get('systemic_risk_level')}",
        f"- Dominant anomaly type: {latest.get('dominant_anomaly_type')}",
        f"- Anomaly score: {latest.get('anomaly_score')}",
        f"- Structural break probability: {latest.get('structural_break_prob')}",
        f"- Correlation break probability: {latest.get('correlation_break_prob')}",
        f"- Flow shock probability: {latest.get('flow_shock_prob')}",
        f"- Behavioral anomaly score: {latest.get('behavioral_anomaly_score')}",
        "",
        "## Validation",
        "",
        f"- Walk-forward features only: {validation.get('walk_forward_features_only')}",
        f"- Uses future return labels: {validation.get('uses_future_return_labels')}",
        f"- Uses alpha model: {validation.get('uses_alpha_model')}",
        f"- Predicts market direction: {validation.get('predicts_market_direction')}",
        f"- Purely observational: {validation.get('purely_observational')}",
        f"- All scores bounded 0-1: {validation.get('all_scores_bounded_0_1')}",
        f"- Anomaly event frequency: {validation.get('anomaly_event_frequency')}",
        f"- High risk frequency: {validation.get('high_risk_frequency')}",
        f"- Recent 30D mean anomaly: {validation.get('recent_30d_mean_anomaly')}",
        "",
        "## Distribution",
        "",
    ]
    for key, values in report["history"].get("distribution", {}).items():
        lines.append(f"- {key}: {values}")
    lines.extend(["", "## Recent Anomaly Events", ""])
    events = report["history"].get("anomaly_events", [])
    if not events:
        lines.append("- No medium/high anomaly events in the latest 120 observations.")
    for row in events[-10:]:
        lines.append(
            "- {date}: state={anomaly_state}, score={anomaly_score}, risk={systemic_risk_level}".format(
                **row
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
