from __future__ import annotations

from datetime import datetime, timezone
from bisect import bisect_right
import json
from pathlib import Path
from typing import Mapping

import pandas as pd

from adaptive_allocation.allocation_engine import build_allocation_intent_snapshot
from backtest.allocation_backtest_engine import run_v2_allocation_backtest
from backtest.benchmark_comparator import metrics_for_returns
from config import BASE_DIR, CACHE_DIR, DATA_DIR
from core.alpha_validation_engine import compound_return
from core.data_loader import cache_path_for, normalize_trade_date
from engine.regime_coverage_analyzer import expected_trade_dates, market_daily_cache_coverage
from industry_structure.industry_loader import load_industry_universe
from macro.macro_loader import DEFAULT_MACRO_INDICATORS, load_macro_indicator


DEFAULT_OUTPUT_PATH = DATA_DIR / "v2_full_cycle_validation.json"
V2_ALLOCATION_BACKTEST_PATH = DATA_DIR / "v2_allocation_backtest.json"
SNAPSHOT_MANIFEST_PATH = DATA_DIR / "history_snapshots" / "v2_full_cycle_manifest.json"
SIGNAL_SNAPSHOT_PATH = DATA_DIR / "history_snapshots" / "v2_full_cycle_rebalance_signals.json"

DESIRED_START = "20150101"
DESIRED_END = "20991231"

INDEX_REQUIREMENTS = {
    "000001.SH": "上证指数",
    "000300.SH": "沪深300指数",
    "000905.SH": "中证500指数",
}
ETF_REQUIREMENTS = {
    "510300.SH": "沪深300ETF",
    "510500.SH": "中证500ETF",
    "511880.SH": "银华日利ETF",
}

RISK_BUDGET_ORDER = ("defensive", "low", "medium", "medium_high", "high")


def _round(value: float | None, digits: int = 6) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _display_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(BASE_DIR).as_posix()
    except ValueError:
        return resolved.as_posix()


def _read_csv_dates(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"available": False, "file": _display_path(path), "start": None, "end": None, "rows": 0}
    frame = pd.read_csv(path, dtype={"trade_date": str})
    if frame.empty or "trade_date" not in frame:
        return {"available": False, "file": str(path), "start": None, "end": None, "rows": 0}
    dates = frame["trade_date"].astype(str).str.replace(r"\.0$", "", regex=True)
    return {
        "available": True,
        "file": _display_path(path),
        "start": str(dates.min()),
        "end": str(dates.max()),
        "rows": int(len(frame)),
    }


def _cache_range_for_index(ts_code: str) -> dict[str, object]:
    return _read_csv_dates(cache_path_for(ts_code))


def _cache_range_for_fund(ts_code: str) -> dict[str, object]:
    return _read_csv_dates(CACHE_DIR / f"fund_daily_{ts_code.replace('.', '_')}.csv")


def _max_start(items: list[Mapping[str, object]]) -> str | None:
    starts = [str(item["start"]) for item in items if item.get("available") and item.get("start")]
    return max(starts) if starts else None


def _min_end(items: list[Mapping[str, object]]) -> str | None:
    ends = [str(item["end"]) for item in items if item.get("available") and item.get("end")]
    return min(ends) if ends else None


def _range_status(items: Mapping[str, Mapping[str, object]]) -> dict[str, object]:
    values = list(items.values())
    missing = [name for name, item in items.items() if not item.get("available")]
    return {
        "series": dict(items),
        "common_start": _max_start(values),
        "common_end": _min_end(values),
        "missing": missing,
    }


def _macro_coverage(desired_start: str, desired_end: str) -> dict[str, object]:
    series: dict[str, dict[str, object]] = {}
    for indicator in DEFAULT_MACRO_INDICATORS:
        try:
            records = load_macro_indicator(indicator, "19000101", desired_end)
        except Exception as exc:
            series[indicator] = {
                "available": False,
                "start": None,
                "end": None,
                "records": 0,
                "error": str(exc),
            }
            continue
        dates = [record.observation_date for record in records]
        series[indicator] = {
            "available": bool(dates),
            "start": min(dates) if dates else None,
            "end": max(dates) if dates else None,
            "records": len(dates),
        }
    status = _range_status(series)
    blockers = []
    for name, item in series.items():
        if not item.get("available"):
            blockers.append(f"macro {name} missing")
        elif item.get("start") and str(item["start"]) > desired_start:
            blockers.append(f"macro {name} starts at {item['start']}")
    starts = [str(item["start"]) for item in series.values() if item.get("available") and item.get("start")]
    ends = [str(item["end"]) for item in series.values() if item.get("available") and item.get("end")]
    return {
        **status,
        "first_available_start": min(starts) if starts else None,
        "latest_available_end": max(ends) if ends else None,
        "desired_start": desired_start,
        "desired_end": desired_end,
        "blockers": blockers,
        "note": "Macro cache is local-record based; historical validation must not fabricate pre-cache macro observations.",
    }


def _market_structure_coverage(desired_start: str, desired_end: str) -> dict[str, object]:
    index_series = {
        code: {"label": label, **_cache_range_for_index(code)}
        for code, label in INDEX_REQUIREMENTS.items()
    }
    index_status = _range_status(index_series)
    breadth = {"available": False, "start": None, "end": None, "coverage_ratio": 0.0}
    index_path = cache_path_for("000001.SH")
    if index_path.exists():
        index_frame = pd.read_csv(index_path, dtype={"trade_date": str})
        trade_dates = expected_trade_dates(index_frame, start_date=desired_start, end_date=desired_end)
        cache_coverage = market_daily_cache_coverage(trade_dates, cache_dir=CACHE_DIR)
        available = cache_coverage.get("available_sample") or []
        missing = cache_coverage.get("missing_sample") or []
        breadth = {
            "available": int(cache_coverage["covered_days"]) > 0,
            "start": min(available) if available else None,
            "end": max(
                [
                    path.stem.replace("market_daily_", "")
                    for path in CACHE_DIR.glob("market_daily_*.csv")
                ],
                default=None,
            ),
            **cache_coverage,
            "missing_sample": missing,
        }
    hsgt_files = sorted(CACHE_DIR.glob("moneyflow_hsgt_*.csv"))
    hsgt_ranges = []
    for path in hsgt_files:
        parts = path.stem.split("_")
        if len(parts) >= 4:
            hsgt_ranges.append({"file": path.name, "start": parts[-2], "end": parts[-1]})
    hsgt = {
        "available": bool(hsgt_ranges),
        "file_count": len(hsgt_ranges),
        "start": min((item["start"] for item in hsgt_ranges), default=None),
        "end": max((item["end"] for item in hsgt_ranges), default=None),
    }
    blockers = []
    for name, item in index_series.items():
        if not item.get("available"):
            blockers.append(f"index {name} missing")
        elif item.get("start") and str(item["start"]) > desired_start:
            blockers.append(f"index {name} starts at {item['start']}")
    if float(breadth.get("coverage_ratio") or 0.0) < 0.95:
        blockers.append("market_daily breadth cache coverage below 95%")
    if hsgt.get("start") and str(hsgt["start"]) > desired_start:
        blockers.append(f"hsgt liquidity proxy starts at {hsgt['start']}")
    return {
        "indexes": index_status,
        "breadth": breadth,
        "liquidity_hsgt": hsgt,
        "common_start": max(
            value
            for value in [index_status["common_start"], breadth.get("start"), hsgt.get("start")]
            if value
        )
        if any([index_status["common_start"], breadth.get("start"), hsgt.get("start")])
        else None,
        "common_end": min(
            value
            for value in [index_status["common_end"], breadth.get("end"), hsgt.get("end")]
            if value
        )
        if any([index_status["common_end"], breadth.get("end"), hsgt.get("end")])
        else None,
        "blockers": blockers,
    }


def _industry_coverage(desired_start: str) -> dict[str, object]:
    assets, universe_status = load_industry_universe()
    series = {
        asset.code: {
            "label": asset.name,
            "source_type": asset.source_type,
            **(_cache_range_for_index(asset.code) if asset.source_type == "industry_index" else _cache_range_for_fund(asset.code)),
        }
        for asset in assets
    }
    status = _range_status(series)
    blockers = []
    for name, item in series.items():
        if not item.get("available"):
            blockers.append(f"industry {name} missing")
        elif item.get("start") and str(item["start"]) > desired_start:
            blockers.append(f"industry {name} starts at {item['start']}")
    return {
        **status,
        "asset_count": len(assets),
        "available_count": len(series) - len(status["missing"]),
        "universe": universe_status,
        "blockers": blockers[:20],
        "blocker_count": len(blockers),
    }


def _etf_proxy_coverage(desired_start: str) -> dict[str, object]:
    series = {
        code: {"label": label, **_cache_range_for_fund(code)}
        for code, label in ETF_REQUIREMENTS.items()
    }
    status = _range_status(series)
    blockers = []
    for name, item in series.items():
        if not item.get("available"):
            blockers.append(f"ETF proxy {name} missing")
        elif item.get("start") and str(item["start"]) > desired_start:
            blockers.append(f"ETF proxy {name} starts at {item['start']}")
    return {**status, "blockers": blockers}


def _artifact_window(path: Path, date_key: str = "date") -> dict[str, object]:
    if not path.exists():
        return {"available": False, "start": None, "end": None, "rows": 0}
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("daily_returns") or payload.get("shadow_returns") or payload.get("equity_curve") or []
    dates = [str(row.get(date_key) or "") for row in rows if isinstance(row, Mapping) and row.get(date_key)]
    return {
        "available": bool(dates),
        "start": min(dates) if dates else None,
        "end": max(dates) if dates else None,
        "rows": len(dates),
        "file": _display_path(path),
    }


def build_data_coverage_audit(
    *,
    desired_start: str,
    desired_end: str,
) -> dict[str, object]:
    macro = _macro_coverage(desired_start, desired_end)
    market_structure = _market_structure_coverage(desired_start, desired_end)
    industry = _industry_coverage(desired_start)
    etf_proxy = _etf_proxy_coverage(desired_start)
    legacy = {
        "old_s1": _artifact_window(DATA_DIR / "shadow_equity_curve.json"),
        "m2_macro_style": _artifact_window(DATA_DIR / "macro_style_etf_backtest.json"),
    }
    operational_start_candidates = [
        macro.get("first_available_start"),
        industry.get("common_start"),
        etf_proxy.get("common_start"),
        market_structure.get("indexes", {}).get("common_start"),
    ]
    operational_end_candidates = [
        macro.get("latest_available_end"),
        industry.get("common_end"),
        etf_proxy.get("common_end"),
        market_structure.get("indexes", {}).get("common_end"),
    ]
    operational_start = max(str(value) for value in operational_start_candidates if value)
    operational_end = min(str(value) for value in operational_end_candidates if value)
    blockers = [
        *macro.get("blockers", []),
        *market_structure.get("blockers", []),
        *industry.get("blockers", []),
        *etf_proxy.get("blockers", []),
    ]
    can_cover_desired = not blockers and operational_start <= desired_start and operational_end >= desired_end
    return {
        "desired_window": {"start": desired_start, "end": desired_end},
        "operational_validation_window": {"start": operational_start, "end": operational_end},
        "can_cover_desired_window": can_cover_desired,
        "blockers": blockers,
        "blocker_count": len(blockers),
        "modules": {
            "macro": macro,
            "market_structure": market_structure,
            "industry_opportunity": industry,
            "theme_risk": {
                "depends_on": "industry_opportunity top themes and their historical price positions",
                "common_start": industry.get("common_start"),
                "common_end": industry.get("common_end"),
                "blockers": industry.get("blockers", []),
            },
            "etf_proxy": etf_proxy,
            "legacy_benchmarks": legacy,
        },
        "policy": {
            "do_not_fabricate_history": True,
            "do_not_treat_partial_cache_as_full_cycle": True,
            "report_window_gap_in_web": True,
        },
    }


def _adjust_budget(base: str, delta: int) -> str:
    index = RISK_BUDGET_ORDER.index(base)
    return RISK_BUDGET_ORDER[max(0, min(len(RISK_BUDGET_ORDER) - 1, index + delta))]


def _legacy_v2_budget(signal: Mapping[str, object]) -> str:
    structural_state = str(signal.get("structural_state") or "RANGE")
    macro_state = str(signal.get("macro_state") or "")
    market_structure_state = str(signal.get("market_structure_state") or "")
    theme_risk_level = str(signal.get("theme_risk_level") or "medium")
    if structural_state == "BROAD_BULL":
        base = "high"
    elif structural_state == "STRUCTURAL_BULL_ROTATION":
        base = "medium_high"
    elif structural_state == "BEAR_REBOUND":
        base = "low"
    elif structural_state in {"BEAR_STRUCTURE", "WEAK_MARKET"}:
        base = "defensive"
    else:
        base = "medium"
    if macro_state == "BEAR":
        base = _adjust_budget(base, -2)
    elif macro_state == "BULL" and market_structure_state == "BULL_BROADENING":
        base = _adjust_budget(base, 1)
    if theme_risk_level == "high":
        base = _adjust_budget(base, -2)
    elif theme_risk_level == "medium":
        base = _adjust_budget(base, -1)
    return base


def _snapshot_from_signal(signal: Mapping[str, object], *, risk_budget: str, allocation_state: str) -> dict[str, object]:
    return {
        "as_of": signal.get("as_of") or signal.get("date"),
        "structural_state": signal.get("structural_state"),
        "allocation_structural_state": allocation_state,
        "allocation_intent": {
            "risk_budget": risk_budget,
            "style_preference": signal.get("style_preference") or [],
        },
        "risk_adjustments": {
            "theme_risk_level": signal.get("theme_risk_level"),
            "allocation_structural_state": allocation_state,
            "structural_bull_policy": {
                "applies": False,
                "comparison_only": True,
                "note": "Legacy V2 baseline uses the pre-V2.5.3 structural-state-to-risk-budget mapping.",
            },
        },
        "evidence": {
            "macro": {"state": signal.get("macro_state")},
            "market_structure": {"state": signal.get("market_structure_state")},
        },
        "explanation": signal.get("explanation") or [],
    }


def _signal_history_snapshot_builder(
    signals: list[Mapping[str, object]],
    *,
    legacy: bool,
):
    ordered = sorted(
        [signal for signal in signals if signal.get("date")],
        key=lambda item: str(item["date"]),
    )
    dates = [str(signal["date"]) for signal in ordered]

    def builder(date_text: str) -> dict[str, object]:
        if not ordered:
            return build_allocation_intent_snapshot(date_text, cache_only=True)
        position = bisect_right(dates, str(date_text)) - 1
        signal = ordered[max(0, position)]
        if legacy:
            return _snapshot_from_signal(
                signal,
                risk_budget=_legacy_v2_budget(signal),
                allocation_state="LEGACY_V2_BASELINE",
            )
        return _snapshot_from_signal(
            signal,
            risk_budget=str(signal.get("risk_budget") or "medium"),
            allocation_state=str(signal.get("allocation_structural_state") or signal.get("structural_state") or "unknown"),
        )

    return builder


def _daily_returns_frame(payload: Mapping[str, object]) -> pd.DataFrame:
    rows = payload.get("daily_returns") or []
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame = frame.sort_values("date").reset_index(drop=True)
    for column in frame.columns:
        if column.endswith("_return") or column in {"turnover", "target_exposure"}:
            frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    return frame


def _metrics_from_payload(payload: Mapping[str, object], return_column: str) -> dict[str, object]:
    frame = _daily_returns_frame(payload)
    if frame.empty or return_column not in frame:
        return {}
    return metrics_for_returns(frame[return_column])


def _comparison_table(
    refined_payload: Mapping[str, object],
    legacy_payload: Mapping[str, object],
) -> dict[str, dict[str, object]]:
    refined_frame = _daily_returns_frame(refined_payload)
    legacy_frame = _daily_returns_frame(legacy_payload)
    result = {
        "v2_refined_structural_policy": {
            "label": "V2 refined structural policy",
            **_metrics_from_payload(refined_payload, "v2_return"),
            "average_exposure": refined_payload.get("summary", {}).get("average_exposure"),
        },
        "v2_baseline": {
            "label": "V2 baseline pre-V2.5.3 policy",
            **_metrics_from_payload(legacy_payload, "v2_return"),
            "average_exposure": legacy_payload.get("summary", {}).get("average_exposure"),
        },
        "benchmark_510300": {
            "label": "510300 沪深300ETF",
            **_metrics_from_payload(refined_payload, "benchmark_510300_return"),
            "average_exposure": 1.0,
        },
        "benchmark_510500": {
            "label": "510500 中证500ETF",
            **_metrics_from_payload(refined_payload, "benchmark_510500_return"),
            "average_exposure": 1.0,
        },
        "old_s1": {
            "label": "S1.1 仓位风控",
            **_metrics_from_payload(refined_payload, "old_s1_return"),
            "average_exposure": None,
        },
        "m2_macro_style": {
            "label": "M2.1 Macro-Style-ETF",
            **_metrics_from_payload(refined_payload, "m2_macro_style_return"),
            "average_exposure": None,
        },
    }
    if not refined_frame.empty:
        buy_hold = 0.5 * refined_frame["benchmark_510300_return"] + 0.5 * refined_frame["benchmark_510500_return"]
        result["buy_hold_equal_510300_510500"] = {
            "label": "Buy&Hold 50/50 510300+510500",
            **metrics_for_returns(buy_hold),
            "average_exposure": 1.0,
        }
    if not refined_frame.empty and not legacy_frame.empty:
        result["v2_refined_structural_policy"]["excess_vs_v2_baseline"] = _round(
            compound_return(refined_frame["v2_return"]) - compound_return(legacy_frame["v2_return"])
        )
    return result


def _key_regime_attribution(payload: Mapping[str, object]) -> dict[str, object]:
    attribution = payload.get("state_attribution") or {}
    macro = attribution.get("macro_state") or {}
    structural = attribution.get("structural_state") or {}
    allocation_structural = attribution.get("allocation_structural_state") or {}
    return {
        "macro_bull": macro.get("BULL"),
        "macro_bear": macro.get("BEAR"),
        "structural_bull_rotation": structural.get("STRUCTURAL_BULL_ROTATION"),
        "broad_bull": structural.get("BROAD_BULL"),
        "allocation_structural_states": allocation_structural,
    }


def _load_v2_allocation_artifact(path: str | Path = V2_ALLOCATION_BACKTEST_PATH) -> dict[str, object] | None:
    artifact = Path(path)
    if not artifact.exists():
        return None
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _write_history_snapshot_manifest(
    payload: Mapping[str, object],
    *,
    manifest_path: str | Path = SNAPSHOT_MANIFEST_PATH,
    signal_path: str | Path = SIGNAL_SNAPSHOT_PATH,
) -> dict[str, object]:
    manifest = {
        "engine": "V2.6.1 Historical Snapshot Reconstruction Manifest",
        "generated_at": payload["metadata"]["generated_at"],
        "storage_policy": "compressed_rebalance_snapshots",
        "reason": "Daily JSON snapshots would duplicate large module payloads; V2.6.1 stores rebalance-date signal snapshots and full daily return series in v2_full_cycle_validation.json.",
        "full_cycle_artifact": _display_path(DEFAULT_OUTPUT_PATH),
        "signal_snapshot_artifact": _display_path(signal_path),
        "requested_window": payload["metadata"]["desired_window"],
        "validation_window": payload["metadata"]["validation_window"],
        "rebalance_signal_count": len(payload.get("refined_policy", {}).get("signals", [])),
        "constraints": payload["constraints"],
    }
    signals = {
        "engine": "V2.6.1 Compressed Rebalance Snapshot History",
        "generated_at": payload["metadata"]["generated_at"],
        "signals": payload.get("refined_policy", {}).get("signals", []),
    }
    for path, item in ((Path(manifest_path), manifest), (Path(signal_path), signals)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(item, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def run_full_cycle_validation(
    *,
    desired_start: str = DESIRED_START,
    desired_end: str = DESIRED_END,
    rebalance_every_sessions: int = 20,
) -> dict[str, object]:
    start = normalize_trade_date(desired_start)
    end = normalize_trade_date(desired_end)
    coverage = build_data_coverage_audit(desired_start=start, desired_end=end)
    operational = coverage["operational_validation_window"]
    validation_start = max(start, str(operational["start"]))
    validation_end = min(end, str(operational["end"]))
    existing_refined = _load_v2_allocation_artifact()
    if existing_refined and existing_refined.get("signals"):
        refined = existing_refined
        first_signal = str(refined["signals"][0].get("date") or refined["summary"]["start_date"])
        validation_start = max(validation_start, first_signal)
        validation_end = min(validation_end, str(refined["summary"]["end_date"]))
    else:
        refined = run_v2_allocation_backtest(
            start_date=validation_start,
            end_date=validation_end,
            rebalance_every_sessions=rebalance_every_sessions,
            cache_only=True,
        )
    legacy = run_v2_allocation_backtest(
        start_date=validation_start,
        end_date=validation_end,
        rebalance_every_sessions=rebalance_every_sessions,
        cache_only=True,
        snapshot_builder=_signal_history_snapshot_builder(list(refined.get("signals") or []), legacy=True),
    )
    comparison = _comparison_table(refined, legacy)
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload: dict[str, object] = {
        "metadata": {
            "engine": "V2.6.1 Historical Coverage Expansion & Full Cycle Validation",
            "generated_at": generated_at,
            "desired_window": {"start": start, "end": end},
            "validation_window": {
                "start": refined["summary"]["start_date"],
                "end": refined["summary"]["end_date"],
            },
            "rebalance_every_sessions": rebalance_every_sessions,
            "result_type": "best_available_window_validation",
            "full_cycle_claim": bool(coverage["can_cover_desired_window"]),
            "signal_source": _display_path(V2_ALLOCATION_BACKTEST_PATH) if existing_refined else "dynamic_snapshot_builder",
        },
        "coverage_audit": coverage,
        "comparison": comparison,
        "refined_policy": {
            "summary": refined["summary"],
            "performance_metrics": refined["performance_metrics"],
            "state_attribution": refined["state_attribution"],
            "key_regime_attribution": _key_regime_attribution(refined),
            "signals": refined["signals"],
            "validation": refined["validation"],
            "data_quality": refined["data_quality"],
        },
        "v2_baseline": {
            "summary": legacy["summary"],
            "performance_metrics": legacy["performance_metrics"],
            "state_attribution": legacy["state_attribution"],
            "key_regime_attribution": _key_regime_attribution(legacy),
            "signals": legacy["signals"],
            "validation": legacy["validation"],
            "data_quality": legacy["data_quality"],
        },
        "equity_curve": refined["equity_curve"],
        "daily_returns": refined["daily_returns"],
        "conclusion": [
            "V2.6.1 does not change strategy rules, thresholds, factors, ETF selection, or historical labels.",
            "The current local cache cannot support a true 2015-2026 V2 full-cycle claim because macro and industry/theme evidence begin in 2024.",
            "The reported backtest is the best available walk-forward window, not a completed full-cycle validation.",
        ],
        "constraints": {
            "no_strategy_rule_change": True,
            "no_threshold_tuning": True,
            "no_new_factor": True,
            "no_etf_selection": True,
            "no_manual_label_fix": True,
            "walk_forward": True,
            "no_lookahead_bias": True,
            "evaluation_only": True,
        },
    }
    payload["history_snapshot_manifest"] = _write_history_snapshot_manifest(payload)
    return payload


def write_full_cycle_validation(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
