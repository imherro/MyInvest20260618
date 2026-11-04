from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from asset_opportunity.asset_proxy_loader import research_proxy_coverage
from asset_opportunity.asset_proxy_registry import DEFAULT_PROXY_REGISTRY_PATH, read_asset_proxy_registry
from core.data_loader import normalize_trade_date


DEFAULT_OUTPUT_PATH = ROOT_DIR / "data" / "asset_proxy_coverage_audit.json"


def _project_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(ROOT_DIR).as_posix()
    except ValueError:
        return resolved.as_posix()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit V3.1.2 research proxy coverage.")
    parser.add_argument("--registry", default=str(DEFAULT_PROXY_REGISTRY_PATH))
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


def build_asset_proxy_coverage_audit(
    *,
    registry_path: str | Path = DEFAULT_PROXY_REGISTRY_PATH,
    start_date: str = "20150105",
    end_date: str = "20991231",
) -> dict[str, object]:
    start = normalize_trade_date(start_date)
    end = normalize_trade_date(end_date)
    mappings = read_asset_proxy_registry(registry_path)
    enabled = [mapping for mapping in mappings if mapping.enabled]
    with_proxy = [mapping for mapping in enabled if mapping.research_proxy is not None]
    without_proxy = [mapping for mapping in enabled if mapping.research_proxy is None]
    coverage = [research_proxy_coverage(mapping, start_date=start, end_date=end) for mapping in with_proxy]
    missing_proxy = [item["asset_code"] for item in coverage if not item.get("available")]
    target_blockers = [
        f"{item['asset_code']} proxy {item['proxy_code']} starts at {item['start']}"
        for item in coverage
        if item.get("available") and item.get("start") and str(item["start"]) > start
    ]
    target_blockers.extend(f"{code} proxy missing history" for code in missing_proxy)
    return {
        "metadata": {
            "engine": "V3.1.2 Asset Research Proxy Coverage Audit",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "registry": _project_path(registry_path),
            "target_window": {"start": start, "end": end},
            "purpose": "Research proxy coverage audit only; no scoring, no ranking, no allocation, no backtest.",
        },
        "summary": {
            "ETF_assets": len(enabled),
            "with_proxy": len(with_proxy),
            "without_proxy": [mapping.asset_code for mapping in without_proxy],
            "research_coverage_start": _common_start(coverage),
            "research_coverage_end": _common_end(coverage),
            "missing_proxy": missing_proxy,
            "target_window_fully_covered": not target_blockers,
            "target_blockers": target_blockers,
        },
        "proxy_coverage": coverage,
        "constraints": {
            "etf_and_proxy_separated": True,
            "research_proxy_only": True,
            "does_not_fabricate_etf_history": True,
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
    payload = build_asset_proxy_coverage_audit(
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
