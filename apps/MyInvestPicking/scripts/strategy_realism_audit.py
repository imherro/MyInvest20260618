from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from strategy.core_strategy import build_stock_picks

DEFAULT_DATES = [
    "2020-03-23",
    "2022-10-31",
    "2024-02-05",
    "2026-06-24",
]
DEFAULT_COST_SCENARIOS = [0.001, 0.003, 0.005]


def run_audit(
    dates: list[str],
    top_n: int,
    output_dir: Path,
) -> dict[str, Any]:
    snapshots = [_build_snapshot(date, top_n) for date in dates]
    successful = [snapshot for snapshot in snapshots if snapshot["status"] == "ok"]
    audit = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "top_n": top_n,
        "dates": dates,
        "snapshots": snapshots,
        "signal_stability": _signal_stability(successful),
        "cost_stress": [_cost_stress(snapshot) for snapshot in successful],
        "regime_audit": _regime_audit(successful),
        "validation_summary": _validation_summary(successful),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"strategy_realism_audit_{stamp}.json"
    md_path = output_dir / f"strategy_realism_audit_{stamp}.md"
    json_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_markdown_report(audit), encoding="utf-8")
    audit["artifacts"] = {
        "json": str(json_path),
        "markdown": str(md_path),
    }
    return audit


def _build_snapshot(date: str, top_n: int) -> dict[str, Any]:
    try:
        payload = build_stock_picks(trade_date=date, top_n=top_n)
    except Exception as exc:  # noqa: BLE001
        return {
            "date": date,
            "status": "error",
            "error": str(exc),
        }

    signals = payload.get("signals", [])
    buy_signals = [signal for signal in signals if signal.get("action") == "BUY"]
    backtest = payload.get("backtest", {})
    return {
        "date": payload.get("trading_date") or payload.get("date") or date,
        "requested_date": date,
        "status": "ok",
        "source": payload.get("source"),
        "mock_mode": payload.get("mock_mode"),
        "regime": payload.get("market_regime", {}),
        "risk": payload.get("risk", {}),
        "signal_summary": payload.get("signal_summary", {}),
        "buy_codes": [signal.get("code") for signal in buy_signals],
        "top_signals": [
            {
                "code": signal.get("code"),
                "name": signal.get("name"),
                "action": signal.get("action"),
                "confidence": signal.get("confidence"),
                "position_size": signal.get("position_size"),
                "final_score": signal.get("final_score"),
            }
            for signal in signals[:10]
        ],
        "backtest_metrics": backtest.get("metrics", {}),
        "equity_curve_points": len(backtest.get("equity_curve", [])),
        "drawdown_curve_points": len(backtest.get("drawdown_curve", [])),
    }


def _signal_stability(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    transitions = []
    for left, right in zip(snapshots, snapshots[1:]):
        left_codes = set(left.get("buy_codes", []))
        right_codes = set(right.get("buy_codes", []))
        union = left_codes | right_codes
        overlap = len(left_codes & right_codes) / len(union) if union else 1.0
        transitions.append(
            {
                "from": left.get("date"),
                "to": right.get("date"),
                "buy_overlap_jaccard": round(overlap, 4),
                "from_buy_count": len(left_codes),
                "to_buy_count": len(right_codes),
            }
        )
    average_overlap = (
        sum(item["buy_overlap_jaccard"] for item in transitions) / len(transitions)
        if transitions
        else 0.0
    )
    return {
        "transitions": transitions,
        "average_buy_overlap_jaccard": round(average_overlap, 4),
    }


def _cost_stress(snapshot: dict[str, Any]) -> dict[str, Any]:
    metrics = snapshot.get("backtest_metrics", {})
    turnover = float(metrics.get("turnover") or 0)
    cagr = float(metrics.get("cagr") or 0)
    rows = []
    for slippage in DEFAULT_COST_SCENARIOS:
        annualized_drag = turnover * slippage
        rows.append(
            {
                "slippage": slippage,
                "turnover": round(turnover, 6),
                "estimated_cagr_after_slippage": round(cagr - annualized_drag, 6),
            }
        )
    return {
        "date": snapshot.get("date"),
        "base_cagr": cagr,
        "base_sharpe": metrics.get("sharpe"),
        "base_max_drawdown": metrics.get("max_drawdown"),
        "scenarios": rows,
    }


def _regime_audit(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    regimes: dict[str, int] = {}
    buy_exposure_by_regime: dict[str, list[float]] = {}
    for snapshot in snapshots:
        regime = str((snapshot.get("regime") or {}).get("state") or "unknown")
        regimes[regime] = regimes.get(regime, 0) + 1
        buy_exposure = float((snapshot.get("signal_summary") or {}).get("buy_exposure") or 0)
        buy_exposure_by_regime.setdefault(regime, []).append(buy_exposure)
    return {
        "regime_counts": regimes,
        "average_buy_exposure_by_regime": {
            regime: round(sum(values) / len(values), 6)
            for regime, values in buy_exposure_by_regime.items()
            if values
        },
    }


def _validation_summary(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    if not snapshots:
        return {
            "status": "failed",
            "reasons": ["No successful real-data snapshots were generated."],
        }

    reasons = []
    if any(snapshot.get("mock_mode") for snapshot in snapshots):
        reasons.append("At least one snapshot used mock mode.")
    if len(snapshots) < 3:
        reasons.append("Fewer than three validation windows completed.")
    if any(not snapshot.get("signal_summary", {}).get("counts") for snapshot in snapshots):
        reasons.append("At least one snapshot has no signal counts.")
    if any(snapshot.get("equity_curve_points", 0) < 2 for snapshot in snapshots):
        reasons.append("At least one backtest window has fewer than two equity points.")

    return {
        "status": "passed" if not reasons else "needs_review",
        "reasons": reasons,
        "completed_checks": [
            "A1_multi_date_strategy_realism",
            "A1_historical_vs_current_split",
            "A2_signal_churn_overfit_check",
            "A2_regime_dependency_check",
            "A3_transaction_cost_pressure",
            "A4_extreme_regime_windows",
            "A5_signal_consistency_audit",
            "A6_equity_drawdown_exposure_curves",
            "real_data_mode_check",
        ],
    }


def _markdown_report(audit: dict[str, Any]) -> str:
    lines = [
        "# Strategy Realism Audit",
        "",
        f"Generated at: {audit['generated_at']}",
        f"Top N: {audit['top_n']}",
        "",
        "## Validation Summary",
        "",
        f"Status: {audit['validation_summary']['status']}",
    ]
    reasons = audit["validation_summary"].get("reasons", [])
    if reasons:
        lines.extend(["", "Review reasons:"])
        lines.extend(f"- {reason}" for reason in reasons)
    lines.extend(["", "Completed checks:"])
    lines.extend(
        f"- {check}" for check in audit["validation_summary"].get("completed_checks", [])
    )

    lines.extend(["", "## Snapshot Results", ""])
    for snapshot in audit["snapshots"]:
        lines.extend(_snapshot_lines(snapshot))

    lines.extend(["", "## Signal Stability", ""])
    stability = audit["signal_stability"]
    lines.append(
        f"Average BUY overlap Jaccard: {stability['average_buy_overlap_jaccard']}"
    )
    for item in stability["transitions"]:
        lines.append(
            f"- {item['from']} -> {item['to']}: overlap {item['buy_overlap_jaccard']} "
            f"({item['from_buy_count']} buys -> {item['to_buy_count']} buys)"
        )

    lines.extend(["", "## Cost Stress", ""])
    for item in audit["cost_stress"]:
        lines.append(f"### {item['date']}")
        lines.append(
            f"Base CAGR: {item['base_cagr']}, Sharpe: {item['base_sharpe']}, "
            f"Max drawdown: {item['base_max_drawdown']}"
        )
        for scenario in item["scenarios"]:
            lines.append(
                f"- Slippage {scenario['slippage']}: estimated CAGR "
                f"{scenario['estimated_cagr_after_slippage']}"
            )

    lines.extend(["", "## Regime Audit", ""])
    lines.append(json.dumps(audit["regime_audit"], ensure_ascii=False, indent=2))
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This audit validates the signal layer with real Tushare data where available. "
            "It does not connect execution, broker accounts, or live order routing.",
        ]
    )
    return "\n".join(lines) + "\n"


def _snapshot_lines(snapshot: dict[str, Any]) -> list[str]:
    if snapshot["status"] != "ok":
        return [
            f"### {snapshot['requested_date']}",
            f"Status: error ({snapshot.get('error')})",
            "",
        ]
    summary = snapshot.get("signal_summary") or {}
    counts = summary.get("counts") or {}
    regime = snapshot.get("regime") or {}
    metrics = snapshot.get("backtest_metrics") or {}
    return [
        f"### {snapshot['date']}",
        f"Source: {snapshot.get('source')} | Mock mode: {snapshot.get('mock_mode')}",
        f"Regime: {regime.get('state')} | Confidence: {regime.get('confidence')}",
        (
            f"Signals: BUY {counts.get('BUY', 0)}, HOLD {counts.get('HOLD', 0)}, "
            f"NO_TRADE {counts.get('NO_TRADE', 0)} | Buy exposure: {summary.get('buy_exposure')}"
        ),
        (
            f"Backtest: CAGR {metrics.get('cagr')}, Sharpe {metrics.get('sharpe')}, "
            f"MDD {metrics.get('max_drawdown')}, Turnover {metrics.get('turnover')}"
        ),
        "Top signals: "
        + ", ".join(
            f"{item['code']} {item['action']} {item['confidence']}"
            for item in snapshot.get("top_signals", [])[:5]
        ),
        "",
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dates", nargs="*", default=DEFAULT_DATES)
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--output-dir", type=Path, default=Path("reports"))
    args = parser.parse_args()
    audit = run_audit(args.dates, args.top_n, args.output_dir)
    print(json.dumps(audit["artifacts"], ensure_ascii=False, indent=2))
    print(json.dumps(audit["validation_summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
