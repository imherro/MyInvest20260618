from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import DEFAULT_INDEX_CODE
from core.exposure_controller import build_exposure_decision
from core.regime_adapter import validate_risk_signal
from core.risk_score_engine import load_risk_policy
from engine.regime_input_bridge import load_risk_input_signal


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test the Regime Risk Engine snapshot.")
    parser.add_argument("--date", default=date.today().strftime("%Y%m%d"), help="Target date, YYYYMMDD.")
    parser.add_argument("--ts-code", default=DEFAULT_INDEX_CODE)
    parser.add_argument("--policy", default=str(ROOT_DIR / "rules" / "risk_policy.yaml"))
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    parser.add_argument("--include-hsgt", action="store_true")
    parser.add_argument("--history-sample-size", type=int, default=0)
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
    validate_risk_signal(signal)
    policy = load_risk_policy(args.policy)
    decision = build_exposure_decision(signal, policy=policy)
    print(json.dumps({"input": signal, "decision": decision}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
