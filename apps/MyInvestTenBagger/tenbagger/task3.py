"""TASK 3 orchestration."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from tenbagger.alpha_validation import AlphaValidator
from tenbagger.config import DEFAULT_DATA_DIR, DEFAULT_REPORT_DIR
from tenbagger.factor_engine import FACTOR_COLUMNS, FactorEngine
from tenbagger.factor_storage import FactorStorage
from tenbagger.screener import HardFilter
from tenbagger.universe import UniverseManager


def run_task3(
    universe_level: str = "dev",
    data_dir: Path | str = DEFAULT_DATA_DIR,
    report_dir: Path | str = DEFAULT_REPORT_DIR,
) -> dict[str, Any]:
    universe = UniverseManager().resolve(universe_level)
    data_path = Path(data_dir)
    report_path = Path(report_dir)
    report_path.mkdir(parents=True, exist_ok=True)

    engine = FactorEngine()
    task1_data = engine.read_task1_parquet(data_path, universe=universe.codes)
    factors = engine.compute(task1_data)
    validation = engine.validate(factors)
    FactorStorage(data_path).write(factors)

    filtered = HardFilter().apply_filters(factors, latest_only=True)
    candidates = HardFilter.top_candidates(filtered, limit=20)
    near_misses = HardFilter.near_misses(filtered, limit=20)
    latest_factors = factors[factors["date"] == factors["date"].max()].copy()
    v2_ranked = latest_factors.sort_values(
        ["v2_eligible", "tenbagger_score_v2", "v2_confidence_score"],
        ascending=[False, False, False],
    )
    v2_candidates = v2_ranked[
        v2_ranked["v2_eligible"] & v2_ranked["v2_confidence_grade"].isin(["A", "B"])
    ].head(20)
    if v2_candidates.empty:
        v2_candidates = v2_ranked.head(20)

    screener_dir = data_path / "screener"
    screener_dir.mkdir(parents=True, exist_ok=True)
    candidates.to_parquet(screener_dir / "latest_candidates.parquet", index=False)
    filtered.to_parquet(screener_dir / "latest_filter_diagnostics.parquet", index=False)

    alpha = AlphaValidator()
    enriched = alpha.attach_forward_returns(factors, task1_data)
    ic_summary = alpha.ic_summary(enriched)
    ic_decay = alpha.ic_decay_curve(enriched)
    v2_ic_decay = alpha.ic_decay_curve(enriched, factor="tenbagger_score_v2")
    preview = alpha.backtest_preview(enriched)
    v2_preview = alpha.backtest_preview(enriched, factor="tenbagger_score_v2")

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "task": "TASK 3 - Screener and alpha validation",
        "universe": universe.to_api(),
        "stock_count": int(factors["ts_code"].nunique()),
        "row_count": int(len(factors)),
        "latest_trading_date": str(factors["date"].max()),
        "factor_validation": asdict(validation),
        "candidate_count": int(len(candidates)),
        "hard_filter_config": asdict(HardFilter().config),
        "top_candidates": _records(candidates, FACTOR_COLUMNS + ["industry", "revenue_growth_yoy", "roe", "debt_ratio", "max_drawdown_120d"]),
        "near_misses": _records(near_misses, FACTOR_COLUMNS + ["industry", "revenue_growth_yoy", "roe", "debt_ratio", "max_drawdown_120d", "fail_reasons"]),
        "model_v2_summary": {
            "candidate_count": int(len(v2_candidates)),
            "eligible_count": int(latest_factors["v2_eligible"].fillna(False).sum()),
            "eligible_rate": float(latest_factors["v2_eligible"].fillna(False).mean()) if not latest_factors.empty else 0.0,
            "grade_distribution": {
                str(key): int(value)
                for key, value in latest_factors["v2_confidence_grade"].value_counts().to_dict().items()
            },
            "latest_market_regime": str(latest_factors["v2_market_regime"].dropna().iloc[0])
            if not latest_factors["v2_market_regime"].dropna().empty
            else "unknown",
            "latest_volatility_regime": str(latest_factors["v2_volatility_regime"].dropna().iloc[0])
            if not latest_factors["v2_volatility_regime"].dropna().empty
            else "unknown",
        },
        "v2_top_candidates": _records(
            v2_candidates,
            [
                "ts_code",
                "date",
                "tenbagger_score",
                "tenbagger_score_v2",
                "v2_confidence_grade",
                "v2_confidence_score",
                "v2_eligible",
                "v2_fail_reasons",
                "v2_growth_persistence_score",
                "v2_quality_durability_score",
                "v2_industry_relative_score",
                "v2_risk_control_score",
                "v2_momentum_score",
                "v2_market_state_score",
                "v2_weight_profile",
                "industry",
                "revenue_growth_yoy",
                "roe",
                "debt_ratio",
            ],
        ),
        "ic_summary": ic_summary,
        "ic_decay_curve": ic_decay,
        "v2_ic_decay_curve": v2_ic_decay,
        "backtest_preview": asdict(preview),
        "v2_backtest_preview": asdict(v2_preview),
    }

    (report_path / "task3_screener_summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_markdown(report, report_path / "task3_screener_summary.md")
    return report


def _records(df: pd.DataFrame, columns: list[str]) -> list[dict[str, Any]]:
    if df.empty:
        return []
    existing = [column for column in columns if column in df.columns]
    records = df[existing].head(20).to_dict(orient="records")
    clean = []
    for row in records:
        clean.append({key: None if pd.isna(value) else value for key, value in row.items()})
    return clean


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# TASK 3 Screener Report",
        "",
        f"- Generated at: {report['generated_at']}",
        f"- Stock count: {report['stock_count']}",
        f"- Row count: {report['row_count']}",
        f"- Latest trading date: {report['latest_trading_date']}",
        f"- Candidate count: {report['candidate_count']}",
        f"- Future leak rows: {report['factor_validation']['future_leak_rows']}",
        f"- NaN score cells: {report['factor_validation']['nan_cells']}",
        "",
        "## Top Candidates",
        "",
    ]
    if report["top_candidates"]:
        for row in report["top_candidates"]:
            lines.append(
                "- {ts_code}: score={tenbagger_score:.2f}, growth={growth_score:.2f}, quality={quality_score:.2f}, industry={industry_score:.2f}".format(
                    **row
                )
            )
    else:
        lines.append("- No stock passed all hard filters in the current universe.")

    lines.extend(["", "## Backtest Preview", ""])
    preview = report["backtest_preview"]
    for key in ["top_decile_return", "benchmark_return", "excess_return", "max_drawdown", "observations"]:
        lines.append(f"- {key}: {preview[key]}")

    lines.extend(["", "## IC Decay", ""])
    for item in report["ic_decay_curve"]:
        lines.append(
            "- {horizon_days}d: IC={ic_mean:.4f}, RankIC={rank_ic_mean:.4f}, observations={observations}".format(
                **item
            )
        )
    lines.extend(["", "## Model V2", ""])
    summary = report["model_v2_summary"]
    lines.extend(
        [
            f"- V2 candidate count: {summary['candidate_count']}",
            f"- V2 eligible count: {summary['eligible_count']}",
            f"- V2 eligible rate: {summary['eligible_rate']:.2%}",
            f"- Latest market regime: {summary['latest_market_regime']}",
            f"- Latest volatility regime: {summary['latest_volatility_regime']}",
            "",
            "## V2 Top Candidates",
            "",
        ]
    )
    for row in report["v2_top_candidates"][:10]:
        lines.append(
            "- {ts_code}: v2={tenbagger_score_v2:.2f}, grade={v2_confidence_grade}, profile={v2_weight_profile}, v1={tenbagger_score:.2f}".format(
                **row
            )
        )
    lines.extend(["", "## V2 IC Decay", ""])
    for item in report["v2_ic_decay_curve"]:
        lines.append(
            "- {horizon_days}d: IC={ic_mean:.4f}, RankIC={rank_ic_mean:.4f}, observations={observations}".format(
                **item
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
