from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from asset_opportunity.asset_loader import asset_history_coverage
from asset_opportunity.asset_registry import DEFAULT_REGISTRY_PATH, read_asset_registry
from core.data_loader import normalize_trade_date


DEFAULT_OUTPUT_PATH = ROOT_DIR / "data" / "asset_universe_audit.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit V3.1.1 ETF-only asset universe history coverage.")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY_PATH))
    parser.add_argument("--start", default="20150105")
    parser.add_argument("--end", default="20991231")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    return parser.parse_args()


def _common_start(items: list[dict[str, object]]) -> str | None:
    starts = [str(item["start"]) for item in items if item.get("available") and item.get("start")]
    return max(starts) if starts else None


def _common_end(items: list[dict[str, object]]) -> str | None:
    ends = [str(item["end"]) for item in items if item.get("available") and item.get("end")]
    return min(ends) if ends else None


def build_asset_universe_audit(
    *,
    registry_path: str | Path = DEFAULT_REGISTRY_PATH,
    start_date: str = "20150105",
    end_date: str = "20991231",
) -> dict[str, object]:
    start = normalize_trade_date(start_date)
    end = normalize_trade_date(end_date)
    assets = read_asset_registry(registry_path)
    enabled = [asset for asset in assets if asset.enabled]
    coverage = [asset_history_coverage(asset, start_date=start, end_date=end) for asset in enabled]
    missing = [item for item in coverage if not item.get("available")]
    category_counts = dict(Counter(asset.category for asset in enabled))
    target_blockers = [
        f"{item['code']} starts at {item['start']}"
        for item in coverage
        if item.get("available") and item.get("start") and str(item["start"]) > start
    ]
    target_blockers.extend(f"{item['code']} missing history" for item in missing)
    return {
        "metadata": {
            "engine": "V3.1.1 Asset Universe Coverage Audit",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "registry": str(registry_path),
            "target_window": {"start": start, "end": end},
            "purpose": "Coverage audit only; no scoring, no ranking, no allocation, no backtest.",
        },
        "summary": {
            "total_assets": len(assets),
            "enabled_assets": len(enabled),
            "category_counts": category_counts,
            "missing_history": [item["code"] for item in missing],
            "coverage_start": _common_start(coverage),
            "coverage_end": _common_end(coverage),
            "target_window_fully_covered": not target_blockers,
            "target_blockers": target_blockers,
        },
        "asset_coverage": coverage,
        "constraints": {
            "etf_only": True,
            "no_single_stock_selection": True,
            "no_opportunity_score": True,
            "no_ranking": True,
            "no_allocation": True,
            "no_backtest": True,
            "no_trade_execution": True,
            "no_order_generation": True,
            "no_broker_connection": True,
        },
    }


def main() -> None:
    args = parse_args()
    payload = build_asset_universe_audit(
        registry_path=args.registry,
        start_date=args.start,
        end_date=args.end,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), **payload["summary"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
