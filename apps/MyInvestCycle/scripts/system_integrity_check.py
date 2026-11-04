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
from core.capital_controller import load_portfolio_policy
from core.execution_policy import load_execution_policy
from core.execution_simulator import simulate_execution_layer
from core.exposure_controller import build_exposure_decision
from core.portfolio_allocator import build_portfolio_allocation
from core.regime_adapter import validate_risk_signal
from core.risk_score_engine import load_risk_policy
from core.strategy_filter import load_strategy_policy
from core.strategy_router import build_strategy_route
from engine.regime_input_bridge import load_risk_input_signal


REQUIRED_FILES = (
    "docs/system_architecture_freeze.md",
    "logs/decision_trace.json",
    "rules/LOCKED_POLICY.md",
    "rules/risk_policy.yaml",
    "rules/portfolio_policy.yaml",
    "rules/strategy_policy.yaml",
    "rules/execution_policy.yaml",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the frozen system integrity check.")
    parser.add_argument("--date", default=date.today().strftime("%Y%m%d"), help="Target date, YYYYMMDD.")
    parser.add_argument("--ts-code", default=DEFAULT_INDEX_CODE)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    parser.add_argument("--include-hsgt", action="store_true")
    parser.add_argument("--history-sample-size", type=int, default=0)
    return parser.parse_args()


def _required_file_status() -> dict[str, bool]:
    return {path: (ROOT_DIR / path).exists() for path in REQUIRED_FILES}


def main() -> None:
    args = parse_args()
    file_status = _required_file_status()
    missing_files = [path for path, exists in file_status.items() if not exists]
    if missing_files:
        raise FileNotFoundError(f"Missing required frozen artifacts: {missing_files}")

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

    checks = {
        "required_files_present": all(file_status.values()),
        "risk_score_present": "risk_score" in risk_decision,
        "portfolio_normalized": portfolio["constraints"]["cash_plus_exposure"] == 1.0,
        "no_stock_selection": portfolio["constraints"]["no_stock_selection"] is True,
        "strategy_budget_normalized": strategy_route["constraints"]["strategy_budget_sum"] == 1.0,
        "no_trade_execution": strategy_route["constraints"]["no_trade_execution"] is True,
        "simulation_only": execution["constraints"]["simulated_only"] is True,
        "no_real_orders": execution["constraints"]["no_real_orders"] is True,
        "no_broker_connection": execution["constraints"]["no_broker_connection"] is True,
    }
    status = "pass" if all(checks.values()) else "fail"
    payload = {
        "status": status,
        "as_of": signal["as_of"],
        "checks": checks,
        "summary": {
            "regime": signal["regime"],
            "risk_level": risk_decision["risk_level"],
            "total_exposure": portfolio["total_exposure"],
            "enabled_strategies": strategy_route["enabled_strategies"],
            "execution_mode": execution["strategy_mode"],
            "simulated_order_count": execution["constraints"]["order_count"],
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if status != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
