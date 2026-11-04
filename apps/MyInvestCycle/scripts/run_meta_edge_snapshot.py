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
from core.capital_controller import load_portfolio_policy
from core.execution_policy import load_execution_policy
from core.execution_simulator import simulate_execution_layer
from core.exposure_controller import build_exposure_decision
from core.meta_signal_engine import build_meta_edge_signal, load_meta_edge_rules
from core.portfolio_allocator import build_portfolio_allocation
from core.regime_adapter import validate_risk_signal
from core.risk_score_engine import load_risk_policy
from core.strategy_filter import load_strategy_policy
from core.strategy_router import build_strategy_route
from engine.regime_input_bridge import load_risk_input_signal


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the M1.1 Meta Signal Engine snapshot.")
    parser.add_argument("--date", default=date.today().strftime("%Y%m%d"), help="Target date, YYYYMMDD.")
    parser.add_argument("--ts-code", default=DEFAULT_INDEX_CODE)
    parser.add_argument("--rules", default=str(ROOT_DIR / "rules" / "meta_edge_rules.yaml"))
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    parser.add_argument("--include-hsgt", action="store_true")
    parser.add_argument("--history-sample-size", type=int, default=0)
    return parser.parse_args()


def _read_data_json(file_name: str) -> list[dict]:
    path = DATA_DIR / file_name
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, list) else []


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
    risk_decision = build_exposure_decision(signal, policy=load_risk_policy())
    portfolio = build_portfolio_allocation(
        {"input": signal, "decision": risk_decision},
        policy=load_portfolio_policy(),
    )
    strategy_route = build_strategy_route(portfolio, policy=load_strategy_policy())
    execution = simulate_execution_layer(strategy_route, policy=load_execution_policy())
    meta_edge = build_meta_edge_signal(
        regime_signal=signal,
        risk_decision=risk_decision,
        portfolio=portfolio,
        strategy_route=strategy_route,
        hazard_rows=_read_data_json("structural_hazard_dataset.json"),
        survival_rows=_read_data_json("structural_survival_dataset.json"),
        rules=load_meta_edge_rules(args.rules),
    )
    print(
        json.dumps(
            {
                "input": signal,
                "risk_decision": risk_decision,
                "portfolio": portfolio,
                "strategy_route": strategy_route,
                "execution": execution,
                "meta_edge": meta_edge,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
