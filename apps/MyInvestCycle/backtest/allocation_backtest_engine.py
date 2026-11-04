from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Callable, Mapping

import pandas as pd

from adaptive_allocation.allocation_engine import build_allocation_intent_snapshot
from backtest.benchmark_comparator import compare_benchmarks, metrics_for_returns
from backtest.performance_attribution import build_state_attribution
from config import DATA_DIR
from core.alpha_validation_engine import compound_return, max_drawdown
from core.benchmark_loader import load_benchmark_daily, read_benchmark_cache
from core.data_loader import normalize_trade_date
from core.etf_return_utils import coerce_price_frame, daily_return_series


DEFAULT_OUTPUT_PATH = DATA_DIR / "v2_allocation_backtest.json"
EQUITY_PROXY_CODES = ("510300.SH", "510500.SH")
CASH_PROXY_CODE = "511880.SH"
REQUIRED_PRICE_CODES = (*EQUITY_PROXY_CODES, CASH_PROXY_CODE)
RISK_BUDGET_EXPOSURE = {
    "defensive": 0.15,
    "low": 0.40,
    "medium": 0.60,
    "medium_high": 0.70,
    "high": 0.80,
}


SnapshotBuilder = Callable[[str], Mapping[str, object]]


def _calendar_shift(date_text: str, days: int) -> str:
    return (pd.to_datetime(date_text, format="%Y%m%d") + pd.Timedelta(days=days)).strftime("%Y%m%d")


def _load_price_history(
    start_date: str,
    end_date: str,
    *,
    cache_only: bool,
    refresh: bool,
) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    price_history: dict[str, pd.DataFrame] = {}
    errors: dict[str, str] = {}
    warmup_start = _calendar_shift(start_date, -10)
    for code in REQUIRED_PRICE_CODES:
        try:
            if cache_only:
                frame = read_benchmark_cache(code, warmup_start, end_date)
            else:
                frame = load_benchmark_daily(code, warmup_start, end_date, refresh=refresh, cache_only=False)
        except Exception as exc:
            errors[code] = str(exc)
            continue
        if frame.empty:
            errors[code] = "empty price history"
            continue
        price_history[code] = frame
    return price_history, errors


def _returns_matrix(price_history: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    returns: dict[str, pd.Series] = {}
    for code, frame in price_history.items():
        prices = coerce_price_frame(frame)
        if prices.empty:
            continue
        returns[code] = daily_return_series(prices)
    if not returns:
        raise ValueError("no price history available for V2 allocation backtest")
    return pd.DataFrame(returns).sort_index()


def _common_window(returns: pd.DataFrame, start_date: str, end_date: str) -> tuple[str, str, list[str]]:
    required = [code for code in REQUIRED_PRICE_CODES if code in returns.columns]
    if len(required) < len(REQUIRED_PRICE_CODES):
        missing = sorted(set(REQUIRED_PRICE_CODES) - set(required))
        raise ValueError(f"missing required return columns: {missing}")
    clean = returns[list(REQUIRED_PRICE_CODES)].dropna(how="any")
    dates = [str(date) for date in clean.index.astype(str) if start_date <= str(date) <= end_date]
    if len(dates) < 5:
        raise ValueError("not enough overlapping trading sessions for V2 allocation backtest")
    return dates[0], dates[-1], dates


def _target_weights(exposure: float) -> dict[str, float]:
    clipped = max(0.0, min(1.0, float(exposure)))
    return {
        "510300.SH": round(clipped * 0.5, 6),
        "510500.SH": round(clipped * 0.5, 6),
        CASH_PROXY_CODE: round(1.0 - clipped, 6),
    }


def _target_turnover(previous: Mapping[str, float], current: Mapping[str, float]) -> float:
    keys = set(previous) | set(current)
    return round(sum(abs(float(current.get(key, 0.0)) - float(previous.get(key, 0.0))) for key in keys) / 2.0, 6)


def _risk_budget_from_snapshot(snapshot: Mapping[str, object]) -> str:
    intent = snapshot.get("allocation_intent")
    if not isinstance(intent, Mapping):
        return "medium"
    return str(intent.get("risk_budget") or "medium")


def _exposure_from_snapshot(snapshot: Mapping[str, object], exposure_map: Mapping[str, float]) -> float:
    risk_budget = _risk_budget_from_snapshot(snapshot)
    return float(exposure_map.get(risk_budget, exposure_map.get("medium", RISK_BUDGET_EXPOSURE["medium"])))


def _state_from_evidence(snapshot: Mapping[str, object], section: str, key: str = "state") -> object:
    evidence = snapshot.get("evidence")
    if not isinstance(evidence, Mapping):
        return None
    payload = evidence.get(section)
    if not isinstance(payload, Mapping):
        return None
    return payload.get(key)


def _signal_record(
    date_text: str,
    snapshot: Mapping[str, object],
    previous_weights: Mapping[str, float],
    exposure_map: Mapping[str, float],
) -> dict[str, object]:
    risk_budget = _risk_budget_from_snapshot(snapshot)
    exposure = _exposure_from_snapshot(snapshot, exposure_map)
    weights = _target_weights(exposure)
    return {
        "date": date_text,
        "apply_from_next_session": True,
        "as_of": snapshot.get("as_of"),
        "risk_budget": risk_budget,
        "target_exposure": round(exposure, 6),
        "target_weights": weights,
        "turnover_to_target": _target_turnover(previous_weights, weights),
        "structural_state": snapshot.get("structural_state"),
        "allocation_structural_state": snapshot.get("allocation_structural_state")
        or (
            ((snapshot.get("risk_adjustments") or {}).get("allocation_structural_state"))
            if isinstance(snapshot.get("risk_adjustments"), Mapping)
            else None
        ),
        "macro_state": _state_from_evidence(snapshot, "macro"),
        "market_structure_state": _state_from_evidence(snapshot, "market_structure"),
        "theme_risk_level": (snapshot.get("risk_adjustments") or {}).get("theme_risk_level")
        if isinstance(snapshot.get("risk_adjustments"), Mapping)
        else None,
        "style_preference": (snapshot.get("allocation_intent") or {}).get("style_preference")
        if isinstance(snapshot.get("allocation_intent"), Mapping)
        else [],
        "explanation": snapshot.get("explanation") or [],
    }


def _read_shadow_returns(path: str | Path) -> dict[str, float]:
    artifact = Path(path)
    if not artifact.exists():
        return {}
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    rows = payload.get("shadow_returns") or []
    return {
        str(row["date"]): float(row.get("return", 0.0))
        for row in rows
        if isinstance(row, Mapping) and row.get("date")
    }


def _read_m2_returns(path: str | Path) -> dict[str, float]:
    artifact = Path(path)
    if not artifact.exists():
        return {}
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    rows = payload.get("daily_returns") or []
    return {
        str(row["date"]): float(row.get("hierarchical_return", 0.0))
        for row in rows
        if isinstance(row, Mapping) and row.get("date")
    }


def _curve_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    columns = [
        "date",
        "risk_budget",
        "target_exposure",
        "macro_state",
        "market_structure_state",
        "structural_state",
        "allocation_structural_state",
        "theme_risk_level",
        "v2_equity",
        "benchmark_510300_equity",
        "benchmark_510500_equity",
        "old_s1_equity",
        "m2_macro_style_equity",
    ]
    rows: list[dict[str, object]] = []
    for _, row in frame[columns].iterrows():
        item = {}
        for key in columns:
            if key not in row:
                continue
            if key in {
                "date",
                "risk_budget",
                "macro_state",
                "market_structure_state",
                "structural_state",
                "allocation_structural_state",
                "theme_risk_level",
            }:
                item[key] = str(row[key])
            else:
                item[key] = round(float(row[key]), 6)
        rows.append(item)
    return rows


def _return_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    columns = [
        "date",
        "risk_budget",
        "target_exposure",
        "v2_return",
        "benchmark_510300_return",
        "benchmark_510500_return",
        "old_s1_return",
        "m2_macro_style_return",
        "cash_proxy_return",
        "turnover",
    ]
    rows: list[dict[str, object]] = []
    for _, row in frame[columns].iterrows():
        item = {}
        for key in columns:
            if key not in row:
                continue
            if key in {"date", "risk_budget"}:
                item[key] = str(row[key])
            else:
                item[key] = round(float(row[key]), 8)
        rows.append(item)
    return rows


def _equity_columns(frame: pd.DataFrame, return_columns: list[str]) -> None:
    for column in return_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
        frame[column.replace("_return", "_equity")] = (1.0 + frame[column]).cumprod()


def run_v2_allocation_backtest(
    *,
    start_date: str = "20240101",
    end_date: str = "20991231",
    rebalance_every_sessions: int = 20,
    cache_only: bool = True,
    refresh: bool = False,
    shadow_backtest_path: str | Path = DATA_DIR / "shadow_equity_curve.json",
    m2_backtest_path: str | Path = DATA_DIR / "macro_style_etf_backtest.json",
    snapshot_builder: SnapshotBuilder | None = None,
    price_history: Mapping[str, pd.DataFrame] | None = None,
    exposure_map: Mapping[str, float] | None = None,
) -> dict[str, object]:
    start = normalize_trade_date(start_date)
    end = normalize_trade_date(end_date)
    if start > end:
        raise ValueError("start_date must be earlier than or equal to end_date")

    loaded_prices, price_errors = ({}, {})
    if price_history is None:
        loaded_prices, price_errors = _load_price_history(start, end, cache_only=cache_only, refresh=refresh)
        price_history = loaded_prices
    returns = _returns_matrix(price_history)
    effective_start, effective_end, dates = _common_window(returns, start, end)
    old_s1_returns = _read_shadow_returns(shadow_backtest_path)
    m2_returns = _read_m2_returns(m2_backtest_path)
    builder = snapshot_builder or (
        lambda signal_date: build_allocation_intent_snapshot(signal_date, cache_only=cache_only)
    )
    resolved_exposure_map = {**RISK_BUDGET_EXPOSURE, **dict(exposure_map or {})}

    current_signal: dict[str, object] | None = None
    current_weights: dict[str, float] = {}
    pending_turnover = 0.0
    last_rebalance_index = -max(1, rebalance_every_sessions)
    daily_records: list[dict[str, object]] = []
    signal_records: list[dict[str, object]] = []
    snapshot_errors: dict[str, str] = {}

    for index, date_text in enumerate(dates):
        day_returns = returns.loc[date_text].fillna(0.0)
        if current_signal is not None and current_weights:
            v2_return = sum(float(weight) * float(day_returns.get(code, 0.0)) for code, weight in current_weights.items())
            daily_records.append(
                {
                    "date": date_text,
                    "risk_budget": current_signal["risk_budget"],
                    "target_exposure": current_signal["target_exposure"],
                    "macro_state": current_signal.get("macro_state"),
                    "market_structure_state": current_signal.get("market_structure_state"),
                    "structural_state": current_signal.get("structural_state"),
                    "allocation_structural_state": current_signal.get("allocation_structural_state"),
                    "theme_risk_level": current_signal.get("theme_risk_level"),
                    "v2_return": v2_return,
                    "benchmark_510300_return": float(day_returns.get("510300.SH", 0.0)),
                    "benchmark_510500_return": float(day_returns.get("510500.SH", 0.0)),
                    "old_s1_return": float(old_s1_returns.get(date_text, 0.0)),
                    "m2_macro_style_return": float(m2_returns.get(date_text, 0.0)),
                    "cash_proxy_return": float(day_returns.get(CASH_PROXY_CODE, 0.0)),
                    "turnover": pending_turnover,
                    "applied_weights": dict(current_weights),
                }
            )
            pending_turnover = 0.0

        should_rebalance = index - last_rebalance_index >= max(1, rebalance_every_sessions)
        if should_rebalance:
            try:
                snapshot = builder(date_text)
            except Exception as exc:
                snapshot_errors[date_text] = str(exc)
                continue
            signal = _signal_record(date_text, snapshot, current_weights, resolved_exposure_map)
            new_weights = signal["target_weights"]
            current_signal = signal
            current_weights = dict(new_weights)
            pending_turnover = float(signal["turnover_to_target"])
            last_rebalance_index = index
            signal_records.append(signal)

    frame = pd.DataFrame(daily_records)
    if frame.empty:
        raise ValueError("no V2 backtest returns generated")

    return_columns = [
        "v2_return",
        "benchmark_510300_return",
        "benchmark_510500_return",
        "old_s1_return",
        "m2_macro_style_return",
        "cash_proxy_return",
    ]
    _equity_columns(frame, return_columns)
    v2_metrics = metrics_for_returns(frame["v2_return"])
    comparison = compare_benchmarks(
        frame,
        strategy_column="v2_return",
        benchmark_columns={
            "benchmark_510300_return": "510300 沪深300ETF",
            "benchmark_510500_return": "510500 中证500ETF",
            "old_s1_return": "旧 S1.1 仓位风控",
            "m2_macro_style_return": "M2.1 Macro-Style-ETF",
        },
    )
    total = compound_return(frame["v2_return"])
    summary = {
        "start_date": str(frame["date"].iloc[0]),
        "end_date": str(frame["date"].iloc[-1]),
        "effective_price_start": effective_start,
        "effective_price_end": effective_end,
        "sessions": int(len(frame)),
        "rebalance_count": len(signal_records),
        "rebalance_every_sessions": max(1, rebalance_every_sessions),
        "v2_total_return": round(total, 6),
        "v2_annualized_return": v2_metrics["annualized_return"],
        "v2_max_drawdown": max_drawdown(frame["v2_equity"]),
        "v2_sharpe": v2_metrics["sharpe"],
        "v2_calmar": v2_metrics["calmar"],
        "benchmark_510300_return": round(compound_return(frame["benchmark_510300_return"]), 6),
        "benchmark_510500_return": round(compound_return(frame["benchmark_510500_return"]), 6),
        "old_s1_return": round(compound_return(frame["old_s1_return"]), 6),
        "m2_macro_style_return": round(compound_return(frame["m2_macro_style_return"]), 6),
        "alpha_vs_510300": round(total - compound_return(frame["benchmark_510300_return"]), 6),
        "alpha_vs_510500": round(total - compound_return(frame["benchmark_510500_return"]), 6),
        "alpha_vs_old_s1": round(total - compound_return(frame["old_s1_return"]), 6),
        "alpha_vs_m2_macro_style": round(total - compound_return(frame["m2_macro_style_return"]), 6),
        "benchmark_510300_max_drawdown": max_drawdown(frame["benchmark_510300_equity"]),
        "benchmark_510500_max_drawdown": max_drawdown(frame["benchmark_510500_equity"]),
        "old_s1_max_drawdown": max_drawdown(frame["old_s1_equity"]),
        "m2_macro_style_max_drawdown": max_drawdown(frame["m2_macro_style_equity"]),
        "average_exposure": round(float(frame["target_exposure"].mean()), 6),
        "average_turnover": round(float(frame["turnover"].fillna(0.0).mean()), 6),
        "cumulative_turnover": round(float(frame["turnover"].fillna(0.0).sum()), 6),
    }
    return {
        "metadata": {
            "engine": "V2.5.1 Adaptive Allocation Backtest & Validation Engine",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "requested_window": {"start_date": start, "end_date": end},
            "signal_timing": "V2 intent is generated after close on date t and applied starting t+1.",
            "walk_forward": True,
            "no_lookahead_bias": True,
            "evaluation_only": True,
            "no_stock_selection": True,
            "no_trade_execution": True,
            "no_order_generation": True,
            "no_broker_connection": True,
            "mapping_contract": {
                "intent_to_exposure": resolved_exposure_map,
                "equity_proxy": "50% 510300.SH + 50% 510500.SH inside the V2 exposure band",
                "cash_proxy": CASH_PROXY_CODE,
                "purpose": "validation proxy only, not ETF candidate mapping or executable allocation",
            },
        },
        "summary": summary,
        "performance_metrics": v2_metrics,
        "benchmark_comparison": comparison,
        "state_attribution": build_state_attribution(
            frame,
            state_columns=(
                "macro_state",
                "market_structure_state",
                "structural_state",
                "allocation_structural_state",
                "theme_risk_level",
            ),
        ),
        "equity_curve": _curve_records(frame),
        "daily_returns": _return_records(frame),
        "signals": signal_records,
        "validation": {
            "walk_forward_t_plus_1": True,
            "uses_hypothetical_exposure_only": True,
            "compares_510300": "benchmark_510300_return" in frame,
            "compares_510500": "benchmark_510500_return" in frame,
            "compares_old_s1": bool(old_s1_returns),
            "compares_m2_macro_style": bool(m2_returns),
            "snapshot_error_count": len(snapshot_errors),
            "effective_start_after_first_signal": summary["start_date"],
        },
        "data_quality": {
            "price_history": {
                "loaded_codes": sorted(price_history),
                "errors": price_errors,
                "source": "Tushare fund_daily cache by default; --allow-fetch may refresh missing ranges.",
            },
            "snapshot_errors": snapshot_errors,
            "old_s1_artifact_available": bool(old_s1_returns),
            "m2_artifact_available": bool(m2_returns),
        },
    }


def write_v2_allocation_backtest(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
