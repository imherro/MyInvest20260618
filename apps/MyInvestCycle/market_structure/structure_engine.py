from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

import pandas as pd

from config import BREADTH_HISTORY_SAMPLE_SIZE
from core.breadth import calculate_breadth_metrics, get_market_daily, get_market_history_sample
from core.data_loader import get_index_daily, normalize_trade_date
from core.liquidity import calculate_liquidity_metrics, get_moneyflow_hsgt
from market_structure.structure_classifier import classify_structure, estimate_structure_confidence
from market_structure.structure_explainer import explain_structure
from market_structure.structure_score_engine import INDEX_LABELS, build_structure_metrics, score_index_trend


DEFAULT_INDEX_CODES = ("000001.SH", "000300.SH", "000905.SH")


def _calendar_shift(date_text: str, days: int) -> str:
    return (pd.to_datetime(date_text, format="%Y%m%d") + pd.Timedelta(days=days)).strftime("%Y%m%d")


def _load_index_frames(
    index_codes: tuple[str, ...],
    start_date: str,
    end_date: str,
) -> tuple[dict[str, pd.DataFrame], str]:
    frames: dict[str, pd.DataFrame] = {}
    latest_dates = []
    for code in index_codes:
        frame = get_index_daily(code, start_date, end_date)
        frame = frame[frame["trade_date"] <= end_date].sort_values("trade_date").reset_index(drop=True)
        if frame.empty:
            continue
        frames[code] = frame
        latest_dates.append(str(frame["trade_date"].iloc[-1]))
    if not frames:
        raise ValueError("No index frames available for structure snapshot.")
    resolved_as_of = min(latest_dates)
    aligned = {
        code: frame[frame["trade_date"] <= resolved_as_of].copy()
        for code, frame in frames.items()
    }
    return aligned, resolved_as_of


def _safe_breadth_payload(
    as_of: str,
    *,
    history_sample_size: int,
    cache_only: bool,
) -> tuple[dict[str, object] | None, dict[str, object]]:
    try:
        market_daily = get_market_daily(as_of)
    except Exception as exc:
        if cache_only:
            return None, {"status": "missing", "message": f"market_daily cache unavailable: {exc}"}
        raise

    history = None
    if history_sample_size > 0:
        try:
            history = get_market_history_sample(
                market_daily,
                _calendar_shift(as_of, -370),
                as_of,
                sample_size=history_sample_size,
            )
        except Exception as exc:
            history = None
            history_status = {"status": "partial", "message": f"market history sample unavailable: {exc}"}
        else:
            history_status = {"status": "available", "rows": int(len(history))}
    else:
        history_status = {"status": "skipped", "rows": 0}

    return calculate_breadth_metrics(market_daily, market_history_df=history), {
        "status": "available",
        "market_daily_rows": int(len(market_daily)),
        "history": history_status,
    }


def _safe_liquidity_payload(index_df: pd.DataFrame, as_of: str) -> tuple[dict[str, object] | None, dict[str, object]]:
    try:
        hsgt = get_moneyflow_hsgt(_calendar_shift(as_of, -45), as_of)
    except Exception as exc:
        hsgt = None
        hsgt_status = {"status": "missing", "message": str(exc)}
    else:
        hsgt_status = {"status": "available", "rows": int(len(hsgt))}

    try:
        return calculate_liquidity_metrics(index_df, hsgt_df=hsgt), hsgt_status
    except Exception as exc:
        return None, {"status": "missing", "message": str(exc), "hsgt": hsgt_status}


def build_structure_snapshot(
    as_of: str | int,
    *,
    start_date: str | int = "20150101",
    index_codes: tuple[str, ...] = DEFAULT_INDEX_CODES,
    industry_metrics: Mapping[str, object] | None = None,
    history_sample_size: int = BREADTH_HISTORY_SAMPLE_SIZE,
    cache_only: bool = False,
) -> dict[str, object]:
    requested_as_of = normalize_trade_date(as_of)
    start = normalize_trade_date(start_date)
    index_frames, resolved_as_of = _load_index_frames(index_codes, start, requested_as_of)
    index_metrics = {
        code: {
            "label": INDEX_LABELS.get(code, code),
            **score_index_trend(frame),
        }
        for code, frame in index_frames.items()
    }
    breadth_metrics, breadth_status = _safe_breadth_payload(
        resolved_as_of,
        history_sample_size=history_sample_size,
        cache_only=cache_only,
    )
    liquidity_metrics, liquidity_status = _safe_liquidity_payload(index_frames[index_codes[0]], resolved_as_of)
    metrics = build_structure_metrics(
        index_metrics,
        breadth_metrics=breadth_metrics,
        liquidity_metrics=liquidity_metrics,
        industry_metrics=industry_metrics,
    )
    state = classify_structure(metrics)
    confidence = estimate_structure_confidence(metrics, state)
    return {
        "engine": "V2.3.1 Market Structure Engine Core",
        "requested_as_of": requested_as_of,
        "as_of": resolved_as_of,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "structure_state": state,
        "structure_score": metrics["structure_score"],
        "confidence": confidence,
        "metrics": metrics,
        "index_metrics": index_metrics,
        "data_quality": {
            "index_codes": list(index_frames),
            "breadth": breadth_status,
            "liquidity": liquidity_status,
            "industry_theme_data": "not_available_in_v2_3_1" if industry_metrics is None else "provided",
            "no_future_data": resolved_as_of <= requested_as_of,
        },
        "explanation": explain_structure(state, metrics),
        "constraints": {
            "independent_from_macro_state": True,
            "no_position_sizing": True,
            "no_etf_allocation": True,
            "no_trade_signal": True,
            "no_backtest": True,
        },
    }


def write_structure_snapshot(payload: Mapping[str, object], output_path: str | Path) -> Path:
    import json

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
