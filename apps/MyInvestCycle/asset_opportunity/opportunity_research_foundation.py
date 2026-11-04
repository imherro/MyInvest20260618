from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Mapping

from config import DATA_DIR


DEFAULT_OUTPUT_PATH = DATA_DIR / "opportunity_research_foundation.json"

REQUIRED_INPUTS = {
    "asset_registry": DATA_DIR / "asset_registry.json",
    "asset_universe_audit": DATA_DIR / "asset_universe_audit.json",
    "asset_proxy_registry": DATA_DIR / "asset_proxy_registry.json",
    "asset_proxy_coverage_audit": DATA_DIR / "asset_proxy_coverage_audit.json",
}


def _read_json(path: Path) -> object:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _as_mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _project_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _input_payloads(data_dir: str | Path = DATA_DIR) -> dict[str, Mapping[str, object]]:
    root = Path(data_dir)
    paths = {
        name: (root / path.name if path.is_absolute() else root / path)
        for name, path in REQUIRED_INPUTS.items()
    }
    payloads = {name: _as_mapping(_read_json(path)) for name, path in paths.items()}
    missing = [name for name, payload in payloads.items() if not payload]
    if missing:
        raise RuntimeError(f"missing V7.1 foundation inputs: {missing}")
    return payloads


def _asset_rows(asset_registry: Mapping[str, object], proxy_registry: Mapping[str, object], coverage_audit: Mapping[str, object]) -> list[dict[str, object]]:
    assets = asset_registry.get("assets") if isinstance(asset_registry.get("assets"), list) else []
    mappings = proxy_registry.get("mappings") if isinstance(proxy_registry.get("mappings"), list) else []
    coverage = coverage_audit.get("asset_coverage") if isinstance(coverage_audit.get("asset_coverage"), list) else []
    mapping_by_code = {
        str(item.get("asset_code") or ""): item
        for item in mappings
        if isinstance(item, Mapping)
    }
    coverage_by_code = {
        str(item.get("code") or ""): item
        for item in coverage
        if isinstance(item, Mapping)
    }
    rows: list[dict[str, object]] = []
    for asset in assets:
        if not isinstance(asset, Mapping):
            continue
        code = str(asset.get("code") or "")
        mapping = _as_mapping(mapping_by_code.get(code))
        research_proxy = _as_mapping(mapping.get("research_proxy"))
        history = _as_mapping(coverage_by_code.get(code))
        rows.append(
            {
                "asset_code": code,
                "asset_name": asset.get("name"),
                "asset_type": asset.get("type"),
                "category": asset.get("category"),
                "theme": asset.get("theme"),
                "enabled": bool(asset.get("enabled")),
                "tradable_history": {
                    "available": bool(history.get("available")),
                    "start": history.get("start"),
                    "end": history.get("end"),
                    "rows": history.get("rows"),
                },
                "research_proxy": {
                    "mapping_method": mapping.get("mapping_method"),
                    "has_proxy": bool(research_proxy),
                    "code": research_proxy.get("code"),
                    "name": research_proxy.get("name"),
                    "type": research_proxy.get("type"),
                    "source": research_proxy.get("source"),
                },
                "research_only": True,
            }
        )
    return rows


def _coverage_status(asset_audit: Mapping[str, object], proxy_audit: Mapping[str, object]) -> dict[str, object]:
    asset_summary = _as_mapping(asset_audit.get("summary"))
    proxy_summary = _as_mapping(proxy_audit.get("summary"))
    return {
        "tradable_history": {
            "coverage_start": asset_summary.get("coverage_start"),
            "coverage_end": asset_summary.get("coverage_end"),
            "target_window_fully_covered": bool(asset_summary.get("target_window_fully_covered")),
            "target_blocker_count": len(asset_summary.get("target_blockers") or []),
            "target_blockers": asset_summary.get("target_blockers") or [],
        },
        "research_proxy_history": {
            "coverage_start": proxy_summary.get("research_coverage_start"),
            "coverage_end": proxy_summary.get("research_coverage_end"),
            "target_window_fully_covered": bool(proxy_summary.get("target_window_fully_covered")),
            "missing_proxy": proxy_summary.get("missing_proxy") or [],
            "target_blockers": proxy_summary.get("target_blockers") or [],
        },
        "readiness": "research_ready_with_tradability_caveat"
        if bool(proxy_summary.get("target_window_fully_covered")) and not bool(asset_summary.get("target_window_fully_covered"))
        else "research_ready"
        if bool(proxy_summary.get("target_window_fully_covered")) and bool(asset_summary.get("target_window_fully_covered"))
        else "not_ready",
    }


def build_opportunity_research_foundation(data_dir: str | Path = DATA_DIR) -> dict[str, object]:
    payloads = _input_payloads(data_dir)
    asset_registry = payloads["asset_registry"]
    asset_audit = payloads["asset_universe_audit"]
    proxy_registry = payloads["asset_proxy_registry"]
    proxy_audit = payloads["asset_proxy_coverage_audit"]
    asset_metadata = _as_mapping(asset_registry.get("metadata"))
    proxy_metadata = _as_mapping(proxy_registry.get("metadata"))
    asset_summary = _as_mapping(asset_audit.get("summary"))
    proxy_summary = _as_mapping(proxy_audit.get("summary"))
    rows = _asset_rows(asset_registry, proxy_registry, asset_audit)
    coverage = _coverage_status(asset_audit, proxy_audit)
    summary = {
        "asset_count": asset_metadata.get("asset_count"),
        "enabled_assets": asset_summary.get("enabled_assets"),
        "category_counts": asset_metadata.get("category_counts"),
        "research_proxy_assets": proxy_metadata.get("with_proxy"),
        "research_proxy_count": proxy_metadata.get("proxy_count"),
        "direct_history_only_assets": len(proxy_summary.get("without_proxy") or []),
        "tradable_history_full_window": coverage["tradable_history"]["target_window_fully_covered"],
        "research_proxy_full_window": coverage["research_proxy_history"]["target_window_fully_covered"],
        "readiness": coverage["readiness"],
        "ready_for_scoring": False,
        "ready_for_ranking": False,
        "ready_for_allocation": False,
        "ready_for_trade": False,
        "key_read": (
            "V7.1 establishes a research-only asset opportunity foundation. "
            "Research proxy history is usable for long-window study, while tradable ETF history has coverage caveats."
        ),
    }
    return {
        "metadata": {
            "engine": "V7.1 Opportunity / Asset Research Layer Foundation",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source_engines": {
                "asset_registry": asset_metadata.get("engine"),
                "asset_universe_audit": _as_mapping(asset_audit.get("metadata")).get("engine"),
                "asset_proxy_registry": proxy_metadata.get("engine"),
                "asset_proxy_coverage_audit": _as_mapping(proxy_audit.get("metadata")).get("engine"),
            },
            "input_files": {name: _project_path(path) for name, path in REQUIRED_INPUTS.items()},
            "purpose": "Foundation only: asset universe, research proxy layer, coverage, and time-safety boundaries.",
        },
        "summary": summary,
        "coverage": coverage,
        "asset_rows": rows,
        "time_safety": {
            "uses_cache_date_bounds": True,
            "future_labels_used": False,
            "research_proxy_not_treated_as_tradable": True,
            "tradable_history_and_research_proxy_are_separated": True,
            "no_forward_fill_from_future": True,
        },
        "data_quality": {
            "uses_existing_asset_registry": True,
            "uses_existing_proxy_registry": True,
            "uses_existing_coverage_audits": True,
            "no_scoring": True,
            "no_ranking": True,
            "no_allocation": True,
            "no_backtest": True,
            "no_parameter_optimization": True,
        },
        "constraints": {
            "foundation_only": True,
            "research_only": True,
            "does_not_create_opportunity_score": True,
            "does_not_rank_assets": True,
            "does_not_modify_asset_universe": True,
            "does_not_generate_position": True,
            "no_percentage_exposure": True,
            "no_etf_weight": True,
            "no_portfolio_weight": True,
            "no_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
        },
    }


def write_opportunity_research_foundation(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
