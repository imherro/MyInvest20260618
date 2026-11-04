from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

from config import DATA_DIR


DEFAULT_MATERIALIZATION_PATH = DATA_DIR / "v15_backtest_dataset_materialization_status.json"
DEFAULT_OUTPUT_PATH = DATA_DIR / "v15_macro_drawdown_backtest_result.json"
CSI300_PATH = DATA_DIR / "cache" / "index_daily_000300_SH.csv"
CSI300_TOTAL_RETURN_PATH = DATA_DIR / "cache" / "index_daily_H00300_CSI.csv"
SHANGHAI_PATH = DATA_DIR / "cache" / "index_daily_000001_SH.csv"
PHASE_PATH = DATA_DIR / "market_phase_snapshot.json"
OLD_STRATEGY_PATH = DATA_DIR / "etf_rotation_backtest.json"
CASH_ANNUAL_RETURN = 0.02
TRANSACTION_COST_BPS = 15
BACKTEST_START_DATE = "20160101"
TRADING_DAYS = 252


def _read_json(path: str | Path) -> dict[str, object]:
    target = Path(path)
    if not target.exists():
        return {}
    payload = json.loads(target.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _read_index_csv(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            date = str(row.get("trade_date") or "")
            close = float(row.get("close") or 0)
            if date and close > 0:
                rows.append({"date": date, "close": close})
    rows.sort(key=lambda item: str(item["date"]))
    return rows


def _load_phase_points(path: Path = PHASE_PATH) -> list[dict[str, object]]:
    payload = _read_json(path)
    points: list[dict[str, object]] = []
    for row in _sequence(payload.get("historical_replay")):
        item = _mapping(row)
        date = str(item.get("date") or "")
        phase = str(item.get("phase") or "UNKNOWN")
        metrics = _mapping(item.get("metrics"))
        if date:
            points.append({"date": date, "phase": phase, "metrics": dict(metrics)})
    current = _mapping(payload.get("current"))
    current_date = str(current.get("as_of") or "")
    current_phase = str(current.get("phase") or "")
    if current_date and current_phase:
        points.append({"date": current_date, "phase": current_phase, "metrics": dict(_mapping(current.get("metrics")))})
    points.sort(key=lambda item: str(item["date"]))
    deduped: dict[str, dict[str, object]] = {}
    for point in points:
        deduped[str(point["date"])] = point
    return [deduped[date] for date in sorted(deduped)]


def _phase_for_dates(dates: list[str], phase_points: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    phase_by_date: dict[str, dict[str, object]] = {}
    index = 0
    current: dict[str, object] = {"phase": "UNKNOWN", "metrics": {}}
    for date in dates:
        while index < len(phase_points) and str(phase_points[index]["date"]) <= date:
            current = phase_points[index]
            index += 1
        phase_by_date[date] = current
    return phase_by_date


def _target_exposure(phase: str, drawdown: float) -> float:
    if phase in {"EARLY_CYCLE", "EXPANSION"}:
        return 1.0 if drawdown <= -0.08 else 0.85
    if phase == "ROTATION":
        return 0.75 if drawdown <= -0.10 else 0.65
    if phase == "LATE_CYCLE":
        return 0.30 if drawdown <= -0.05 else 0.55
    if phase == "CONTRACTION":
        return 0.15 if drawdown <= -0.05 else 0.25
    return 0.50


def _max_drawdown(equity: list[float]) -> tuple[float, int]:
    peak = -math.inf
    max_dd = 0.0
    max_recovery = 0
    current_recovery = 0
    for value in equity:
        if value >= peak:
            peak = value
            current_recovery = 0
        else:
            current_recovery += 1
            max_recovery = max(max_recovery, current_recovery)
            if peak > 0:
                max_dd = min(max_dd, value / peak - 1.0)
    return max_dd, max_recovery


def _metrics(dates: list[str], equity: list[float], *, benchmark_cagr: float | None = None) -> dict[str, object]:
    if len(dates) < 2 or len(equity) < 2:
        return {
            "start_date": dates[0] if dates else None,
            "end_date": dates[-1] if dates else None,
            "sessions": len(dates),
            "total_return": None,
            "CAGR": None,
            "annual_return": None,
            "annual_alpha": None,
            "max_drawdown": None,
            "calmar": None,
            "sharpe": None,
            "drawdown_recovery_days": None,
        }
    if equity[0] == 0:
        raise ValueError("equity curve must start from a non-zero value")
    values = [value / equity[0] for value in equity]
    returns = [values[i] / values[i - 1] - 1.0 for i in range(1, len(values))]
    years = max((len(values) - 1) / TRADING_DAYS, 1 / TRADING_DAYS)
    total_return = values[-1] - 1.0
    cagr = values[-1] ** (1 / years) - 1.0
    max_dd, recovery = _max_drawdown(values)
    daily_excess = [ret - CASH_ANNUAL_RETURN / TRADING_DAYS for ret in returns]
    volatility = pstdev(daily_excess) if len(daily_excess) > 1 else 0.0
    sharpe = (mean(daily_excess) / volatility * math.sqrt(TRADING_DAYS)) if volatility > 1e-12 else None
    return {
        "start_date": dates[0],
        "end_date": dates[-1],
        "sessions": len(dates),
        "total_return": round(total_return, 6),
        "CAGR": round(cagr, 6),
        "annual_return": round(cagr, 6),
        "annual_alpha": round(cagr - benchmark_cagr, 6) if benchmark_cagr is not None else None,
        "max_drawdown": round(max_dd, 6),
        "calmar": round(cagr / abs(max_dd), 6) if max_dd < 0 else None,
        "sharpe": round(sharpe, 6) if sharpe is not None else None,
        "drawdown_recovery_days": recovery,
    }


def _yearly_returns(dates: list[str], equity: list[float]) -> dict[str, float]:
    by_year: dict[str, list[tuple[str, float]]] = defaultdict(list)
    base = equity[0] if equity else 1.0
    for date, value in zip(dates, equity, strict=False):
        by_year[date[:4]].append((date, value / base))
    result: dict[str, float] = {}
    for year, rows in sorted(by_year.items()):
        if len(rows) >= 2:
            result[year] = round(rows[-1][1] / rows[0][1] - 1.0, 6)
    return result


def _segment_returns(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["phase"])].append(row)
    result: dict[str, dict[str, object]] = {}
    for phase, items in sorted(grouped.items()):
        if len(items) < 2:
            continue
        result[phase] = {
            "sessions": len(items),
            "strategy_return": round(float(items[-1]["strategy_equity"]) / float(items[0]["strategy_equity"]) - 1.0, 6),
            "csi_300_return": round(float(items[-1]["csi_300_equity"]) / float(items[0]["csi_300_equity"]) - 1.0, 6),
            "avg_applied_exposure": round(mean(float(item["applied_exposure"]) for item in items), 6),
        }
    return result


def _slice_curve(dates: list[str], equity: list[float], start: str, end: str) -> tuple[list[str], list[float]]:
    sliced = [(date, value) for date, value in zip(dates, equity, strict=False) if start <= date <= end]
    if not sliced:
        return [], []
    out_dates = [date for date, _ in sliced]
    base = sliced[0][1]
    out_equity = [value / base for _, value in sliced]
    return out_dates, out_equity


def _old_strategy_baseline(path: Path = OLD_STRATEGY_PATH) -> tuple[dict[str, object], tuple[str | None, str | None]]:
    payload = _read_json(path)
    rows = _sequence(payload.get("equity_curve"))
    dates: list[str] = []
    equity: list[float] = []
    for row in rows:
        item = _mapping(row)
        date = str(item.get("date") or "")
        value = item.get("rotation_equity")
        if date and isinstance(value, (int, float)):
            dates.append(date)
            equity.append(float(value))
    metrics = _metrics(dates, equity)
    metrics["source"] = "data/etf_rotation_backtest.json"
    metrics["baseline_note"] = "Existing ETF rotation research backtest, used only as old strategy baseline."
    return metrics, (dates[0] if dates else None, dates[-1] if dates else None)


def _build_curves() -> dict[str, object]:
    csi_price_rows = {str(row["date"]): float(row["close"]) for row in _read_index_csv(CSI300_PATH)}
    csi_total_return_rows = {
        str(row["date"]): float(row["close"])
        for row in _read_index_csv(CSI300_TOTAL_RETURN_PATH)
    }
    sh_rows = {str(row["date"]): float(row["close"]) for row in _read_index_csv(SHANGHAI_PATH)}
    phase_points = _load_phase_points()
    start_date = max(BACKTEST_START_DATE, str(phase_points[0]["date"]) if phase_points else BACKTEST_START_DATE)
    common_dates = sorted(
        date
        for date in csi_price_rows.keys() & csi_total_return_rows.keys() & sh_rows.keys()
        if date >= start_date
    )
    if not common_dates:
        raise RuntimeError("V15 formal evaluation requires overlapping CSI300 price and total-return data.")
    phase_map = _phase_for_dates(common_dates, phase_points)
    cash_daily = CASH_ANNUAL_RETURN / TRADING_DAYS
    cost_rate = TRANSACTION_COST_BPS / 10_000

    strategy_equity = [1.0]
    csi_equity = [1.0]
    shanghai_equity = [1.0]
    cash_equity = [1.0]
    target_exposures: list[float] = []
    applied_exposures: list[float] = [0.85]
    drawdowns: list[float] = []
    csi_peak = csi_price_rows[common_dates[0]]
    curve: list[dict[str, object]] = []

    for index, date in enumerate(common_dates):
        close = csi_price_rows[date]
        csi_peak = max(csi_peak, close)
        drawdown = close / csi_peak - 1.0
        drawdowns.append(drawdown)
        phase = str(phase_map[date].get("phase") or "UNKNOWN")
        target_exposure = _target_exposure(phase, drawdown)
        target_exposures.append(target_exposure)
        if index > 0:
            prev = common_dates[index - 1]
            csi_ret = csi_total_return_rows[date] / csi_total_return_rows[prev] - 1.0
            sh_ret = sh_rows[date] / sh_rows[prev] - 1.0
            applied = target_exposures[index - 1]
            previous_applied = applied_exposures[-1]
            turnover = abs(applied - previous_applied)
            applied_exposures.append(applied)
            strategy_ret = applied * csi_ret + (1 - applied) * cash_daily - turnover * cost_rate
            strategy_equity.append(strategy_equity[-1] * (1 + strategy_ret))
            csi_equity.append(csi_equity[-1] * (1 + csi_ret))
            shanghai_equity.append(shanghai_equity[-1] * (1 + sh_ret))
            cash_equity.append(cash_equity[-1] * (1 + cash_daily))
        curve.append(
            {
                "date": date,
                "phase": phase,
                "drawdown": round(drawdown, 6),
                "target_exposure": round(target_exposure, 6),
                "applied_exposure": round(applied_exposures[-1], 6),
                "transaction_cost_bps": TRANSACTION_COST_BPS,
                "strategy_equity": round(strategy_equity[-1], 6),
                "csi_300_equity": round(csi_equity[-1], 6),
                "csi_300_total_return_equity": round(csi_equity[-1], 6),
                "shanghai_composite_equity": round(shanghai_equity[-1], 6),
                "cash_equity": round(cash_equity[-1], 6),
            }
        )
    return {
        "dates": common_dates,
        "curve": curve,
        "strategy_equity": strategy_equity,
        "csi_equity": csi_equity,
        "shanghai_equity": shanghai_equity,
        "cash_equity": cash_equity,
        "phase_points": phase_points,
    }


def validate_v15_macro_drawdown_backtest_result(payload: Mapping[str, object]) -> dict[str, object]:
    summary = _mapping(payload.get("summary"))
    benchmarks = _mapping(payload.get("benchmarks"))
    strategy_results = _mapping(payload.get("strategy_results"))
    strategy = _mapping(strategy_results.get("macro_drawdown_strategy"))
    constraints = _mapping(payload.get("constraints"))
    if payload.get("phase") != "V15.3":
        raise AssertionError("phase must be V15.3")
    if payload.get("backtest_status") != "completed":
        raise AssertionError("backtest_status must be completed")
    for key in ("research_backtest_only", "not_production_signal", "no_real_trade_order", "uses_point_in_time_inputs", "uses_t_plus_one_execution"):
        if payload.get(key) is not True:
            raise AssertionError(f"{key} must be true")
    for key in ("cash_baseline", "csi_300_buy_hold", "shanghai_composite_buy_hold", "old_strategy_baseline"):
        if key not in benchmarks:
            raise AssertionError(f"missing benchmark {key}")
    for key in ("CAGR", "annual_return", "annual_alpha", "max_drawdown", "calmar", "sharpe", "yearly_returns", "regime_segment_returns"):
        if key not in strategy:
            raise AssertionError(f"strategy missing {key}")
    for key in ("no_broker_connection", "no_order_generation", "not_intraday_signal", "not_production_trade_signal"):
        if constraints.get(key) is not True:
            raise AssertionError(f"constraints.{key} must be true")
    if summary.get("strategy_scope") != "macro_drawdown_regime_baseline":
        raise AssertionError("strategy scope mismatch")
    rules = _mapping(payload.get("strategy_rules"))
    if rules.get("return_index") != "H00300.CSI" or rules.get("transaction_cost_bps") != TRANSACTION_COST_BPS:
        raise AssertionError("formal total-return and cost assumptions are required")
    return {
        "audit_status": "passed",
        "checked_phase": payload.get("phase"),
        "checked_backtest_status": payload.get("backtest_status"),
        "checked_research_backtest_only": payload.get("research_backtest_only"),
        "checked_not_production_signal": payload.get("not_production_signal"),
        "checked_no_real_trade_order": payload.get("no_real_trade_order"),
        "checked_benchmarks": sorted(benchmarks.keys()),
        "checked_strategy_scope": summary.get("strategy_scope"),
    }


def build_v15_macro_drawdown_backtest_result(
    *,
    materialization_path: str | Path = DEFAULT_MATERIALIZATION_PATH,
) -> dict[str, object]:
    materialization = _read_json(materialization_path)
    if materialization.get("phase") != "V15.2" or materialization.get("materialization_status") != "coverage_report_ready":
        raise RuntimeError("V15.3 requires V15.2 materialization status first.")

    curves = _build_curves()
    dates = list(curves["dates"])
    strategy_equity = list(curves["strategy_equity"])
    csi_equity = list(curves["csi_equity"])
    shanghai_equity = list(curves["shanghai_equity"])
    cash_equity = list(curves["cash_equity"])
    curve = list(curves["curve"])

    csi_metrics = _metrics(dates, csi_equity)
    cash_metrics = _metrics(dates, cash_equity)
    shanghai_metrics = _metrics(dates, shanghai_equity)
    old_metrics, old_period = _old_strategy_baseline()
    strategy_metrics = _metrics(dates, strategy_equity, benchmark_cagr=csi_metrics.get("CAGR"))
    strategy_metrics["yearly_returns"] = _yearly_returns(dates, strategy_equity)
    strategy_metrics["regime_segment_returns"] = _segment_returns(curve)

    common_comparison: dict[str, object] = {}
    old_start, old_end = old_period
    if old_start and old_end:
        common_start = max(str(old_start), dates[0])
        common_end = min(str(old_end), dates[-1])
        common_dates, common_strategy = _slice_curve(dates, strategy_equity, common_start, common_end)
        _, common_csi = _slice_curve(dates, csi_equity, common_start, common_end)
        _, common_cash = _slice_curve(dates, cash_equity, common_start, common_end)
        old_payload = _read_json(OLD_STRATEGY_PATH)
        old_rows = [
            _mapping(row)
            for row in _sequence(old_payload.get("equity_curve"))
            if common_start <= str(_mapping(row).get("date") or "") <= common_end
        ]
        old_dates = [str(row.get("date")) for row in old_rows]
        old_equity = [float(row.get("rotation_equity")) for row in old_rows if isinstance(row.get("rotation_equity"), (int, float))]
        common_comparison = {
            "common_start_date": common_start,
            "common_end_date": common_end,
            "macro_drawdown_strategy": _metrics(common_dates, common_strategy, benchmark_cagr=_metrics(common_dates, common_csi).get("CAGR")),
            "csi_300_buy_hold": _metrics(common_dates, common_csi),
            "cash_baseline": _metrics(common_dates, common_cash),
            "old_strategy_baseline": _metrics(old_dates[: len(old_equity)], old_equity),
        }

    comparison = {
        "beats_cash_baseline": strategy_metrics["CAGR"] > cash_metrics["CAGR"],
        "beats_csi_300_buy_hold": strategy_metrics["CAGR"] > csi_metrics["CAGR"],
        "beats_shanghai_composite_buy_hold": strategy_metrics["CAGR"] > shanghai_metrics["CAGR"],
        "improves_max_drawdown_vs_csi_300": strategy_metrics["max_drawdown"] > csi_metrics["max_drawdown"],
        "improves_calmar_vs_csi_300": (
            strategy_metrics["calmar"] is not None
            and csi_metrics["calmar"] is not None
            and strategy_metrics["calmar"] > csi_metrics["calmar"]
        ),
        "result_must_not_be_marketed_as_success_without_beating_core_benchmarks": True,
    }
    payload: dict[str, object] = {
        "metadata": {
            "engine": "V15.3 Macro + Drawdown Regime Baseline Backtest",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": dates[-1],
            "source_materialization": "data/v15_backtest_dataset_materialization_status.json",
            "purpose": "Run a research-only macro/drawdown baseline backtest against cash and broad-index benchmarks.",
        },
        "phase": "V15.3",
        "backtest_status": "completed",
        "research_backtest_only": True,
        "not_production_signal": True,
        "no_real_trade_order": True,
        "strategy_scope": "macro_drawdown_regime_baseline",
        "input_materialization": "data/v15_backtest_dataset_materialization_status.json",
        "uses_point_in_time_inputs": True,
        "uses_t_plus_one_execution": True,
        "summary": {
            "phase": "V15.3",
            "backtest_status": "completed",
            "strategy_scope": "macro_drawdown_regime_baseline",
            "start_date": dates[0],
            "end_date": dates[-1],
            "sessions": len(dates),
            "macro_drawdown_CAGR": strategy_metrics["CAGR"],
            "macro_drawdown_max_drawdown": strategy_metrics["max_drawdown"],
            "macro_drawdown_calmar": strategy_metrics["calmar"],
            "return_index": "H00300.CSI",
            "transaction_cost_bps": TRANSACTION_COST_BPS,
            "beats_cash_baseline": comparison["beats_cash_baseline"],
            "beats_csi_300_buy_hold": comparison["beats_csi_300_buy_hold"],
            "research_backtest_only": True,
            "not_production_signal": True,
            "no_real_trade_order": True,
            "next_task": "V15.4 structural bull rotation strategy backtest if ChatGPT audit approves V15.3",
        },
        "strategy_rules": {
            "carrier_index": "H00300.CSI",
            "signal_index": "000300.SH",
            "return_index": "H00300.CSI",
            "return_index_name": "CSI 300 Total Return Index",
            "drawdown_signal_uses_price_index": True,
            "strategy_return_includes_dividend_reinvestment": True,
            "transaction_cost_bps": TRANSACTION_COST_BPS,
            "transaction_cost_definition": "15bp per one-way absolute exposure change",
            "cash_annual_return": CASH_ANNUAL_RETURN,
            "signal_timing": "phase and drawdown observed after close on t; target exposure is applied to t+1 return",
            "exposure_rules": {
                "EARLY_CYCLE_or_EXPANSION": "0.85 base, 1.00 if CSI300 drawdown <= -8%",
                "ROTATION": "0.65 base, 0.75 if CSI300 drawdown <= -10%",
                "LATE_CYCLE": "0.55 base, 0.30 if CSI300 drawdown <= -5%",
                "CONTRACTION": "0.25 base, 0.15 if CSI300 drawdown <= -5%",
                "UNKNOWN": "0.50",
            },
        },
        "benchmarks": {
            "cash_baseline": cash_metrics,
            "csi_300_buy_hold": csi_metrics,
            "csi_300_total_return_buy_hold": csi_metrics,
            "shanghai_composite_buy_hold": shanghai_metrics,
            "old_strategy_baseline": old_metrics,
        },
        "strategy_results": {
            "macro_drawdown_strategy": strategy_metrics,
        },
        "comparison": comparison,
        "common_period_comparison": common_comparison,
        "kill_criteria": {
            "must_beat_cash_baseline": True,
            "must_not_have_unacceptable_drawdown": True,
            "failure_result_is_acceptable": True,
            "do_not_package_as_success_if_core_benchmarks_not_beaten": True,
        },
        "data_quality": {
            "phase_points": len(curves["phase_points"]),
            "phase_forward_fill_used": True,
            "phase_forward_fill_after_last_replay_allowed_until_current_as_of": True,
            "old_strategy_baseline_period_may_differ_from_full_backtest": True,
            "signal_source": "data/cache/index_daily_000300_SH.csv",
            "return_source": "data/cache/index_daily_H00300_CSI.csv",
            "return_source_is_total_return_index": True,
            "backtest_start_policy": "Start from the first common trading day in 2016.",
        },
        "equity_curve": curve,
        "constraints": {
            "no_broker_connection": True,
            "no_order_generation": True,
            "not_intraday_signal": True,
            "not_production_trade_signal": True,
        },
    }
    payload["audit"] = validate_v15_macro_drawdown_backtest_result(payload)
    return payload


def write_v15_macro_drawdown_backtest_result(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
