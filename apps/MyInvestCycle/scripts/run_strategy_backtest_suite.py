from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import DATA_DIR
from core.benchmark_loader import load_benchmark_daily, read_benchmark_cache
from core.data_loader import cache_path_for, get_index_daily, normalize_trade_date
from core.drawdown_batch_backtest_engine import (
    DrawdownBatchSpec,
    MAX_DRAWDOWN_BATCH_SPEC,
    run_max_drawdown_batch_backtest,
)
from core.equal_weight_reversion_backtest_engine import (
    EQUAL_WEIGHT_REVERSION_SPECS,
    EqualWeightReversionSpec,
    run_equal_weight_reversion_backtest,
)
from core.fixed_allocation_backtest_engine import (
    ALL_WEATHER_SPEC,
    FixedAllocationSpec,
    run_fixed_allocation_backtest,
)
from core.free_cash_flow_trend_channel_backtest_engine import (
    FREE_CASH_FLOW_TREND_SPECS,
    FreeCashFlowTrendSpec,
    run_free_cash_flow_trend_backtest,
)
from core.free_cash_flow_rebound_backtest_engine import (
    FREE_CASH_FLOW_REBOUND_SPEC,
    FreeCashFlowReboundSpec,
    run_free_cash_flow_rebound_backtest,
)
from core.free_cash_flow_buy_hold_backtest_engine import (
    FREE_CASH_FLOW_BUY_HOLD_SPEC,
    FreeCashFlowBuyHoldSpec,
    run_free_cash_flow_buy_hold_backtest,
)
from core.free_cash_flow_chinext_dynamic_backtest_engine import (
    FREE_CASH_FLOW_CHINEXT_DYNAMIC_SPEC,
    FreeCashFlowChinextDynamicSpec,
    run_free_cash_flow_chinext_dynamic_backtest,
)
from core.free_cash_flow_chinext_reversion_backtest_engine import (
    FREE_CASH_FLOW_CHINEXT_REVERSION_SPEC,
    FreeCashFlowChinextReversionSpec,
    run_free_cash_flow_chinext_reversion_backtest,
)
from core.free_cash_flow_chinext_balanced_reversion_backtest_engine import (
    FREE_CASH_FLOW_CHINEXT_BALANCED_REVERSION_SPEC,
    FreeCashFlowChinextBalancedReversionSpec,
    run_free_cash_flow_chinext_balanced_reversion_backtest,
)
from core.free_cash_flow_ma_deviation_backtest_engine import (
    FREE_CASH_FLOW_MA_DEVIATION_SPEC,
    FreeCashFlowMaDeviationSpec,
    run_free_cash_flow_ma_deviation_backtest,
)
from core.free_cash_flow_dual_ma_crossover_backtest_engine import (
    FREE_CASH_FLOW_DUAL_MA_CROSSOVER_SPEC,
    FreeCashFlowDualMaCrossoverSpec,
    run_free_cash_flow_dual_ma_crossover_backtest,
)
from core.strategy_suite_backtest_engine import STRATEGY_SPECS, StrategySpec, run_strategy_backtest


DEFAULT_OUTPUT_DIR = DATA_DIR / "strategy_backtests"
DEFAULT_START_DATE = "20200101"
DEFAULT_END_DATE = "20260625"
SPECIAL_STRATEGY_IDS = (
    MAX_DRAWDOWN_BATCH_SPEC.strategy_id,
    ALL_WEATHER_SPEC.strategy_id,
    *EQUAL_WEIGHT_REVERSION_SPECS,
    *FREE_CASH_FLOW_TREND_SPECS,
    FREE_CASH_FLOW_REBOUND_SPEC.strategy_id,
    FREE_CASH_FLOW_BUY_HOLD_SPEC.strategy_id,
    FREE_CASH_FLOW_CHINEXT_DYNAMIC_SPEC.strategy_id,
    FREE_CASH_FLOW_CHINEXT_REVERSION_SPEC.strategy_id,
    FREE_CASH_FLOW_CHINEXT_BALANCED_REVERSION_SPEC.strategy_id,
    FREE_CASH_FLOW_MA_DEVIATION_SPEC.strategy_id,
    FREE_CASH_FLOW_DUAL_MA_CROSSOVER_SPEC.strategy_id,
)
ALL_STRATEGY_IDS = sorted([*STRATEGY_SPECS, *SPECIAL_STRATEGY_IDS])


def _calendar_shift(date_text: str, days: int) -> str:
    return (pd.to_datetime(date_text, format="%Y%m%d") + pd.Timedelta(days=days)).strftime("%Y%m%d")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run additional ETF strategy backtests.")
    parser.add_argument(
        "--start",
        default=None,
        help=f"Start date, YYYYMMDD. Defaults to each strategy setting; otherwise {DEFAULT_START_DATE}.",
    )
    parser.add_argument("--end", default=DEFAULT_END_DATE, help="End date, YYYYMMDD.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--strategy", choices=ALL_STRATEGY_IDS, action="append", help="Run one strategy id; repeatable.")
    parser.add_argument("--rebalance-every-sessions", type=int, default=20)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    return parser.parse_args()


def _load_price_history(
    spec: StrategySpec | DrawdownBatchSpec | FixedAllocationSpec | EqualWeightReversionSpec,
    start_date: str,
    end_date: str,
    *,
    refresh: bool,
    cache_only: bool,
) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    price_history: dict[str, pd.DataFrame] = {}
    errors: dict[str, str] = {}
    warmup_start = _calendar_shift(start_date, -int(getattr(spec, "warmup_calendar_days", 430)))
    codes = sorted({asset.code for asset in spec.universe} | set(spec.benchmark_codes))
    for code in codes:
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


def _read_index_cache(ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    path = cache_path_for(ts_code)
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path, dtype={"trade_date": str})
    if frame.empty:
        return frame
    frame["trade_date"] = frame["trade_date"].astype(str)
    return frame[(frame["trade_date"] >= start_date) & (frame["trade_date"] <= end_date)].copy()


def _load_free_cash_flow_index_history(
    spec: (
        FreeCashFlowTrendSpec
        | FreeCashFlowReboundSpec
        | FreeCashFlowBuyHoldSpec
        | FreeCashFlowChinextDynamicSpec
        | FreeCashFlowChinextReversionSpec
        | FreeCashFlowChinextBalancedReversionSpec
        | FreeCashFlowMaDeviationSpec
        | FreeCashFlowDualMaCrossoverSpec
    ),
    start_date: str,
    end_date: str,
    *,
    refresh: bool,
    cache_only: bool,
) -> tuple[dict[str, pd.DataFrame], dict[str, str], str, str]:
    warmup_start = _calendar_shift(start_date, -spec.warmup_calendar_days)
    background_codes = list(getattr(spec, "background_codes", ()))
    codes = [
        spec.index_code,
        *[code for code in spec.benchmark_codes if code != spec.index_code],
        *[code for code in background_codes if code != spec.index_code and code not in spec.benchmark_codes],
    ]
    errors: dict[str, str] = {}
    price_history: dict[str, pd.DataFrame] = {}
    for code in codes:
        try:
            if cache_only:
                frame = _read_index_cache(code, warmup_start, end_date)
            else:
                frame = get_index_daily(code, warmup_start, end_date, refresh=refresh)
        except Exception as exc:
            errors[code] = str(exc)
            continue
        if frame.empty:
            errors[code] = "empty index_daily history"
            continue
        price_history[code] = frame
    resolved_index_type = "total_return" if spec.index_code in price_history else "missing"
    return price_history, errors, spec.index_code, resolved_index_type


def main() -> None:
    args = parse_args()
    requested_start_date = normalize_trade_date(args.start) if args.start else None
    end_date = normalize_trade_date(args.end)

    strategy_ids = args.strategy or [*STRATEGY_SPECS, *SPECIAL_STRATEGY_IDS]
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for strategy_id in strategy_ids:
        if strategy_id == MAX_DRAWDOWN_BATCH_SPEC.strategy_id:
            spec = MAX_DRAWDOWN_BATCH_SPEC
        elif strategy_id == ALL_WEATHER_SPEC.strategy_id:
            spec = ALL_WEATHER_SPEC
        elif strategy_id in EQUAL_WEIGHT_REVERSION_SPECS:
            spec = EQUAL_WEIGHT_REVERSION_SPECS[strategy_id]
        elif strategy_id in FREE_CASH_FLOW_TREND_SPECS:
            spec = FREE_CASH_FLOW_TREND_SPECS[strategy_id]
        elif strategy_id == FREE_CASH_FLOW_REBOUND_SPEC.strategy_id:
            spec = FREE_CASH_FLOW_REBOUND_SPEC
        elif strategy_id == FREE_CASH_FLOW_BUY_HOLD_SPEC.strategy_id:
            spec = FREE_CASH_FLOW_BUY_HOLD_SPEC
        elif strategy_id == FREE_CASH_FLOW_CHINEXT_DYNAMIC_SPEC.strategy_id:
            spec = FREE_CASH_FLOW_CHINEXT_DYNAMIC_SPEC
        elif strategy_id == FREE_CASH_FLOW_CHINEXT_REVERSION_SPEC.strategy_id:
            spec = FREE_CASH_FLOW_CHINEXT_REVERSION_SPEC
        elif strategy_id == FREE_CASH_FLOW_CHINEXT_BALANCED_REVERSION_SPEC.strategy_id:
            spec = FREE_CASH_FLOW_CHINEXT_BALANCED_REVERSION_SPEC
        elif strategy_id == FREE_CASH_FLOW_MA_DEVIATION_SPEC.strategy_id:
            spec = FREE_CASH_FLOW_MA_DEVIATION_SPEC
        elif strategy_id == FREE_CASH_FLOW_DUAL_MA_CROSSOVER_SPEC.strategy_id:
            spec = FREE_CASH_FLOW_DUAL_MA_CROSSOVER_SPEC
        else:
            spec = STRATEGY_SPECS[strategy_id]
        start_date = requested_start_date or normalize_trade_date(getattr(spec, "backtest_start_date", DEFAULT_START_DATE))
        if start_date > end_date:
            raise ValueError(f"start must be earlier than or equal to end for {strategy_id}")
        if (
            strategy_id in FREE_CASH_FLOW_TREND_SPECS
            or strategy_id == FREE_CASH_FLOW_REBOUND_SPEC.strategy_id
            or strategy_id == FREE_CASH_FLOW_BUY_HOLD_SPEC.strategy_id
            or strategy_id == FREE_CASH_FLOW_CHINEXT_DYNAMIC_SPEC.strategy_id
            or strategy_id == FREE_CASH_FLOW_CHINEXT_REVERSION_SPEC.strategy_id
            or strategy_id == FREE_CASH_FLOW_CHINEXT_BALANCED_REVERSION_SPEC.strategy_id
            or strategy_id == FREE_CASH_FLOW_MA_DEVIATION_SPEC.strategy_id
            or strategy_id == FREE_CASH_FLOW_DUAL_MA_CROSSOVER_SPEC.strategy_id
        ):
            price_history, price_errors, resolved_index_code, resolved_index_type = _load_free_cash_flow_index_history(
                spec,
                start_date,
                end_date,
                refresh=args.refresh,
                cache_only=args.cache_only,
            )
            if strategy_id == FREE_CASH_FLOW_REBOUND_SPEC.strategy_id:
                result = run_free_cash_flow_rebound_backtest(
                    spec,
                    price_history,
                    start_date=start_date,
                    end_date=end_date,
                    resolved_index_code=resolved_index_code,
                    resolved_index_type=resolved_index_type,
                )
            elif strategy_id == FREE_CASH_FLOW_BUY_HOLD_SPEC.strategy_id:
                result = run_free_cash_flow_buy_hold_backtest(
                    spec,
                    price_history,
                    start_date=start_date,
                    end_date=end_date,
                    resolved_index_code=resolved_index_code,
                    resolved_index_type=resolved_index_type,
                )
            elif strategy_id == FREE_CASH_FLOW_CHINEXT_DYNAMIC_SPEC.strategy_id:
                result = run_free_cash_flow_chinext_dynamic_backtest(
                    spec,
                    price_history,
                    start_date=start_date,
                    end_date=end_date,
                    resolved_index_code=resolved_index_code,
                    resolved_index_type=resolved_index_type,
                )
            elif strategy_id == FREE_CASH_FLOW_CHINEXT_REVERSION_SPEC.strategy_id:
                result = run_free_cash_flow_chinext_reversion_backtest(
                    spec,
                    price_history,
                    start_date=start_date,
                    end_date=end_date,
                    resolved_index_code=resolved_index_code,
                    resolved_index_type=resolved_index_type,
                )
            elif strategy_id == FREE_CASH_FLOW_CHINEXT_BALANCED_REVERSION_SPEC.strategy_id:
                result = run_free_cash_flow_chinext_balanced_reversion_backtest(
                    spec,
                    price_history,
                    start_date=start_date,
                    end_date=end_date,
                    resolved_index_code=resolved_index_code,
                    resolved_index_type=resolved_index_type,
                )
            elif strategy_id == FREE_CASH_FLOW_MA_DEVIATION_SPEC.strategy_id:
                result = run_free_cash_flow_ma_deviation_backtest(
                    spec,
                    price_history,
                    start_date=start_date,
                    end_date=end_date,
                    resolved_index_code=resolved_index_code,
                    resolved_index_type=resolved_index_type,
                )
            elif strategy_id == FREE_CASH_FLOW_DUAL_MA_CROSSOVER_SPEC.strategy_id:
                result = run_free_cash_flow_dual_ma_crossover_backtest(
                    spec,
                    price_history,
                    start_date=start_date,
                    end_date=end_date,
                    resolved_index_code=resolved_index_code,
                    resolved_index_type=resolved_index_type,
                )
            else:
                result = run_free_cash_flow_trend_backtest(
                    spec,
                    price_history,
                    start_date=start_date,
                    end_date=end_date,
                    resolved_index_code=resolved_index_code,
                    resolved_index_type=resolved_index_type,
                )
        else:
            price_history, price_errors = _load_price_history(
                spec,
                start_date,
                end_date,
                refresh=args.refresh,
                cache_only=args.cache_only,
            )
        if strategy_id == MAX_DRAWDOWN_BATCH_SPEC.strategy_id:
            result = run_max_drawdown_batch_backtest(
                price_history,
                start_date=start_date,
                end_date=end_date,
                rebalance_every_sessions=args.rebalance_every_sessions,
            )
        elif strategy_id == ALL_WEATHER_SPEC.strategy_id:
            result = run_fixed_allocation_backtest(
                price_history,
                start_date=start_date,
                end_date=end_date,
                rebalance_every_sessions=args.rebalance_every_sessions,
            )
        elif strategy_id in EQUAL_WEIGHT_REVERSION_SPECS:
            result = run_equal_weight_reversion_backtest(
                spec,
                price_history,
                start_date=start_date,
                end_date=end_date,
                rebalance_every_sessions=args.rebalance_every_sessions,
            )
        elif (
            strategy_id not in FREE_CASH_FLOW_TREND_SPECS
            and strategy_id != FREE_CASH_FLOW_REBOUND_SPEC.strategy_id
            and strategy_id != FREE_CASH_FLOW_BUY_HOLD_SPEC.strategy_id
            and strategy_id != FREE_CASH_FLOW_CHINEXT_DYNAMIC_SPEC.strategy_id
            and strategy_id != FREE_CASH_FLOW_CHINEXT_REVERSION_SPEC.strategy_id
            and strategy_id != FREE_CASH_FLOW_CHINEXT_BALANCED_REVERSION_SPEC.strategy_id
            and strategy_id != FREE_CASH_FLOW_MA_DEVIATION_SPEC.strategy_id
            and strategy_id != FREE_CASH_FLOW_DUAL_MA_CROSSOVER_SPEC.strategy_id
        ):
            result = run_strategy_backtest(
                spec,
                price_history,
                start_date=start_date,
                end_date=end_date,
                rebalance_every_sessions=args.rebalance_every_sessions,
            )
        result["price_history"] = {
            "loaded_etfs": sorted(price_history),
            "errors": price_errors,
        }
        output_path = output_dir / f"{strategy_id}.json"
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        results.append(
            {
                "strategy_id": strategy_id,
                "output": str(output_path),
                "summary": result["summary"],
                "validation": result["validation"],
                "price_history_errors": price_errors,
            }
        )

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
