"""TASK 1 validation reporting."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from tenbagger.schema import STANDARD_COLUMNS


def _json_safe(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def build_task1_report(
    df: pd.DataFrame,
    storage: dict[str, Any],
    report_dir: Path | str,
) -> dict[str, Any]:
    """Build and persist the TASK 1 report required by the design document."""

    if df.empty:
        raise ValueError("Cannot build TASK 1 report from an empty dataframe.")

    report_path = Path(report_dir)
    report_path.mkdir(parents=True, exist_ok=True)

    stock_stats = []
    required_for_completeness = [
        "open",
        "high",
        "low",
        "close",
        "revenue",
        "net_profit",
        "roe",
        "pe",
        "pb",
        "market_cap",
    ]

    for ts_code, stock_df in df.groupby("ts_code", sort=True):
        non_null = stock_df[required_for_completeness].notna().mean().mean()
        stock_stats.append(
            {
                "ts_code": ts_code,
                "rows": int(len(stock_df)),
                "start_date": str(stock_df["date"].min()),
                "end_date": str(stock_df["date"].max()),
                "coverage_ratio": round(float(non_null), 4),
            }
        )

    missing_rates = {
        column: round(float(df[column].isna().mean()), 4)
        for column in STANDARD_COLUMNS
        if column in df.columns
    }

    latest_date = str(df["date"].max())
    latest_snapshot = (
        df[df["date"] == latest_date]
        .sort_values("ts_code")
        .head(20)
        .loc[:, [column for column in STANDARD_COLUMNS if column in df.columns]]
    )

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "task": "TASK 1 - data layer and stock universe construction",
        "stock_count": int(df["ts_code"].nunique()),
        "row_count": int(len(df)),
        "date_range": {
            "start": str(df["date"].min()),
            "end": str(df["date"].max()),
        },
        "stock_coverage": stock_stats,
        "missing_rates": missing_rates,
        "latest_trading_date": latest_date,
        "latest_snapshot": [
            {key: _json_safe(value) for key, value in row.items()}
            for row in latest_snapshot.to_dict(orient="records")
        ],
        "storage": storage,
    }

    (report_path / "task1_summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    markdown = [
        "# TASK 1 Report",
        "",
        f"- Generated at: {report['generated_at']}",
        f"- Stock count: {report['stock_count']}",
        f"- Row count: {report['row_count']}",
        f"- Date range: {report['date_range']['start']} to {report['date_range']['end']}",
        f"- Latest trading date: {report['latest_trading_date']}",
        "",
        "## Missing Rates",
        "",
    ]
    for column, rate in missing_rates.items():
        markdown.append(f"- {column}: {rate:.2%}")

    markdown.extend(["", "## Stock Coverage", ""])
    for item in stock_stats:
        markdown.append(
            "- {ts_code}: {rows} rows, {start_date} to {end_date}, coverage {coverage_ratio:.2%}".format(
                **item
            )
        )

    (report_path / "task1_summary.md").write_text(
        "\n".join(markdown) + "\n",
        encoding="utf-8",
    )
    return report
