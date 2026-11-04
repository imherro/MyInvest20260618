from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Mapping

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import DATA_DIR
from core.alpha_validation_engine import benchmark_comparison, compound_return, max_drawdown, performance_metrics, regime_breakdown
from core.benchmark_loader import load_benchmark_daily, read_benchmark_cache
from core.data_loader import normalize_trade_date
from core.etf_return_utils import coerce_price_frame, daily_return_series
from core.etf_universe_builder import ETF_UNIVERSE
from core.hierarchical_portfolio_engine import build_hierarchical_portfolio
from core.shadow_portfolio_engine import load_structural_survival_rows, risk_signal_from_survival_row


DEFAULT_OUTPUT = DATA_DIR / "macro_style_etf_backtest.json"
DEFAULT_A1_BACKTEST = DATA_DIR / "etf_rotation_backtest.json"
COMPARISON_BENCHMARKS = (
    {"code": "510300.SH", "name": "沪深300ETF", "style": "价值/大盘"},
    {"code": "510500.SH", "name": "中证500ETF", "style": "中小盘"},
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run M2.1 Macro-Style-ETF hierarchical allocation backtest.")
    parser.add_argument("--start", default="20200101", help="Start date, YYYYMMDD.")
    parser.add_argument("--end", default="20260625", help="End date, YYYYMMDD.")
    parser.add_argument("--dataset", default=str(DATA_DIR / "structural_survival_dataset.json"))
    parser.add_argument("--a1-backtest", default=str(DEFAULT_A1_BACKTEST))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--regime-field", default="raw_regime")
    parser.add_argument("--rebalance-every-sessions", type=int, default=20)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    return parser.parse_args()


def _calendar_shift(date_text: str, days: int) -> str:
    return (pd.to_datetime(date_text, format="%Y%m%d") + pd.Timedelta(days=days)).strftime("%Y%m%d")


def _date_window(rows: list[dict[str, object]], start: str, end: str) -> tuple[str, str]:
    dates = sorted(str(row["date"]) for row in rows if isinstance(row, dict) and row.get("date"))
    if not dates:
        raise ValueError("dataset has no date rows")
    start_date = max(normalize_trade_date(start), dates[0])
    end_date = min(normalize_trade_date(end), dates[-1])
    if start_date > end_date:
        raise ValueError("start must be earlier than or equal to end")
    return start_date, end_date


def _load_price_history(
    start_date: str,
    end_date: str,
    *,
    refresh: bool,
    cache_only: bool,
) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    price_history: dict[str, pd.DataFrame] = {}
    errors: dict[str, str] = {}
    warmup_start = _calendar_shift(start_date, -430)
    for etf in ETF_UNIVERSE:
        code = str(etf["code"])
        try:
            if cache_only:
                frame = read_benchmark_cache(code, warmup_start, end_date)
            else:
                frame = load_benchmark_daily(code, warmup_start, end_date, refresh=refresh, cache_only=False)
        except Exception as exc:
            errors[code] = str(exc)
            continue
        if frame.empty:
            errors[code] = "empty fund_daily history"
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
        raise ValueError("no ETF price history available for backtest")
    return pd.DataFrame(returns).sort_index()


def _target_turnover(previous: Mapping[str, float], current: Mapping[str, float]) -> float:
    keys = set(previous) | set(current)
    return round(sum(abs(float(current.get(key, 0.0)) - float(previous.get(key, 0.0))) for key in keys) / 2.0, 6)


def _signal_from_row(row: Mapping[str, object], regime_field: str) -> dict[str, object]:
    signal = risk_signal_from_survival_row(row, regime_field=regime_field)
    features = row.get("features")
    if isinstance(features, Mapping):
        signal["features"] = dict(features)
    signal["raw_regime"] = row.get("raw_regime")
    signal["structural_regime"] = row.get("structural_regime")
    return signal


def _read_a1_returns(path: str | Path) -> dict[str, float]:
    artifact_path = Path(path)
    if not artifact_path.exists():
        return {}
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    rows = payload.get("daily_returns", [])
    if not isinstance(rows, list):
        return {}
    return {
        str(row["date"]): float(row.get("rotation_return", 0.0))
        for row in rows
        if isinstance(row, Mapping) and row.get("date")
    }


def _state_labels_from_row(row: Mapping[str, object], regime_field: str) -> tuple[str, str]:
    model_regime = str(
        row.get(regime_field)
        or row.get("raw_regime")
        or row.get("regime")
        or row.get("structural_regime")
        or ""
    )
    hindsight_regime = str(
        row.get("structural_regime")
        or row.get("regime")
        or row.get("raw_regime")
        or model_regime
    )
    return model_regime, hindsight_regime


def _curve_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    columns = [
        "date",
        "macro_regime",
        "model_regime",
        "hindsight_regime",
        "target_exposure",
        "hierarchical_equity",
        "benchmark_510300_equity",
        "benchmark_510500_equity",
        "equal_weight_basket_equity",
        "current_a1_equity",
    ]
    return [
        {
            key: (str(row[key]) if key in {"date", "macro_regime", "model_regime", "hindsight_regime"} else round(float(row[key]), 6))
            for key in columns
            if key in row
        }
        for _, row in frame[columns].iterrows()
    ]


def _return_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    columns = [
        "date",
        "macro_regime",
        "model_regime",
        "hindsight_regime",
        "target_exposure",
        "hierarchical_return",
        "benchmark_510300_return",
        "benchmark_510500_return",
        "equal_weight_basket_return",
        "current_a1_return",
        "turnover",
    ]
    return [
        {
            key: (str(row[key]) if key in {"date", "macro_regime", "model_regime", "hindsight_regime"} else round(float(row[key]), 8))
            for key in columns
            if key in row
        }
        for _, row in frame[columns].iterrows()
    ]


def _signal_records(signals: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {
            "date": item["date"],
            "apply_from_next_session": True,
            "model_regime": item.get("model_regime"),
            "hindsight_regime": item.get("hindsight_regime"),
            "macro_regime": item["portfolio"]["macro_regime"],
            "exposure_ceiling": item["portfolio"]["exposure_ceiling"],
            "target_exposure": item["portfolio"]["target_exposure"],
            "risk_overlay": item["portfolio"]["risk_overlay"],
            "style_allocation": item["portfolio"]["style_allocation"],
            "etf_allocation": item["portfolio"]["etf_allocation"],
            "turnover_to_target": item["turnover"],
        }
        for item in signals
    ]


def run_macro_style_etf_backtest(
    rows: list[dict[str, object]],
    price_history: Mapping[str, pd.DataFrame],
    *,
    start_date: str,
    end_date: str,
    a1_returns: Mapping[str, float] | None = None,
    regime_field: str = "raw_regime",
    rebalance_every_sessions: int = 20,
) -> dict[str, object]:
    rows_by_date = {
        str(row["date"]): row
        for row in rows
        if isinstance(row, Mapping) and row.get("date") and start_date <= str(row["date"]) <= end_date
    }
    returns = _returns_matrix(price_history)
    dates = sorted(date for date in returns.index.astype(str) if start_date <= date <= end_date and date in rows_by_date)
    if not dates:
        raise ValueError("no overlapping dates between survival rows and ETF returns")

    a1_returns = a1_returns or {}
    current_weights: dict[str, float] = {}
    current_portfolio: dict[str, object] | None = None
    pending_turnover = 0.0
    last_rebalance_index = -max(1, rebalance_every_sessions)
    daily_records: list[dict[str, object]] = []
    signal_records: list[dict[str, object]] = []

    for index, date_text in enumerate(dates):
        source_row = rows_by_date[date_text]
        model_regime, hindsight_regime = _state_labels_from_row(source_row, regime_field)
        day_returns = returns.loc[date_text].fillna(0.0)
        if current_weights and current_portfolio is not None:
            hierarchical_return = sum(
                float(weight) * float(day_returns.get(code, 0.0))
                for code, weight in current_weights.items()
            )
            equal_weight_return = float(day_returns[[code for code in price_history if code in day_returns.index]].mean())
            record = {
                "date": date_text,
                "macro_regime": current_portfolio["macro_regime"],
                "model_regime": model_regime,
                "hindsight_regime": hindsight_regime,
                "target_exposure": current_portfolio["target_exposure"],
                "hierarchical_return": hierarchical_return,
                "benchmark_510300_return": float(day_returns.get("510300.SH", 0.0)),
                "benchmark_510500_return": float(day_returns.get("510500.SH", 0.0)),
                "equal_weight_basket_return": equal_weight_return,
                "current_a1_return": float(a1_returns.get(date_text, 0.0)),
                "turnover": pending_turnover,
                "applied_weights": dict(current_weights),
            }
            daily_records.append(record)
            pending_turnover = 0.0

        should_rebalance = index - last_rebalance_index >= max(1, rebalance_every_sessions)
        if should_rebalance:
            signal = _signal_from_row(source_row, regime_field)
            signal_model_regime, signal_hindsight_regime = _state_labels_from_row(source_row, regime_field)
            portfolio = build_hierarchical_portfolio(signal)
            new_weights = {str(code): float(weight) for code, weight in portfolio["etf_allocation"].items()}
            if new_weights:
                pending_turnover = _target_turnover(current_weights, new_weights)
                current_weights = new_weights
                current_portfolio = portfolio
                last_rebalance_index = index
                signal_records.append(
                    {
                        "date": date_text,
                        "model_regime": signal_model_regime,
                        "hindsight_regime": signal_hindsight_regime,
                        "portfolio": portfolio,
                        "turnover": pending_turnover,
                    }
                )

    frame = pd.DataFrame(daily_records)
    if frame.empty:
        raise ValueError("no backtest returns generated")

    return_columns = [
        "hierarchical_return",
        "benchmark_510300_return",
        "benchmark_510500_return",
        "equal_weight_basket_return",
        "current_a1_return",
    ]
    for column in return_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)

    frame["hierarchical_equity"] = (1.0 + frame["hierarchical_return"]).cumprod()
    frame["benchmark_510300_equity"] = (1.0 + frame["benchmark_510300_return"]).cumprod()
    frame["benchmark_510500_equity"] = (1.0 + frame["benchmark_510500_return"]).cumprod()
    frame["equal_weight_basket_equity"] = (1.0 + frame["equal_weight_basket_return"]).cumprod()
    frame["current_a1_equity"] = (1.0 + frame["current_a1_return"]).cumprod()

    primary = performance_metrics(
        frame["hierarchical_return"],
        benchmark_returns=frame["benchmark_510500_return"],
        turnover=frame["turnover"],
    )
    comparison = benchmark_comparison(
        frame,
        rotation_column="hierarchical_return",
        benchmark_columns=[
            "benchmark_510300_return",
            "benchmark_510500_return",
            "equal_weight_basket_return",
            "current_a1_return",
        ],
    )
    total = compound_return(frame["hierarchical_return"])
    summary = {
        "start_date": str(frame["date"].iloc[0]),
        "end_date": str(frame["date"].iloc[-1]),
        "sessions": int(len(frame)),
        "rebalance_count": len(signal_records),
        "rebalance_every_sessions": max(1, rebalance_every_sessions),
        "hierarchical_total_return": round(total, 6),
        "benchmark_510300_return": round(compound_return(frame["benchmark_510300_return"]), 6),
        "benchmark_510500_return": round(compound_return(frame["benchmark_510500_return"]), 6),
        "equal_weight_basket_return": round(compound_return(frame["equal_weight_basket_return"]), 6),
        "current_a1_return": round(compound_return(frame["current_a1_return"]), 6),
        "alpha_vs_510300": round(total - compound_return(frame["benchmark_510300_return"]), 6),
        "alpha_vs_510500": round(total - compound_return(frame["benchmark_510500_return"]), 6),
        "alpha_vs_equal_weight": round(total - compound_return(frame["equal_weight_basket_return"]), 6),
        "alpha_vs_current_a1": round(total - compound_return(frame["current_a1_return"]), 6),
        "sharpe": primary["sharpe"],
        "max_drawdown": max_drawdown(frame["hierarchical_equity"]),
        "benchmark_510300_max_drawdown": max_drawdown(frame["benchmark_510300_equity"]),
        "benchmark_510500_max_drawdown": max_drawdown(frame["benchmark_510500_equity"]),
        "equal_weight_basket_max_drawdown": max_drawdown(frame["equal_weight_basket_equity"]),
        "current_a1_max_drawdown": max_drawdown(frame["current_a1_equity"]),
        "hit_rate_vs_510500": primary.get("hit_rate"),
        "average_turnover": primary.get("average_turnover"),
        "cumulative_turnover": primary.get("cumulative_turnover"),
        "average_target_exposure": round(float(frame["target_exposure"].mean()), 6),
    }

    return {
        "metadata": {
            "engine": "Macro-Style-ETF Hierarchical Allocation Backtest M2.1",
            "regime_field": regime_field,
            "return_source": "Tushare fund_daily ETF quote returns; prefer pct_chg, then close/pre_close, with close pct_change only as fallback.",
            "signal_timing": "Signal is generated after close on date t and applied starting t+1.",
            "state_band_fields": {
                "applied_macro_regime": "macro_regime",
                "model_visible_regime": "model_regime",
                "hindsight_confirmed_regime": "hindsight_regime",
            },
            "no_lookahead_bias": True,
            "evaluation_only": True,
            "no_stock_selection": True,
            "no_trade_execution": True,
            "no_order_generation": True,
            "layer_contract": {
                "macro": "controls exposure ceiling and risk overlay only",
                "style": "controls style split only",
                "etf": "implements style-to-ETF mapping only",
            },
        },
        "summary": summary,
        "performance_metrics": primary,
        "benchmark_comparison": comparison,
        "macro_regime_breakdown": regime_breakdown(
            frame,
            regime_column="macro_regime",
            rotation_column="hierarchical_return",
            benchmark_column="benchmark_510500_return",
        ),
        "equity_curve": _curve_records(frame),
        "daily_returns": _return_records(frame),
        "signals": _signal_records(signal_records),
        "validation": {
            "alpha_positive_vs_510300": summary["alpha_vs_510300"] > 0,
            "alpha_positive_vs_510500": summary["alpha_vs_510500"] > 0,
            "alpha_positive_vs_equal_weight": summary["alpha_vs_equal_weight"] > 0,
            "alpha_positive_vs_current_a1": summary["alpha_vs_current_a1"] > 0,
            "stable_signal_count": len(signal_records),
            "effective_start_after_first_signal": summary["start_date"],
        },
    }


def main() -> None:
    args = parse_args()
    rows = load_structural_survival_rows(args.dataset)
    start_date, end_date = _date_window(rows, args.start, args.end)
    price_history, price_errors = _load_price_history(
        start_date,
        end_date,
        refresh=args.refresh,
        cache_only=args.cache_only,
    )
    result = run_macro_style_etf_backtest(
        rows,
        price_history,
        start_date=start_date,
        end_date=end_date,
        a1_returns=_read_a1_returns(args.a1_backtest),
        regime_field=args.regime_field,
        rebalance_every_sessions=args.rebalance_every_sessions,
    )
    result["price_history"] = {
        "loaded_etfs": sorted(price_history),
        "errors": price_errors,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "output": str(output_path),
                "summary": result["summary"],
                "validation": result["validation"],
                "price_history_errors": price_errors,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
