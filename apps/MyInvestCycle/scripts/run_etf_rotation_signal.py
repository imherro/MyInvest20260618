from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import DATA_DIR, DEFAULT_INDEX_CODE
from core.benchmark_loader import load_benchmark_daily, read_benchmark_cache
from core.etf_rotation_signal_engine import build_etf_rotation_signal
from core.etf_universe_builder import build_etf_universe
from core.exposure_controller import build_exposure_decision
from core.risk_score_engine import load_risk_policy
from core.style_factor_engine import build_style_factor_snapshot
from engine.regime_input_bridge import load_risk_input_signal


DEFAULT_OUTPUT = DATA_DIR / "etf_rotation_signal.json"


def _calendar_shift(date_text: str, days: int) -> str:
    return (pd.to_datetime(date_text, format="%Y%m%d") + pd.Timedelta(days=days)).strftime("%Y%m%d")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run A1.2 ETF rotation signal snapshot.")
    parser.add_argument("--date", default=date.today().strftime("%Y%m%d"), help="Target date, YYYYMMDD.")
    parser.add_argument("--ts-code", default=DEFAULT_INDEX_CODE)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    parser.add_argument("--include-hsgt", action="store_true")
    parser.add_argument("--history-sample-size", type=int, default=0)
    parser.add_argument("--lookback-days", type=int, default=320)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser.parse_args()


def _load_candidate_prices(
    candidates: list[dict[str, object]],
    *,
    start_date: str,
    end_date: str,
    refresh: bool,
    cache_only: bool,
) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    price_history: dict[str, pd.DataFrame] = {}
    errors: dict[str, str] = {}
    for candidate in candidates:
        code = str(candidate["code"])
        try:
            if cache_only:
                frame = read_benchmark_cache(code, start_date, end_date)
            else:
                frame = load_benchmark_daily(
                    code,
                    start_date,
                    end_date,
                    refresh=refresh,
                    cache_only=False,
                )
        except Exception as exc:
            errors[code] = str(exc)
            continue
        if frame.empty:
            errors[code] = "empty fund_daily history"
            continue
        price_history[code] = frame
    return price_history, errors


def main() -> None:
    args = parse_args()
    signal = load_risk_input_signal(
        args.date,
        ts_code=args.ts_code,
        refresh=args.refresh,
        cache_only=args.cache_only,
        include_hsgt=args.include_hsgt,
        history_sample_size=args.history_sample_size,
    )
    risk_decision = build_exposure_decision(signal, policy=load_risk_policy())
    style_snapshot = build_style_factor_snapshot(signal, risk_decision)
    etf_universe = build_etf_universe(style_snapshot)

    as_of = str(style_snapshot["as_of"])
    start_date = _calendar_shift(as_of, -args.lookback_days)
    price_history, price_errors = _load_candidate_prices(
        etf_universe["candidates"],
        start_date=start_date,
        end_date=as_of,
        refresh=args.refresh,
        cache_only=args.cache_only,
    )
    rotation_signal = build_etf_rotation_signal(style_snapshot, etf_universe, price_history)
    rotation_signal["price_history"] = {
        "start_date": start_date,
        "end_date": as_of,
        "errors": price_errors,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(rotation_signal, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "output": str(output_path),
                "as_of": rotation_signal["as_of"],
                "regime": rotation_signal["regime"],
                "rebalance_signal": rotation_signal["rebalance_signal"],
                "confidence": rotation_signal["confidence"],
                "target_weights": rotation_signal["etf_target_weights"],
                "data_coverage": rotation_signal["data_coverage"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
