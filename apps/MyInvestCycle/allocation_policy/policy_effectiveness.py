from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import pandas as pd

from config import DATA_DIR, DEFAULT_INDEX_CODE
from core.data_loader import get_index_daily
from allocation_policy.policy_counterfactual import (
    PRIMARY_HORIZON,
    SHORT_HORIZON,
    future_environment_flags,
    future_environment_label,
    policy_alignment,
    policy_contradictions,
    realized_volatility,
)
from allocation_policy.policy_historical_validation import DEFAULT_PERIODS


DEFAULT_OUTPUT_PATH = DATA_DIR / "policy_effectiveness.json"


def _read_json(path: Path) -> object:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _section(payload: Mapping[str, object], name: str) -> Mapping[str, object]:
    value = payload.get(name)
    return value if isinstance(value, Mapping) else {}


def _round(value: object, digits: int = 6) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _share(count: int, total: int) -> float:
    return round(count / total, 6) if total else 0.0


def _distribution(values: Iterable[object]) -> dict[str, dict[str, object]]:
    counter = Counter(str(value or "unknown") for value in values)
    total = sum(counter.values())
    return {
        key: {"count": count, "share": _share(count, total)}
        for key, count in sorted(counter.items())
    }


def _structural_state_by_date(v2_backtest: Mapping[str, object]) -> dict[str, str]:
    signals = _section(v2_backtest, "signals").get("v2_structural_refined") or []
    result = {}
    for row in signals:
        if not isinstance(row, Mapping):
            continue
        date_text = str(row.get("date") or row.get("as_of") or "")
        if date_text:
            result[date_text] = str(row.get("structural_state") or row.get("allocation_structural_state") or "unknown")
    return result


def _load_index_frame(data_dir: Path, start_date: str, end_date: str) -> tuple[pd.DataFrame, dict[str, object]]:
    quality = {
        "market_proxy": DEFAULT_INDEX_CODE,
        "source": "tushare_index_daily_cache_or_fetch",
        "fallback_used": False,
    }
    try:
        frame = get_index_daily(
            DEFAULT_INDEX_CODE,
            start_date,
            end_date,
            cache_dir=data_dir / "cache",
        )
        frame = frame[["trade_date", "close"]].copy()
        frame["trade_date"] = frame["trade_date"].astype(str)
        frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
        frame = frame.dropna(subset=["trade_date", "close"]).sort_values("trade_date").reset_index(drop=True)
        if not frame.empty:
            quality["start_date"] = str(frame["trade_date"].iloc[0])
            quality["end_date"] = str(frame["trade_date"].iloc[-1])
            quality["observations"] = int(len(frame))
            return frame, quality
    except Exception as exc:  # pragma: no cover - exercised only when local data source fails
        quality["fallback_reason"] = str(exc)

    v2 = _read_json(data_dir / "v2_full_cycle_backtest.json")
    equity_rows = v2.get("equity_curve") if isinstance(v2, Mapping) else []
    if not isinstance(equity_rows, Sequence):
        equity_rows = []
    fallback = pd.DataFrame(equity_rows)
    if not fallback.empty and {"date", "buy_hold_equal_equity"}.issubset(fallback.columns):
        frame = fallback[["date", "buy_hold_equal_equity"]].copy()
        frame = frame.rename(columns={"date": "trade_date", "buy_hold_equal_equity": "close"})
        frame["trade_date"] = frame["trade_date"].astype(str)
        frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
        frame = frame.dropna(subset=["trade_date", "close"]).sort_values("trade_date").reset_index(drop=True)
        quality.update(
            {
                "market_proxy": "v2_buy_hold_equal_equity",
                "source": "v2_full_cycle_backtest_equity_curve_fallback",
                "fallback_used": True,
                "start_date": str(frame["trade_date"].iloc[0]) if not frame.empty else None,
                "end_date": str(frame["trade_date"].iloc[-1]) if not frame.empty else None,
                "observations": int(len(frame)),
            }
        )
        return frame, quality
    raise RuntimeError("No market proxy data available for policy effectiveness validation.")


def _future_metrics(frame: pd.DataFrame, signal_date: str) -> dict[str, object]:
    if frame.empty:
        return {"future_window_complete": False, "reason": "empty_market_frame"}
    dates = frame["trade_date"].astype(str).tolist()
    close = frame["close"].astype(float).tolist()
    start_pos = None
    for idx, date_text in enumerate(dates):
        if date_text >= signal_date:
            start_pos = idx
            break
    if start_pos is None or start_pos + 1 >= len(close):
        return {"future_window_complete": False, "reason": "signal_after_market_data", "signal_date": signal_date}

    start_close = close[start_pos]
    metrics: dict[str, object] = {
        "signal_date": signal_date,
        "market_start_date": dates[start_pos],
        "market_start_close": round(start_close, 4),
        "future_available_days": int(len(close) - start_pos - 1),
    }
    returns_for_vol: list[float] = []
    last_close = start_close
    for horizon in (SHORT_HORIZON, PRIMARY_HORIZON):
        end_pos = min(start_pos + horizon, len(close) - 1)
        window = close[start_pos + 1 : end_pos + 1]
        if not window:
            metrics[f"horizon_{horizon}d_complete"] = False
            metrics[f"forward_return_{horizon}d"] = None
            metrics[f"max_drawdown_{horizon}d"] = None
            metrics[f"max_runup_{horizon}d"] = None
            continue
        metrics[f"horizon_{horizon}d_complete"] = (start_pos + horizon) < len(close)
        metrics[f"forward_return_{horizon}d"] = round(window[-1] / start_close - 1.0, 6)
        metrics[f"max_drawdown_{horizon}d"] = round(min(value / start_close - 1.0 for value in window), 6)
        metrics[f"max_runup_{horizon}d"] = round(max(value / start_close - 1.0 for value in window), 6)
        metrics[f"future_end_date_{horizon}d"] = dates[end_pos]
        if horizon == SHORT_HORIZON:
            for value in window:
                returns_for_vol.append(value / last_close - 1.0 if last_close else 0.0)
                last_close = value
    metrics["realized_volatility_60d"] = realized_volatility(returns_for_vol)
    metrics["future_window_complete"] = bool(metrics.get("horizon_60d_complete") and metrics.get("horizon_120d_complete"))
    return metrics


def _annotate_rows(
    policy_rows: Sequence[Mapping[str, object]],
    opportunity_rows: Sequence[Mapping[str, object]],
    structural_by_date: Mapping[str, str],
    market_frame: pd.DataFrame,
) -> list[dict[str, object]]:
    opportunity_by_date = {str(row.get("date") or ""): row for row in opportunity_rows if isinstance(row, Mapping)}
    rows = []
    for row in policy_rows:
        if not isinstance(row, Mapping):
            continue
        date_text = str(row.get("date") or "")
        opportunity_row = opportunity_by_date.get(date_text, {})
        metrics = _future_metrics(market_frame, date_text)
        flags = future_environment_flags(metrics)
        annotated = {
            "date": date_text,
            "structural_state": structural_by_date.get(date_text)
            or _section(_section(opportunity_row, "metrics"), "structural_state")
            or _section(opportunity_row, "metrics").get("structural_state")
            or "unknown",
            "opportunity_state": row.get("opportunity_state"),
            "risk_state": row.get("risk_state"),
            "combined_state": row.get("combined_state"),
            "policy_mode": row.get("policy_mode"),
            "future_metrics": metrics,
            "future_flags": flags,
            "future_environment": future_environment_label(metrics),
            "future_window_complete": flags.get("future_window_complete"),
            "policy_alignment": policy_alignment(str(row.get("policy_mode") or "unknown"), flags),
            "data_quality": row.get("data_quality") or {},
        }
        annotated["contradictions"] = policy_contradictions(annotated)
        rows.append(annotated)
    return rows


def _mean(values: Sequence[object]) -> float | None:
    clean = [float(value) for value in values if isinstance(value, (int, float))]
    if not clean:
        return None
    return round(sum(clean) / len(clean), 6)


def _group_rows(rows: Sequence[Mapping[str, object]], key: str) -> dict[str, list[Mapping[str, object]]]:
    grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get(key) or "unknown")].append(row)
    return dict(grouped)


def _rate(rows: Sequence[Mapping[str, object]], flag_key: str) -> float:
    total = len(rows)
    if not total:
        return 0.0
    count = sum(1 for row in rows if _section(row, "future_flags").get(flag_key))
    return _share(count, total)


def _model_summary(rows: Sequence[Mapping[str, object]], key: str, label: str) -> dict[str, object]:
    usable = [row for row in rows if row.get("future_window_complete")]
    grouped = _group_rows(usable, key)
    groups = {}
    high_risk_rates = []
    opportunity_rates = []
    return_means = []
    purity_values = []
    for group, items in sorted(grouped.items()):
        future_env = Counter(str(row.get("future_environment") or "unknown") for row in items)
        dominant_env, dominant_count = future_env.most_common(1)[0] if future_env else ("unknown", 0)
        high_risk_rate = _rate(items, "high_risk_event")
        strong_opportunity_rate = _rate(items, "strong_opportunity_event")
        avg_return = _mean([_section(row, "future_metrics").get("forward_return_120d") for row in items])
        avg_drawdown = _mean([_section(row, "future_metrics").get("max_drawdown_120d") for row in items])
        if len(items) >= 3:
            high_risk_rates.append(high_risk_rate)
            opportunity_rates.append(strong_opportunity_rate)
            if avg_return is not None:
                return_means.append(avg_return)
            purity_values.append(dominant_count / len(items))
        groups[group] = {
            "count": len(items),
            "high_risk_event_rate": high_risk_rate,
            "strong_opportunity_rate": strong_opportunity_rate,
            "avg_forward_return_120d": avg_return,
            "avg_max_drawdown_120d": avg_drawdown,
            "dominant_future_environment": dominant_env,
            "dominant_future_environment_share": _share(dominant_count, len(items)),
            "future_environment_distribution": _distribution(row.get("future_environment") for row in items),
        }
    return {
        "label": label,
        "group_key": key,
        "usable_rows": len(usable),
        "group_count": len(groups),
        "groups": groups,
        "separation": {
            "high_risk_rate_spread": round(max(high_risk_rates) - min(high_risk_rates), 6) if high_risk_rates else 0.0,
            "strong_opportunity_rate_spread": round(max(opportunity_rates) - min(opportunity_rates), 6)
            if opportunity_rates
            else 0.0,
            "avg_return_120d_spread": round(max(return_means) - min(return_means), 6) if return_means else 0.0,
            "weighted_label_purity": round(sum(purity_values) / len(purity_values), 6) if purity_values else 0.0,
            "min_group_count_for_spread": 3,
        },
    }


def _contradiction_summary(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    usable = [row for row in rows if row.get("future_window_complete")]
    all_items = []
    for row in usable:
        for item in row.get("contradictions") or []:
            all_items.append({"date": row.get("date"), "policy_mode": row.get("policy_mode"), **item})
    severe = [item for item in all_items if item.get("severity") == "high"]
    return {
        "usable_rows": len(usable),
        "contradiction_count": len(all_items),
        "contradiction_rate": _share(len(all_items), len(usable)),
        "high_severity_count": len(severe),
        "high_severity_rate": _share(len(severe), len(usable)),
        "type_distribution": _distribution(item.get("type") for item in all_items),
        "sample_review_items": all_items[:12],
    }


def _period_summary(period: Mapping[str, object], rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    start = str(period["start"])
    end = str(period["end"])
    period_rows = [row for row in rows if start <= str(row.get("date") or "") <= end and row.get("future_window_complete")]
    contradictions = sum(len(row.get("contradictions") or []) for row in period_rows)
    return {
        "period": period.get("id"),
        "label": period.get("label"),
        "window": {"start": start, "end": end},
        "usable_rows": len(period_rows),
        "policy_mode_distribution": _distribution(row.get("policy_mode") for row in period_rows),
        "future_environment_distribution": _distribution(row.get("future_environment") for row in period_rows),
        "high_risk_event_rate": _rate(period_rows, "high_risk_event"),
        "strong_opportunity_rate": _rate(period_rows, "strong_opportunity_event"),
        "contradiction_count": contradictions,
        "contradiction_rate": _share(contradictions, len(period_rows)),
    }


def _policy_usefulness(
    structural_model: Mapping[str, object],
    opportunity_model: Mapping[str, object],
    policy_model: Mapping[str, object],
    rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    policy_distribution = _distribution(row.get("policy_mode") for row in rows)
    top_mode = None
    top_share = 0.0
    for mode, item in policy_distribution.items():
        share = float(item.get("share") or 0.0)
        if share > top_share:
            top_mode = mode
            top_share = share
    structural_spread = _section(structural_model, "separation").get("high_risk_rate_spread") or 0.0
    opportunity_spread = _section(opportunity_model, "separation").get("high_risk_rate_spread") or 0.0
    policy_spread = _section(policy_model, "separation").get("high_risk_rate_spread") or 0.0
    if top_share >= 0.6:
        read = "policy_mode_too_concentrated_review"
    elif policy_spread > structural_spread and policy_spread >= opportunity_spread:
        read = "policy_mode_adds_environment_separation"
    elif opportunity_spread > structural_spread:
        read = "opportunity_risk_axes_add_separation_but_policy_mapping_compresses"
    else:
        read = "no_clear_incremental_environment_value"
    return {
        "status": read,
        "top_policy_mode": top_mode,
        "top_policy_mode_share": round(top_share, 6),
        "structural_high_risk_rate_spread": structural_spread,
        "opportunity_risk_high_risk_rate_spread": opportunity_spread,
        "policy_high_risk_rate_spread": policy_spread,
        "note": "This evaluates environment separation only; it is not a return optimization or allocation rule.",
    }


def build_policy_effectiveness(
    data_dir: str | Path = DATA_DIR,
    start_date: str = "20150101",
    end_date: str = "20261231",
) -> dict[str, object]:
    root = Path(data_dir)
    policy_payload = _read_json(root / "opportunity_risk_policy.json")
    opportunity_payload = _read_json(root / "opportunity_risk_snapshot.json")
    v2_backtest = _read_json(root / "v2_full_cycle_backtest.json")
    if not isinstance(policy_payload, Mapping) or not policy_payload.get("historical_replay"):
        raise RuntimeError("opportunity_risk_policy.json is missing or incomplete.")
    if not isinstance(opportunity_payload, Mapping):
        opportunity_payload = {}
    if not isinstance(v2_backtest, Mapping):
        v2_backtest = {}

    effective_end_date = min(end_date, datetime.now().strftime("%Y%m%d"))
    market_frame, market_quality = _load_index_frame(root, start_date, effective_end_date)
    policy_rows = [row for row in policy_payload.get("historical_replay") or [] if isinstance(row, Mapping)]
    opportunity_rows = [row for row in opportunity_payload.get("historical_replay") or [] if isinstance(row, Mapping)]
    rows = _annotate_rows(policy_rows, opportunity_rows, _structural_state_by_date(v2_backtest), market_frame)
    usable = [row for row in rows if row.get("future_window_complete")]

    structural_model = _model_summary(rows, "structural_state", "Model A: structural_state")
    opportunity_model = _model_summary(rows, "combined_state", "Model B: opportunity_state + risk_state")
    policy_model = _model_summary(rows, "policy_mode", "Model C: policy_mode")
    contradictions = _contradiction_summary(rows)
    return {
        "metadata": {
            "engine": "V4.5 Policy Effectiveness Audit & Counterfactual Validation",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": _section(policy_payload, "metadata").get("as_of"),
            "source_policy_engine": _section(policy_payload, "metadata").get("engine"),
            "market_proxy": market_quality.get("market_proxy"),
            "primary_horizon_days": PRIMARY_HORIZON,
            "short_horizon_days": SHORT_HORIZON,
            "purpose": "Validate whether fixed V4.4 policy modes explain future market environments better than older state labels.",
        },
        "summary": {
            "replay_rows": len(rows),
            "usable_rows": len(usable),
            "incomplete_future_rows": len(rows) - len(usable),
            "future_environment_distribution": _distribution(row.get("future_environment") for row in usable),
            "policy_mode_distribution": _distribution(row.get("policy_mode") for row in usable),
            "high_risk_event_rate": _rate(usable, "high_risk_event"),
            "strong_opportunity_rate": _rate(usable, "strong_opportunity_event"),
            "policy_usefulness": _policy_usefulness(structural_model, opportunity_model, policy_model, usable),
            "contradiction_audit": contradictions,
        },
        "model_comparison": {
            "structural_state_model": structural_model,
            "opportunity_risk_model": opportunity_model,
            "policy_mode_model": policy_model,
        },
        "period_validation": [_period_summary(period, rows) for period in DEFAULT_PERIODS],
        "counterfactual_validation": {
            "question": "Does V4.4 policy_mode separate future risk/opportunity environments beyond structural_state?",
            "fixed_policy_mapping": True,
            "review_items": contradictions.get("sample_review_items", []),
            "policy_mode_concentration_review": _policy_usefulness(
                structural_model,
                opportunity_model,
                policy_model,
                usable,
            ).get("status")
            == "policy_mode_too_concentrated_review",
        },
        "validation_rows": rows,
        "data_quality": {
            "market_data": market_quality,
            "future_returns_used_only_for_validation_labels": True,
            "v4_4_policy_mapping_fixed": True,
            "no_policy_threshold_tuning": True,
            "recent_rows_may_have_incomplete_forward_windows": True,
        },
        "constraints": {
            "audit_only": True,
            "no_etf_code": True,
            "no_asset_weight": True,
            "no_portfolio_weight": True,
            "no_position_sizing": True,
            "no_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
            "no_return_optimization": True,
            "does_not_modify_v4_4_policy_mapping": True,
        },
    }


def write_policy_effectiveness(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
