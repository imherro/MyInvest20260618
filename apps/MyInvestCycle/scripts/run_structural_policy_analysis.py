from __future__ import annotations

import argparse
from collections import Counter
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adaptive_allocation.allocation_engine import build_allocation_intent_snapshot
from config import DATA_DIR
from core.data_loader import normalize_trade_date


DEFAULT_OUTPUT = DATA_DIR / "structural_bull_policy_analysis.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run V2 structural bull policy refinement analysis.")
    parser.add_argument("--date", default="20260708", help="Decision date, YYYYMMDD.")
    parser.add_argument("--backtest", default=str(DATA_DIR / "v2_allocation_backtest.json"))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser.parse_args()


def _historical_distribution(path: str | Path) -> dict[str, object]:
    artifact = Path(path)
    if not artifact.exists():
        return {"available": False, "reason": "v2 allocation backtest artifact missing"}
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    signals = payload.get("signals") or []
    counts = Counter(str(item.get("allocation_structural_state") or item.get("structural_state") or "unknown") for item in signals)
    risk_counts = Counter(str(item.get("risk_budget") or "unknown") for item in signals)
    return {
        "available": True,
        "signal_count": len(signals),
        "allocation_structural_state_counts": dict(sorted(counts.items())),
        "risk_budget_counts": dict(sorted(risk_counts.items())),
        "sample": signals[-5:],
    }


def main() -> None:
    args = parse_args()
    requested = normalize_trade_date(args.date)
    current = build_allocation_intent_snapshot(requested, cache_only=True)
    policy = (current.get("risk_adjustments") or {}).get("structural_bull_policy", {})
    payload = {
        "engine": "V2.5.3 Structural Bull Exposure Policy Refinement",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "requested_as_of": requested,
        "current": {
            "as_of": current.get("as_of"),
            "source_structural_state": current.get("structural_state"),
            "allocation_structural_state": current.get("allocation_structural_state"),
            "risk_budget": (current.get("allocation_intent") or {}).get("risk_budget"),
            "equity_exposure_range": (current.get("allocation_intent") or {}).get("equity_exposure_range"),
            "policy": policy,
            "explanation": current.get("explanation"),
        },
        "historical_distribution": _historical_distribution(args.backtest),
        "constraints": {
            "does_not_change_source_structural_state": True,
            "allocation_policy_only": True,
            "no_etf_selection": True,
            "no_single_stock": True,
            "no_trade_execution": True,
            "no_order": True,
            "no_new_alpha_factor": True,
            "no_macro_score_change": True,
        },
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output_path), "current": payload["current"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
