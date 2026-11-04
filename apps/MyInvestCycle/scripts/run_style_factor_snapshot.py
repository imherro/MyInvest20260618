from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import DATA_DIR, DEFAULT_INDEX_CODE
from core.etf_universe_builder import build_etf_universe
from core.exposure_controller import build_exposure_decision
from core.risk_score_engine import load_risk_policy
from core.style_factor_engine import build_style_factor_snapshot
from engine.regime_input_bridge import load_risk_input_signal


DEFAULT_STYLE_OUTPUT = DATA_DIR / "style_scores.json"
DEFAULT_UNIVERSE_OUTPUT = DATA_DIR / "etf_universe.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run A1.1 style factor and ETF universe snapshot.")
    parser.add_argument("--date", default=date.today().strftime("%Y%m%d"), help="Target date, YYYYMMDD.")
    parser.add_argument("--ts-code", default=DEFAULT_INDEX_CODE)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    parser.add_argument("--include-hsgt", action="store_true")
    parser.add_argument("--history-sample-size", type=int, default=0)
    parser.add_argument("--style-output", default=str(DEFAULT_STYLE_OUTPUT))
    parser.add_argument("--universe-output", default=str(DEFAULT_UNIVERSE_OUTPUT))
    return parser.parse_args()


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

    style_path = Path(args.style_output)
    universe_path = Path(args.universe_output)
    style_path.parent.mkdir(parents=True, exist_ok=True)
    universe_path.parent.mkdir(parents=True, exist_ok=True)
    style_path.write_text(json.dumps(style_snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    universe_path.write_text(json.dumps(etf_universe, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "style_output": str(style_path),
                "universe_output": str(universe_path),
                "style_snapshot": style_snapshot,
                "top_candidates": etf_universe["top_candidates"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
