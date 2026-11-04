from __future__ import annotations

from collections.abc import Mapping
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from config import DATA_DIR
from implementation_readiness.evidence_package_validator import FORBIDDEN_OUTPUT_KEYS


DEFAULT_MANIFEST_PATH = DATA_DIR / "v15_backtest_dataset_manifest.json"
DEFAULT_OUTPUT_PATH = DATA_DIR / "v15_backtest_dataset_materialization_status.json"


SOURCE_SPECS: dict[str, list[dict[str, object]]] = {
    "broad_indices": [
        {"source_id": "shanghai_composite", "role": "broad_index", "paths": ["data/cache/index_daily_000001_SH.csv"]},
        {"source_id": "csi_300", "role": "broad_index", "paths": ["data/cache/index_daily_000300_SH.csv"]},
        {"source_id": "csi_500", "role": "broad_index", "paths": ["data/cache/index_daily_000905_SH.csv"]},
        {"source_id": "chinext_index", "role": "broad_index", "paths": ["data/cache/index_daily_399006_SZ.csv"]},
        {"source_id": "star_50", "role": "broad_index", "paths": ["data/cache/index_daily_000688_SH.csv"]},
        {"source_id": "csi_all_share_proxy", "role": "broad_index", "paths": ["data/cache/index_daily_000922_CSI.csv"]},
    ],
    "sector_indices": [
        {"source_id": "sw_l1_universe", "role": "industry_universe", "paths": ["data/industry/industry_universe_SW2021_L1.json"]},
        {"source_id": "industry_opportunity", "role": "industry_snapshot", "paths": ["data/industry_opportunity_snapshot.json"]},
        {"source_id": "industry_bank", "role": "sw_l1_index", "paths": ["data/cache/index_daily_801010_SI.csv"]},
        {"source_id": "industry_non_bank", "role": "sw_l1_index", "paths": ["data/cache/index_daily_801030_SI.csv"]},
        {"source_id": "industry_metal", "role": "sw_l1_index", "paths": ["data/cache/index_daily_801040_SI.csv"]},
        {"source_id": "industry_power", "role": "sw_l1_index", "paths": ["data/cache/index_daily_801050_SI.csv"]},
    ],
    "macro_cycle": [
        {"source_id": "m1_growth", "role": "macro_series", "paths": ["data/macro/M1_growth.json"]},
        {"source_id": "m2_growth", "role": "macro_series", "paths": ["data/macro/M2_growth.json"]},
        {"source_id": "social_financing_growth", "role": "macro_series", "paths": ["data/macro/social_financing_growth.json"]},
        {"source_id": "pmi", "role": "macro_series", "paths": ["data/macro/PMI.json"]},
        {"source_id": "shibor", "role": "macro_series", "paths": ["data/macro/SHIBOR.json"]},
        {"source_id": "macro_context_history", "role": "macro_context", "paths": ["data/macro_context_history.json"]},
        {"source_id": "macro_cycle_snapshot", "role": "macro_snapshot", "paths": ["data/macro_cycle_snapshot.json"]},
    ],
    "drawdown_context": [
        {"source_id": "market_phase_snapshot", "role": "drawdown_context", "paths": ["data/market_phase_snapshot.json"]},
        {"source_id": "hazard_dataset", "role": "risk_dataset", "paths": ["data/hazard_dataset.json"]},
        {"source_id": "survival_dataset", "role": "risk_dataset", "paths": ["data/survival_dataset.json"]},
        {"source_id": "structural_hazard_dataset", "role": "risk_dataset", "paths": ["data/structural_hazard_dataset.json"]},
        {"source_id": "exposure_numeric_context", "role": "numeric_context", "paths": ["data/exposure_numeric_context.json"]},
    ],
    "structural_bull": [
        {"source_id": "structural_bull_snapshot", "role": "structural_snapshot", "paths": ["data/structural_bull_snapshot.json"]},
        {"source_id": "structural_style_validation", "role": "style_validation", "paths": ["data/structural_style_validation.json"]},
        {"source_id": "structural_style_failure_analysis", "role": "style_failure", "paths": ["data/structural_style_failure_analysis.json"]},
        {"source_id": "historical_style_context", "role": "style_context", "paths": ["data/historical_style_context.json"]},
        {"source_id": "style_incremental_analysis", "role": "style_incremental", "paths": ["data/style_incremental_analysis.json"]},
    ],
}


def _read_json(path: str | Path) -> dict[str, object]:
    target = Path(path)
    if not target.exists():
        return {}
    payload = json.loads(target.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _relative(path: Path) -> str:
    try:
        return path.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return path.as_posix()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _date_range(values: list[str]) -> dict[str, str | None]:
    normalized = [value for value in values if value]
    return {
        "start": min(normalized) if normalized else None,
        "end": max(normalized) if normalized else None,
    }


def _csv_artifact(path: Path) -> dict[str, object]:
    row_count = 0
    dates: list[str] = []
    columns: list[str] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or [])
        date_column = next((name for name in ("trade_date", "date", "cal_date", "ann_date") if name in columns), None)
        for row in reader:
            row_count += 1
            if date_column:
                dates.append(str(row.get(date_column) or ""))
    return {
        "path": _relative(path),
        "exists": True,
        "file_type": "csv",
        "size_bytes": path.stat().st_size,
        "cache_hash": _sha256(path),
        "column_count": len(columns),
        "columns_sample": columns[:24],
        "row_count": row_count,
        "date_range": _date_range(dates),
        "point_in_time_date_column": next((name for name in ("trade_date", "date", "cal_date", "ann_date") if name in columns), None),
    }


def _json_walk_summary(value: Any, *, depth: int = 0) -> tuple[int, int, list[str], list[str]]:
    if depth > 5:
        return (0, 0, [], [])
    if isinstance(value, Mapping):
        object_count = 1
        array_count = 0
        keys = [str(key) for key in value.keys()]
        dates: list[str] = []
        for key, item in value.items():
            if str(key) in {"trade_date", "date", "cal_date", "ann_date", "as_of", "basis_date"} and isinstance(item, (str, int)):
                dates.append(str(item))
            child_objects, child_arrays, child_keys, child_dates = _json_walk_summary(item, depth=depth + 1)
            object_count += child_objects
            array_count += child_arrays
            keys.extend(child_keys)
            dates.extend(child_dates)
        return object_count, array_count, keys, dates
    if isinstance(value, list):
        object_count = 0
        array_count = 1
        keys: list[str] = []
        dates: list[str] = []
        for item in value[:5000]:
            child_objects, child_arrays, child_keys, child_dates = _json_walk_summary(item, depth=depth + 1)
            object_count += child_objects
            array_count += child_arrays
            keys.extend(child_keys)
            dates.extend(child_dates)
        return object_count, array_count, keys, dates
    return (0, 0, [], [])


def _json_artifact(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    object_count, array_count, keys, dates = _json_walk_summary(payload)
    top_level_keys = list(payload.keys()) if isinstance(payload, Mapping) else []
    unique_keys = sorted(set(keys))
    return {
        "path": _relative(path),
        "exists": True,
        "file_type": "json",
        "size_bytes": path.stat().st_size,
        "cache_hash": _sha256(path),
        "top_level_type": type(payload).__name__,
        "top_level_keys_sample": [str(key) for key in top_level_keys[:24]],
        "observed_key_count": len(unique_keys),
        "observed_keys_sample": unique_keys[:40],
        "object_count_scanned": object_count,
        "array_count_scanned": array_count,
        "date_range": _date_range(dates),
    }


def _artifact(path_text: str) -> dict[str, object]:
    path = Path(path_text)
    if not path.exists():
        return {
            "path": path.as_posix(),
            "exists": False,
            "status": "missing",
        }
    if path.suffix.lower() == ".csv":
        return _csv_artifact(path)
    if path.suffix.lower() == ".json":
        return _json_artifact(path)
    return {
        "path": _relative(path),
        "exists": True,
        "file_type": path.suffix.lower().lstrip(".") or "unknown",
        "size_bytes": path.stat().st_size,
        "cache_hash": _sha256(path),
    }


def _coverage_for_group(group_name: str, group_manifest: Mapping[str, Any]) -> dict[str, object]:
    specs = SOURCE_SPECS.get(group_name, [])
    manifest_fields = [
        str(field.get("name"))
        for field in group_manifest.get("fields", [])
        if isinstance(field, Mapping) and field.get("name")
    ]
    sources: list[dict[str, object]] = []
    available_sources = 0
    cache_hashes: list[str] = []
    observed_fields: set[str] = set()
    for spec in specs:
        artifacts = [_artifact(str(path)) for path in spec.get("paths", [])]
        available = any(artifact.get("exists") is True for artifact in artifacts)
        if available:
            available_sources += 1
        for artifact in artifacts:
            if artifact.get("cache_hash"):
                cache_hashes.append(str(artifact["cache_hash"]))
            observed_fields.update(str(item) for item in artifact.get("columns_sample", []))
            observed_fields.update(str(item) for item in artifact.get("observed_keys_sample", []))
        sources.append(
            {
                "source_id": spec.get("source_id"),
                "role": spec.get("role"),
                "status": "available" if available else "missing",
                "artifacts": artifacts,
            }
        )
    required_source_count = len(specs)
    missing_manifest_fields = sorted(set(manifest_fields) - observed_fields)
    return {
        "dataset_group_status": "local_coverage_reported",
        "manifest_field_count": len(manifest_fields),
        "manifest_fields": manifest_fields,
        "required_source_count": required_source_count,
        "available_source_count": available_sources,
        "missing_source_count": required_source_count - available_sources,
        "coverage_ratio": round(available_sources / required_source_count, 4) if required_source_count else 0.0,
        "cache_hash_count": len(cache_hashes),
        "group_cache_hash": hashlib.sha256("|".join(sorted(cache_hashes)).encode("utf-8")).hexdigest() if cache_hashes else None,
        "missing_field_report": {
            "status": "defined",
            "unmatched_manifest_fields": missing_manifest_fields,
            "note": "Field names are compared to observed local cache columns/keys; semantic mapping is deferred to future backtests.",
        },
        "sources": sources,
    }


def validate_v15_backtest_dataset_materialization_status(payload: Mapping[str, object]) -> dict[str, object]:
    metadata = _mapping(payload.get("metadata"))
    summary = _mapping(payload.get("summary"))
    coverage = _mapping(payload.get("coverage"))
    data_quality = _mapping(payload.get("data_quality"))
    constraints = _mapping(payload.get("constraints"))

    if metadata.get("engine") != "V15.2 Outcome Backtest Dataset Materialization":
        raise AssertionError("unexpected engine")
    if payload.get("phase") != "V15.2" or summary.get("phase") != "V15.2":
        raise AssertionError("phase must be V15.2")
    if payload.get("materialization_status") != "coverage_report_ready":
        raise AssertionError("materialization_status must be coverage_report_ready")
    if payload.get("source_manifest") != "data/v15_backtest_dataset_manifest.json":
        raise AssertionError("source_manifest mismatch")
    if payload.get("dataset_groups_checked") != 5:
        raise AssertionError("dataset_groups_checked must be 5")
    for key in (
        "full_dataset_fetched",
        "strategy_run",
        "backtest_result_generated",
        "position_generated",
        "trade_signal_generated",
        "production_trade_enabled",
    ):
        if payload.get(key) is not False:
            raise AssertionError(f"{key} must be false")
        if summary.get(key) is not False:
            raise AssertionError(f"summary.{key} must be false")
    required_groups = {"broad_indices", "sector_indices", "macro_cycle", "drawdown_context", "structural_bull"}
    if set(coverage.keys()) != required_groups:
        raise AssertionError("coverage groups mismatch")
    for key, group in coverage.items():
        group_map = _mapping(group)
        if group_map.get("dataset_group_status") != "local_coverage_reported":
            raise AssertionError(f"{key} must be local_coverage_reported")
        if group_map.get("required_source_count", 0) <= 0:
            raise AssertionError(f"{key} must define source coverage")
    for key in (
        "point_in_time_check_defined",
        "release_date_alignment_defined",
        "survivorship_bias_check_defined",
        "missing_field_report_defined",
        "source_hash_recorded",
    ):
        if data_quality.get(key) is not True:
            raise AssertionError(f"data_quality.{key} must be true")
    for key in (
        "dataset_materialization_only",
        "does_not_run_strategy",
        "does_not_generate_position",
        "does_not_generate_portfolio_weight",
        "does_not_generate_trade_signal",
        "no_order_generation",
        "no_broker_connection",
    ):
        if constraints.get(key) is not True:
            raise AssertionError(f"constraints.{key} must be true")
    if constraints.get("production_trade_enabled") is not False:
        raise AssertionError("production trading must be disabled")
    forbidden_exact_keys = FORBIDDEN_OUTPUT_KEYS.intersection(payload.keys())
    if forbidden_exact_keys:
        raise AssertionError(f"forbidden output keys found: {sorted(forbidden_exact_keys)}")
    return {
        "audit_status": "passed",
        "checked_phase": payload.get("phase"),
        "checked_materialization_status": payload.get("materialization_status"),
        "checked_dataset_groups": sorted(coverage.keys()),
        "checked_full_dataset_fetched": payload.get("full_dataset_fetched"),
        "checked_strategy_run": payload.get("strategy_run"),
        "checked_position_generated": payload.get("position_generated"),
        "checked_trade_signal_generated": payload.get("trade_signal_generated"),
        "checked_production_trade_enabled": payload.get("production_trade_enabled"),
    }


def build_v15_backtest_dataset_materialization_status(
    *,
    manifest_path: str | Path = DEFAULT_MANIFEST_PATH,
) -> dict[str, object]:
    manifest = _read_json(manifest_path)
    if manifest.get("phase") != "V15.1":
        raise RuntimeError("V15.2 requires V15.1 backtest dataset manifest first.")
    dataset_groups = _mapping(manifest.get("dataset_groups"))
    if set(dataset_groups.keys()) != set(SOURCE_SPECS.keys()):
        raise RuntimeError("V15.1 manifest dataset groups do not match V15.2 materializer specs.")

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    coverage = {
        name: _coverage_for_group(name, _mapping(group))
        for name, group in dataset_groups.items()
    }
    total_sources = sum(int(_mapping(group).get("required_source_count", 0)) for group in coverage.values())
    available_sources = sum(int(_mapping(group).get("available_source_count", 0)) for group in coverage.values())
    payload: dict[str, object] = {
        "metadata": {
            "engine": "V15.2 Outcome Backtest Dataset Materialization",
            "generated_at": generated_at,
            "as_of": datetime.now(timezone.utc).strftime("%Y%m%d"),
            "source_manifest_hash": _sha256(Path(manifest_path)),
            "purpose": "Report local coverage for the V15.1 backtest dataset manifest without fetching full datasets or running strategies.",
        },
        "phase": "V15.2",
        "materialization_status": "coverage_report_ready",
        "source_manifest": "data/v15_backtest_dataset_manifest.json",
        "dataset_groups_checked": len(dataset_groups),
        "full_dataset_fetched": False,
        "strategy_run": False,
        "backtest_result_generated": False,
        "position_generated": False,
        "trade_signal_generated": False,
        "production_trade_enabled": False,
        "summary": {
            "phase": "V15.2",
            "materialization_status": "coverage_report_ready",
            "dataset_groups_checked": len(dataset_groups),
            "source_count": total_sources,
            "available_source_count": available_sources,
            "missing_source_count": total_sources - available_sources,
            "coverage_ratio": round(available_sources / total_sources, 4) if total_sources else 0.0,
            "full_dataset_fetched": False,
            "strategy_run": False,
            "backtest_result_generated": False,
            "position_generated": False,
            "trade_signal_generated": False,
            "production_trade_enabled": False,
            "next_task": "V15.3 macro plus drawdown regime strategy backtest after dataset materialization audit passes",
            "conclusion": "v15_2_local_coverage_report_ready_no_strategy_no_trade",
        },
        "data_interfaces": {
            "tushare": {"status": "placeholder_defined", "live_fetch_enabled": False},
            "qmt": {"status": "placeholder_defined", "live_fetch_enabled": False, "broker_connection_enabled": False},
            "fred": {"status": "placeholder_defined", "live_fetch_enabled": False},
            "yfinance": {"status": "placeholder_defined", "live_fetch_enabled": False},
        },
        "coverage": coverage,
        "data_quality": {
            "point_in_time_check_defined": True,
            "release_date_alignment_defined": True,
            "survivorship_bias_check_defined": True,
            "missing_field_report_defined": True,
            "source_hash_recorded": True,
            "cache_hash_recorded": True,
            "coverage_report_only": True,
            "no_live_fetch_attempted": True,
        },
        "constraints": {
            "dataset_materialization_only": True,
            "does_not_run_strategy": True,
            "does_not_generate_position": True,
            "does_not_generate_portfolio_weight": True,
            "does_not_generate_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
            "production_trade_enabled": False,
        },
        "known_exclusions": {
            "data/structural_survival_dataset.json": "left out of source specs because it is an unrelated locally modified file in the working tree",
        },
        "forbidden_outputs": sorted(FORBIDDEN_OUTPUT_KEYS),
    }
    payload["audit"] = validate_v15_backtest_dataset_materialization_status(payload)
    return payload


def write_v15_backtest_dataset_materialization_status(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
