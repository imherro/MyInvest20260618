"""TASK 9 orchestration."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from tenbagger.behavior import BehaviorRunResult, run_behavior_pipeline
from tenbagger.config import DEFAULT_DATA_DIR, DEFAULT_REPORT_DIR


def run_task9(
    universe_level: str = "dev",
    data_dir: Path | str = DEFAULT_DATA_DIR,
    report_dir: Path | str = DEFAULT_REPORT_DIR,
) -> dict[str, Any]:
    result = run_behavior_pipeline(data_dir=data_dir, universe_level=universe_level)
    report = _build_report(result)

    data_path = Path(data_dir) / "behavior"
    data_path.mkdir(parents=True, exist_ok=True)
    result.daily.to_parquet(data_path / f"market_behavior_daily_{universe_level}.parquet", index=False)
    result.daily.to_parquet(data_path / "market_behavior_daily.parquet", index=False)

    report_path = Path(report_dir)
    report_path.mkdir(parents=True, exist_ok=True)
    (report_path / "task9_behavior_summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_markdown(report, report_path / "TASK9_BEHAVIOR_REPORT.md")
    return report


def _build_report(result: BehaviorRunResult) -> dict[str, Any]:
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "task": "TASK 9 - Market Behavior & Flow Engine",
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
        "retail_pressure": latest.get("dominant_actor"),
        "retail_pressure_index": latest.get("retail_pressure_index"),
        "institutional_flow": latest.get("institutional_flow_index"),
        "panic_index": latest.get("panic_index"),
        "fomo_index": latest.get("fomo_index"),
        "crowding_level": latest.get("crowding_level"),
        "positioning_crowdedness": latest.get("positioning_crowdedness"),
        "reversal_risk": latest.get("reversal_risk"),
        "flow_price_divergence": latest.get("flow_price_divergence"),
        "behavior_overlay_state": latest.get("behavior_overlay_state"),
        "joint_regime_behavior": latest.get("joint_regime_behavior"),
    }


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    latest = report["latest"]
    validation = report["validation"]
    lines = [
        "# TASK 9 Market Behavior Report",
        "",
        f"- Generated at: {report['generated_at']}",
        f"- Source: {report['source'].get('source')}",
        f"- Date range: {report['date_range']['start']} to {report['date_range']['end']}",
        f"- Row count: {report['row_count']}",
        "",
        "## Current Market Behavior",
        "",
        f"- Date: {latest.get('date')}",
        f"- Dominant actor: {latest.get('dominant_actor')}",
        f"- Retail pressure index: {latest.get('retail_pressure_index')}",
        f"- Institutional flow index: {latest.get('institutional_flow_index')}",
        f"- Panic index: {latest.get('panic_index')}",
        f"- FOMO index: {latest.get('fomo_index')}",
        f"- Crowding level: {latest.get('crowding_level')}",
        f"- Flow-price divergence: {latest.get('flow_price_divergence')}",
        f"- Joint regime behavior: {latest.get('joint_regime_behavior')}",
        "",
        "## Validation",
        "",
        f"- Walk-forward features only: {validation.get('walk_forward_features_only')}",
        f"- Uses future return labels: {validation.get('uses_future_return_labels')}",
        f"- Uses factor alpha: {validation.get('uses_factor_alpha')}",
        f"- All scores bounded 0-1: {validation.get('all_scores_bounded_0_1')}",
        f"- Overlay autocorrelation: {validation.get('overlay_autocorrelation')}",
        f"- Behavior transition frequency: {validation.get('behavior_transition_frequency')}",
        f"- Divergence event frequency: {validation.get('divergence_event_frequency')}",
        f"- Recent 30D mean panic: {validation.get('recent_30d_mean_panic')}",
        f"- Recent 30D mean FOMO: {validation.get('recent_30d_mean_fomo')}",
        "",
        "## Distribution",
        "",
    ]
    for key, values in report["history"].get("distribution", {}).items():
        lines.append(f"- {key}: {values}")
    lines.extend(["", "## Recent Divergence Events", ""])
    events = report["history"].get("divergence_events", [])
    if not events:
        lines.append("- No flow-price divergence events in the latest 120 observations.")
    for row in events[-10:]:
        lines.append(
            "- {date}: divergence={flow_price_divergence}, score={divergence_score}, actor={dominant_actor}, overlay={behavior_overlay_state}".format(
                **row
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
