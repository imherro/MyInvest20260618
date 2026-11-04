from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd

from asset_opportunity.asset_proxy_loader import load_research_proxy_history
from asset_opportunity.asset_proxy_registry import DEFAULT_PROXY_REGISTRY_PATH, read_asset_proxy_registry
from config import DATA_DIR
from core.benchmark_loader import read_benchmark_cache
from core.data_loader import normalize_trade_date


DEFAULT_OUTPUT_PATH = DATA_DIR / "opportunity_context_features.json"
DEFAULT_START_DATE = "20150105"
DEFAULT_BENCHMARKS = {
    "hs300": {"code": "510300.SH", "name": "沪深300ETF"},
    "csi500": {"code": "510500.SH", "name": "中证500ETF"},
}
CONTEXT_INPUTS = {
    "v7_1_foundation": DATA_DIR / "opportunity_research_foundation.json",
    "risk_gradient": DATA_DIR / "exposure_gradient_analysis.json",
    "protection_score": DATA_DIR / "exposure_context_score_audit.json",
    "two_axis_context": DATA_DIR / "two_axis_context_validation.json",
    "context_information_attribution": DATA_DIR / "context_information_attribution.json",
    "historical_style_context": DATA_DIR / "historical_style_context.json",
}


def _read_json(path: str | Path) -> dict[str, object]:
    target = Path(path)
    if not target.exists():
        return {}
    payload = json.loads(target.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _as_mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _finite(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _round(value: object, digits: int = 6) -> float | None:
    number = _finite(value)
    return round(number, digits) if number is not None else None


def _project_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _price_frame(frame: pd.DataFrame, as_of: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["trade_date", "close"])
    result = frame.copy()
    result["trade_date"] = result["trade_date"].astype(str).str.replace(r"\.0$", "", regex=True)
    result["close"] = pd.to_numeric(result["close"], errors="coerce")
    result = result.dropna(subset=["trade_date", "close"])
    result = result[result["trade_date"] <= as_of]
    return result[["trade_date", "close"]].sort_values("trade_date").reset_index(drop=True)


def _latest_date(frame: pd.DataFrame, requested_as_of: str) -> str | None:
    prices = _price_frame(frame, requested_as_of)
    if prices.empty:
        return None
    return str(prices["trade_date"].iloc[-1])


def _latest_common_as_of(
    histories: Mapping[str, pd.DataFrame],
    benchmarks: Mapping[str, pd.DataFrame],
    requested_as_of: str,
) -> str:
    latest_dates = [_latest_date(frame, requested_as_of) for frame in histories.values()]
    latest_dates.extend(_latest_date(frame, requested_as_of) for frame in benchmarks.values())
    valid = [date for date in latest_dates if date]
    if len(valid) != len(latest_dates):
        missing = [code for code, frame in histories.items() if _latest_date(frame, requested_as_of) is None]
        missing.extend(f"benchmark:{code}" for code, frame in benchmarks.items() if _latest_date(frame, requested_as_of) is None)
        raise RuntimeError(f"missing V7.2 feature history: {missing}")
    return min(valid)


def _return_over_sessions(frame: pd.DataFrame, sessions: int) -> float | None:
    if len(frame) <= sessions:
        return None
    latest = _finite(frame["close"].iloc[-1])
    base = _finite(frame["close"].iloc[-sessions - 1])
    if latest is None or base is None or base <= 0:
        return None
    return latest / base - 1.0


def _moving_average(frame: pd.DataFrame, sessions: int) -> float | None:
    if len(frame) < sessions:
        return None
    return _finite(frame["close"].tail(sessions).mean())


def _distance_to_ma(frame: pd.DataFrame, sessions: int) -> float | None:
    if frame.empty:
        return None
    close = _finite(frame["close"].iloc[-1])
    ma = _moving_average(frame, sessions)
    if close is None or ma in (None, 0.0):
        return None
    return close / ma - 1.0


def _volatility(frame: pd.DataFrame, sessions: int = 60) -> float | None:
    if len(frame) <= sessions:
        return None
    returns = frame["close"].pct_change().tail(sessions).dropna()
    if returns.empty:
        return None
    return _finite(returns.std() * math.sqrt(252))


def _max_drawdown(frame: pd.DataFrame, sessions: int = 120) -> float | None:
    if frame.empty:
        return None
    close = frame["close"].tail(min(sessions, len(frame))).astype(float)
    if close.empty:
        return None
    running_high = close.cummax()
    drawdown = close / running_high - 1.0
    return _finite(drawdown.min())


def _price_percentile(frame: pd.DataFrame, sessions: int = 252) -> float | None:
    if frame.empty:
        return None
    window = frame["close"].tail(min(sessions, len(frame))).dropna()
    if window.empty:
        return None
    latest = window.iloc[-1]
    return _finite((window <= latest).sum() / len(window))


def _source_payload(mapping) -> dict[str, object]:
    if mapping.research_proxy is None:
        return {
            "source": mapping.asset_code,
            "source_name": mapping.asset_name,
            "source_kind": "etf",
            "method": "direct_etf_history_only",
        }
    return {
        "source": mapping.research_proxy.code,
        "source_name": mapping.research_proxy.name,
        "source_kind": "research_proxy",
        "method": "research_only",
    }


def _feature(
    value: object,
    *,
    source: str,
    source_kind: str,
    as_of: str | None,
    method: str,
    window_sessions: int | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "value": _round(value) if isinstance(value, (int, float)) else value,
        "source": source,
        "source_kind": source_kind,
        "as_of": as_of,
        "method": method,
    }
    if window_sessions is not None:
        payload["window_sessions"] = window_sessions
    return payload


def _benchmark_return_features(
    frame: pd.DataFrame,
    *,
    asset_return_60d: float | None,
    as_of: str,
    benchmark_key: str,
) -> tuple[str, dict[str, object]]:
    meta = DEFAULT_BENCHMARKS[benchmark_key]
    benchmark_return = _return_over_sessions(frame, 60)
    value = asset_return_60d - benchmark_return if asset_return_60d is not None and benchmark_return is not None else None
    return (
        f"relative_return_60d_vs_{benchmark_key}",
        _feature(
            value,
            source=meta["code"],
            source_kind="benchmark_etf",
            as_of=as_of,
            method=f"asset_return_60d_minus_{benchmark_key}_return_60d",
            window_sessions=60,
        ),
    )


def _latest_style_context(style_payload: Mapping[str, object], as_of: str) -> dict[str, object]:
    rows = [row for row in style_payload.get("rows") or [] if isinstance(row, Mapping)]
    eligible = [row for row in rows if str(row.get("date") or "") <= as_of]
    return dict(eligible[-1]) if eligible else {}


def _theme_for_proxy(style_row: Mapping[str, object], proxy_code: str | None) -> Mapping[str, object]:
    if not proxy_code:
        return {}
    for item in style_row.get("top_themes") or []:
        if isinstance(item, Mapping) and str(item.get("code") or "") == proxy_code:
            return item
    return {}


def _context_reference(context_payloads: Mapping[str, Mapping[str, object]], as_of: str) -> dict[str, object]:
    risk = _as_mapping(context_payloads.get("risk_gradient"))
    protection = _as_mapping(context_payloads.get("protection_score"))
    two_axis = _as_mapping(context_payloads.get("two_axis_context"))
    attribution = _as_mapping(context_payloads.get("context_information_attribution"))
    risk_metadata = _as_mapping(risk.get("metadata"))
    protection_metadata = _as_mapping(protection.get("metadata"))
    two_axis_metadata = _as_mapping(two_axis.get("metadata"))
    attribution_metadata = _as_mapping(attribution.get("metadata"))
    attribution_summary = _as_mapping(attribution.get("summary"))
    return {
        "as_of": as_of,
        "risk_gradient": {
            "engine": risk_metadata.get("engine"),
            "as_of": risk_metadata.get("as_of"),
            "summary_key_read": _as_mapping(risk.get("summary")).get("key_read"),
        },
        "protection_score": {
            "engine": protection_metadata.get("engine"),
            "as_of": protection_metadata.get("as_of"),
            "conclusion": _as_mapping(protection.get("summary")).get("conclusion"),
        },
        "two_axis_context": {
            "engine": two_axis_metadata.get("engine"),
            "as_of": two_axis_metadata.get("as_of"),
            "conclusion": _as_mapping(two_axis.get("summary")).get("conclusion"),
        },
        "retained_layers": attribution_summary.get("retained_layers") or [],
        "source_context_attribution_engine": attribution_metadata.get("engine"),
        "not_used_for_asset_scoring": True,
        "not_used_for_asset_ranking": True,
        "not_used_for_allocation": True,
    }


def _asset_features(
    mapping,
    frame: pd.DataFrame,
    benchmarks: Mapping[str, pd.DataFrame],
    *,
    as_of: str,
    style_row: Mapping[str, object],
) -> dict[str, object]:
    prices = _price_frame(frame, as_of)
    source = _source_payload(mapping)
    source_code = str(source["source"])
    source_kind = str(source["source_kind"])
    source_name = str(source["source_name"])
    asset_return_60d = _return_over_sessions(prices, 60)
    proxy_code = mapping.research_proxy.code if mapping.research_proxy is not None else None
    theme = _theme_for_proxy(style_row, proxy_code)
    style_context = _as_mapping(style_row.get("style_context"))
    relative_items = [
        _benchmark_return_features(_price_frame(frame, as_of), asset_return_60d=asset_return_60d, as_of=as_of, benchmark_key=key)
        for key, frame in benchmarks.items()
    ]
    return {
        "asset_code": mapping.asset_code,
        "asset_name": mapping.asset_name,
        "asset_category": mapping.asset_category,
        "source": {
            **source,
            "as_of": as_of,
            "rows": int(len(prices)),
        },
        "features": {
            "momentum": {
                "return_20d": _feature(_return_over_sessions(prices, 20), source=source_code, source_kind=source_kind, as_of=as_of, method="close_t/close_t_minus_20_minus_1", window_sessions=20),
                "return_60d": _feature(asset_return_60d, source=source_code, source_kind=source_kind, as_of=as_of, method="close_t/close_t_minus_60_minus_1", window_sessions=60),
                "return_120d": _feature(_return_over_sessions(prices, 120), source=source_code, source_kind=source_kind, as_of=as_of, method="close_t/close_t_minus_120_minus_1", window_sessions=120),
            },
            "relative_strength": dict(relative_items),
            "trend": {
                "ma60": _feature(_moving_average(prices, 60), source=source_code, source_kind=source_kind, as_of=as_of, method="simple_moving_average", window_sessions=60),
                "ma120": _feature(_moving_average(prices, 120), source=source_code, source_kind=source_kind, as_of=as_of, method="simple_moving_average", window_sessions=120),
                "ma250": _feature(_moving_average(prices, 250), source=source_code, source_kind=source_kind, as_of=as_of, method="simple_moving_average", window_sessions=250),
                "distance_to_ma60": _feature(_distance_to_ma(prices, 60), source=source_code, source_kind=source_kind, as_of=as_of, method="close_over_ma_minus_1", window_sessions=60),
                "distance_to_ma120": _feature(_distance_to_ma(prices, 120), source=source_code, source_kind=source_kind, as_of=as_of, method="close_over_ma_minus_1", window_sessions=120),
                "distance_to_ma250": _feature(_distance_to_ma(prices, 250), source=source_code, source_kind=source_kind, as_of=as_of, method="close_over_ma_minus_1", window_sessions=250),
            },
            "risk": {
                "volatility_60d_annualized": _feature(_volatility(prices, 60), source=source_code, source_kind=source_kind, as_of=as_of, method="std_daily_return_60d_times_sqrt_252", window_sessions=60),
                "max_drawdown_120d": _feature(_max_drawdown(prices, 120), source=source_code, source_kind=source_kind, as_of=as_of, method="min_close_over_running_high_minus_1", window_sessions=120),
                "price_extension_252d_percentile": _feature(_price_percentile(prices, 252), source=source_code, source_kind=source_kind, as_of=as_of, method="latest_close_percentile_in_252d_window", window_sessions=252),
            },
            "structure": {
                "industry_breadth": _feature(style_context.get("industry_breadth"), source="historical_style_context.json", source_kind="market_context", as_of=str(style_row.get("date") or as_of), method="market_industry_breadth"),
                "theme_persistence": _feature((theme.get("persistence") if theme else style_context.get("theme_persistence")), source="historical_style_context.json", source_kind="market_context", as_of=str(style_row.get("date") or as_of), method="asset_proxy_top_theme_persistence_or_market_theme_persistence"),
                "crowding_score": _feature(style_context.get("crowding_score"), source="historical_style_context.json", source_kind="market_context", as_of=str(style_row.get("date") or as_of), method="market_crowding_score"),
            },
        },
        "constraints": {
            "research_feature_only": True,
            "no_opportunity_score": True,
            "no_ranking": True,
            "no_top_n": True,
            "no_allocation": True,
            "no_trade_signal": True,
        },
    }


def _feature_completeness(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    groups = ["momentum", "relative_strength", "trend", "risk", "structure"]
    completeness: dict[str, object] = {}
    for group in groups:
        available = 0
        total = 0
        for row in rows:
            fields = _as_mapping(_as_mapping(row.get("features")).get(group))
            for field in fields.values():
                if not isinstance(field, Mapping):
                    continue
                total += 1
                if field.get("value") is not None:
                    available += 1
        completeness[group] = {
            "available_fields": available,
            "total_fields": total,
            "coverage": round(available / total, 6) if total else None,
        }
    return completeness


def build_opportunity_context_features(
    as_of: str | int = "20991231",
    *,
    start_date: str | int = DEFAULT_START_DATE,
    registry_path: str | Path = DEFAULT_PROXY_REGISTRY_PATH,
    cache_only: bool = True,
) -> dict[str, object]:
    requested_as_of = normalize_trade_date(as_of)
    start = normalize_trade_date(start_date)
    mappings = [mapping for mapping in read_asset_proxy_registry(registry_path) if mapping.enabled]
    histories = {
        mapping.asset_code: load_research_proxy_history(mapping, start, requested_as_of, cache_only=cache_only)
        for mapping in mappings
    }
    benchmarks = {
        key: read_benchmark_cache(meta["code"], start, requested_as_of)
        for key, meta in DEFAULT_BENCHMARKS.items()
    }
    resolved_as_of = _latest_common_as_of(histories, benchmarks, requested_as_of)
    context_payloads = {name: _read_json(path) for name, path in CONTEXT_INPUTS.items()}
    style_row = _latest_style_context(context_payloads["historical_style_context"], resolved_as_of)
    rows = [
        _asset_features(
            mapping,
            histories[mapping.asset_code],
            {key: _price_frame(frame, resolved_as_of) for key, frame in benchmarks.items()},
            as_of=resolved_as_of,
            style_row=style_row,
        )
        for mapping in mappings
    ]
    source_counts = Counter(str(row["source"]["source_kind"]) for row in rows)
    summary = {
        "asset_count": len(rows),
        "resolved_as_of": resolved_as_of,
        "requested_as_of": requested_as_of,
        "start_date": start,
        "source_counts": dict(source_counts),
        "feature_groups": ["momentum", "relative_strength", "trend", "risk", "structure"],
        "feature_completeness": _feature_completeness(rows),
        "ready_for_scoring": False,
        "ready_for_ranking": False,
        "ready_for_allocation": False,
        "ready_for_trade": False,
        "key_read": "V7.2 creates time-safe opportunity context features only; it does not score, rank, allocate, or trade.",
    }
    return {
        "metadata": {
            "engine": "V7.2 Structural Opportunity Context Feature Audit",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "requested_as_of": requested_as_of,
            "as_of": resolved_as_of,
            "input_files": {name: _project_path(Path(path)) for name, path in CONTEXT_INPUTS.items()},
            "registry": _project_path(Path(registry_path)),
            "purpose": "Build asset opportunity context features only; no score, ranking, allocation, or trade signal.",
        },
        "summary": summary,
        "environment_context": _context_reference(context_payloads, resolved_as_of),
        "assets": rows,
        "time_safety": {
            "requested_as_of": requested_as_of,
            "resolved_common_as_of": resolved_as_of,
            "resolved_lte_requested": resolved_as_of <= requested_as_of,
            "uses_only_history_lte_as_of": True,
            "future_labels_used": False,
            "research_proxy_not_treated_as_tradable": True,
            "v6_context_reference_not_used_for_asset_ranking": True,
            "v6_context_metadata_only": True,
            "v6_context_values_not_joined_to_asset_features": True,
        },
        "data_quality": {
            "cache_only": cache_only,
            "asset_count": len(rows),
            "benchmark_codes": {key: meta["code"] for key, meta in DEFAULT_BENCHMARKS.items()},
            "style_context_as_of": style_row.get("date"),
            "no_scoring": True,
            "no_ranking": True,
            "no_top_n": True,
            "no_allocation": True,
            "no_backtest": True,
            "no_parameter_optimization": True,
        },
        "constraints": {
            "research_feature_only": True,
            "does_not_create_opportunity_score": True,
            "does_not_rank_assets": True,
            "does_not_select_top_assets": True,
            "does_not_generate_position": True,
            "no_percentage_exposure": True,
            "no_etf_weight": True,
            "no_portfolio_weight": True,
            "no_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
        },
    }


def write_opportunity_context_features(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
