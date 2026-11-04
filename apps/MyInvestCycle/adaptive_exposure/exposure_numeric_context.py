from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from config import DATA_DIR


DEFAULT_OUTPUT_PATH = DATA_DIR / "exposure_numeric_context.json"

NUMERIC_FIELDS = (
    "macro_score",
    "macro_confidence",
    "trend_score",
    "breadth_score",
    "liquidity_score",
    "volatility_score",
    "industry_breadth",
    "theme_persistence",
    "crowding_score",
    "price_extension_proxy",
    "pressure_score",
    "risk_score",
)

NON_MACRO_NUMERIC_FIELDS = tuple(field for field in NUMERIC_FIELDS if not field.startswith("macro_"))


def _read_json(path: Path) -> object:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _share(count: int, total: int) -> float:
    return round(count / total, 6) if total else 0.0


def _to_float(value: object, *, scale: float = 1.0) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number * scale, 4)


def _date_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text if len(text) == 8 and text.isdigit() else None


def _distribution(values: Iterable[object]) -> dict[str, dict[str, object]]:
    counter = Counter(str(value or "unknown") for value in values)
    total = sum(counter.values())
    return {
        key: {"count": count, "share": _share(count, total)}
        for key, count in sorted(counter.items())
    }


def _rows_from_payload(payload: object, key: str) -> list[Mapping[str, object]]:
    if isinstance(payload, Mapping):
        rows = payload.get(key) or payload.get("rows")
    else:
        rows = payload
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, Mapping) and _date_text(row.get("date"))]


def _indexed_rows(rows: Sequence[Mapping[str, object]]) -> list[Mapping[str, object]]:
    return sorted(rows, key=lambda row: str(row.get("date") or ""))


def _pick_latest(rows: Sequence[Mapping[str, object]], signal_date: str) -> Mapping[str, object] | None:
    latest: Mapping[str, object] | None = None
    for row in rows:
        row_date = _date_text(row.get("date"))
        if not row_date:
            continue
        if row_date <= signal_date:
            latest = row
        else:
            break
    return latest


def _source_date(row: Mapping[str, object] | None) -> str | None:
    if not row:
        return None
    quality = row.get("data_quality")
    if isinstance(quality, Mapping):
        context_date = _date_text(quality.get("context_date"))
        if context_date:
            return context_date
    return _date_text(row.get("date"))


def _missing_fields(row: Mapping[str, object] | None) -> set[str]:
    if not row:
        return set()
    quality = row.get("data_quality")
    if not isinstance(quality, Mapping):
        return set()
    fields = quality.get("missing_fields")
    if not isinstance(fields, list):
        return set()
    return {str(field) for field in fields}


def _source_available(row: Mapping[str, object] | None, signal_date: str) -> bool:
    source_date = _source_date(row)
    return bool(source_date and source_date <= signal_date)


def _trace(
    *,
    value: float | None,
    source: str,
    source_date: str | None,
    reason: str | None = None,
) -> dict[str, object]:
    return {
        "available": value is not None,
        "value": value,
        "source": source,
        "source_date": source_date,
        "reason": reason,
    }


def _metric_value(
    row: Mapping[str, object] | None,
    signal_date: str,
    metric: str,
    *,
    source: str,
    missing_aliases: Sequence[str] = (),
    scale: float = 1.0,
) -> tuple[float | None, dict[str, object]]:
    source_date = _source_date(row)
    if not _source_available(row, signal_date):
        return None, _trace(value=None, source=source, source_date=source_date, reason="no_time_safe_source")
    metrics = row.get("metrics") if isinstance(row.get("metrics"), Mapping) else row.get("style_context")
    if not isinstance(metrics, Mapping):
        return None, _trace(value=None, source=source, source_date=source_date, reason="source_missing_metrics")
    aliases = {metric, *missing_aliases}
    if aliases & _missing_fields(row):
        return None, _trace(value=None, source=source, source_date=source_date, reason="marked_missing_by_source")
    value = _to_float(metrics.get(metric), scale=scale)
    if value is None:
        return None, _trace(value=None, source=source, source_date=source_date, reason="value_missing")
    return value, _trace(value=value, source=source, source_date=source_date)


def _feature_value(
    row: Mapping[str, object] | None,
    signal_date: str,
    feature: str,
    *,
    source: str,
    scale: float = 100.0,
) -> tuple[float | None, dict[str, object]]:
    source_date = _source_date(row)
    if not _source_available(row, signal_date):
        return None, _trace(value=None, source=source, source_date=source_date, reason="no_time_safe_source")
    features = row.get("features")
    if not isinstance(features, Mapping):
        return None, _trace(value=None, source=source, source_date=source_date, reason="source_missing_features")
    value = _to_float(features.get(feature), scale=scale)
    if value is None:
        return None, _trace(value=None, source=source, source_date=source_date, reason="value_missing")
    return value, _trace(value=value, source=source, source_date=source_date)


def _style_field_value(
    row: Mapping[str, object] | None,
    signal_date: str,
    field: str,
    *,
    source: str,
    scale: float = 1.0,
) -> tuple[float | None, dict[str, object]]:
    source_date = _source_date(row)
    if not _source_available(row, signal_date):
        return None, _trace(value=None, source=source, source_date=source_date, reason="no_time_safe_source")
    quality = row.get("data_quality") if isinstance(row.get("data_quality"), Mapping) else {}
    style_context = row.get("style_context")
    if not isinstance(style_context, Mapping):
        return None, _trace(value=None, source=source, source_date=source_date, reason="source_missing_style_context")

    reason = None
    if field in {"industry_breadth", "theme_persistence"} and int(quality.get("industry_count") or 0) <= 0:
        reason = "industry_history_missing"
    if field in {"crowding_score", "price_extension"} and int(quality.get("valuation_item_count") or 0) <= 0:
        reason = "valuation_history_missing"
    if field in _missing_fields(row):
        reason = "marked_missing_by_source"
    if reason:
        return None, _trace(value=None, source=source, source_date=source_date, reason=reason)

    value = _to_float(style_context.get(field), scale=scale)
    if value is None:
        return None, _trace(value=None, source=source, source_date=source_date, reason="value_missing")
    return value, _trace(value=value, source=source, source_date=source_date)


def _first_available(*items: tuple[float | None, dict[str, object]]) -> tuple[float | None, dict[str, object]]:
    fallback = items[-1] if items else (None, _trace(value=None, source="none", source_date=None, reason="no_sources"))
    for value, trace in items:
        if value is not None:
            return value, trace
    return fallback


def _risk_score_value(
    row: Mapping[str, object] | None,
    signal_date: str,
) -> tuple[float | None, dict[str, object]]:
    source_date = _source_date(row)
    if not _source_available(row, signal_date):
        return None, _trace(value=None, source="shadow_equity_curve.json/decisions", source_date=source_date, reason="no_time_safe_source")
    value = _to_float(row.get("risk_score"), scale=100.0)
    if value is None:
        return None, _trace(value=None, source="shadow_equity_curve.json/decisions", source_date=source_date, reason="value_missing")
    return value, _trace(value=value, source="shadow_equity_curve.json/decisions", source_date=source_date)


def _macro_context_value(
    row: Mapping[str, object] | None,
    signal_date: str,
    field: str,
) -> tuple[float | None, dict[str, object]]:
    source = "macro_context_history.json/rows"
    if not row:
        return None, _trace(value=None, source=source, source_date=None, reason="macro_context_history_missing")
    row_date = _date_text(row.get("date"))
    macro_context = row.get("macro_context") if isinstance(row.get("macro_context"), Mapping) else {}
    source_trace = row.get("source_trace") if isinstance(row.get("source_trace"), Mapping) else {}
    trace = source_trace.get(field) if isinstance(source_trace.get(field), Mapping) else {}
    release_date = _date_text(trace.get("release_date"))
    effective_date = _date_text(trace.get("effective_date"))
    source_date = effective_date or release_date or row_date
    if not source_date or source_date > signal_date or (row_date and row_date > signal_date):
        return None, _trace(value=None, source=source, source_date=source_date, reason="no_time_safe_macro_context")
    value = _to_float(macro_context.get(field), scale=1.0)
    payload = _trace(
        value=value,
        source=str(trace.get("source") or source),
        source_date=source_date,
        reason=None if value is not None else str(trace.get("reason") or "value_missing"),
    )
    payload["observation_date"] = trace.get("observation_date")
    payload["release_date"] = release_date
    payload["effective_date"] = effective_date
    return value, payload


def _future_label(row: Mapping[str, object]) -> dict[str, object]:
    flags = row.get("future_flags") if isinstance(row.get("future_flags"), Mapping) else {}
    failure = bool(flags.get("high_risk_event") or flags.get("future_drawdown_gt_15"))
    return {
        "future_window_complete": bool(row.get("future_window_complete") or flags.get("future_window_complete")),
        "failure": failure,
        "missed_opportunity": bool(flags.get("strong_opportunity_event")),
        "future_environment": row.get("future_environment"),
    }


def _enrich_row(
    exposure_row: Mapping[str, object],
    *,
    opportunity_rows: Sequence[Mapping[str, object]],
    style_rows: Sequence[Mapping[str, object]],
    structural_rows: Sequence[Mapping[str, object]],
    risk_rows: Sequence[Mapping[str, object]],
    macro_rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    signal_date = _date_text(exposure_row.get("date"))
    if not signal_date:
        raise ValueError("exposure row missing date")

    opportunity = _pick_latest(opportunity_rows, signal_date)
    style = _pick_latest(style_rows, signal_date)
    structural = _pick_latest(structural_rows, signal_date)
    risk = _pick_latest(risk_rows, signal_date)
    macro = _pick_latest(macro_rows, signal_date)

    field_values: dict[str, float | None] = {}
    source_trace: dict[str, dict[str, object]] = {}
    for macro_field in ("macro_score", "macro_confidence"):
        value, trace = _macro_context_value(macro, signal_date, macro_field)
        field_values[macro_field] = value
        source_trace[macro_field] = trace

    metric_specs = {
        "trend_score": ("trend", "trend"),
        "breadth_score": ("breadth", "breadth"),
        "liquidity_score": ("liquidity", "liquidity"),
        "pressure_score": ("pressure", "pressure"),
    }
    for output_field, (metric, missing_alias) in metric_specs.items():
        value, trace = _first_available(
            _metric_value(
                opportunity,
                signal_date,
                metric,
                source="opportunity_risk_snapshot.json/historical_replay",
                missing_aliases=(missing_alias,),
            ),
            _feature_value(
                structural,
                signal_date,
                metric,
                source="structural_hazard_dataset.json/features",
                scale=100.0,
            ),
        )
        field_values[output_field] = value
        source_trace[output_field] = trace

    volatility, volatility_trace = _first_available(
        _style_field_value(
            style,
            signal_date,
            "volatility",
            source="historical_style_context.json/rows",
            scale=100.0,
        ),
        _feature_value(
            structural,
            signal_date,
            "volatility",
            source="structural_hazard_dataset.json/features",
            scale=100.0,
        ),
    )
    field_values["volatility_score"] = volatility
    source_trace["volatility_score"] = volatility_trace

    for output_field, style_field, scale in (
        ("industry_breadth", "industry_breadth", 1.0),
        ("theme_persistence", "theme_persistence", 1.0),
        ("crowding_score", "crowding_score", 1.0),
        ("price_extension_proxy", "price_extension", 1.0),
    ):
        value, trace = _style_field_value(
            style,
            signal_date,
            style_field,
            source="historical_style_context.json/rows",
            scale=scale,
        )
        field_values[output_field] = value
        source_trace[output_field] = trace

    risk_score, risk_trace = _risk_score_value(risk, signal_date)
    field_values["risk_score"] = risk_score
    source_trace["risk_score"] = risk_trace

    exposure_context = {
        "exposure_level": exposure_row.get("exposure_level"),
        "exposure_band": exposure_row.get("exposure_band"),
        "policy_mode": exposure_row.get("policy_mode"),
        "opportunity_state": exposure_row.get("opportunity_state"),
        "risk_state": exposure_row.get("risk_state"),
        "market_phase": exposure_row.get("market_phase"),
        **field_values,
    }
    missing = [field for field in NUMERIC_FIELDS if field_values.get(field) is None]
    return {
        "date": signal_date,
        "exposure_context": exposure_context,
        "future_label": _future_label(exposure_row),
        "source_trace": source_trace,
        "data_quality": {
            "feature_date_lte_signal_date": all(
                trace.get("source_date") is None or str(trace.get("source_date")) <= signal_date
                for trace in source_trace.values()
            ),
            "available_numeric_fields": [field for field in NUMERIC_FIELDS if field_values.get(field) is not None],
            "missing_numeric_fields": missing,
            "null_means_unavailable_not_zero": True,
        },
    }


def _field_coverage(rows: Sequence[Mapping[str, object]]) -> dict[str, dict[str, object]]:
    total = len(rows)
    coverage = {}
    for field in NUMERIC_FIELDS:
        count = sum(
            1
            for row in rows
            if isinstance(row.get("exposure_context"), Mapping)
            and (row.get("exposure_context") or {}).get(field) is not None
        )
        coverage[field] = {
            "available_count": count,
            "missing_count": total - count,
            "coverage_rate": _share(count, total),
        }
    return coverage


def _time_safety(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    checked = 0
    violations = []
    for row in rows:
        date_text = str(row.get("date") or "")
        trace_map = row.get("source_trace") if isinstance(row.get("source_trace"), Mapping) else {}
        for field, trace in trace_map.items():
            if not isinstance(trace, Mapping):
                continue
            source_date = trace.get("source_date")
            if source_date is None:
                continue
            checked += 1
            if str(source_date) > date_text:
                violations.append({"date": date_text, "field": field, "source_date": source_date})
    return {
        "feature_date_lte_signal_date": not violations,
        "checked_values": checked,
        "violation_count": len(violations),
        "violation_examples": violations[:10],
        "no_future_fill": True,
    }


def build_exposure_numeric_context(data_dir: str | Path = DATA_DIR) -> dict[str, object]:
    root = Path(data_dir)
    exposure = _read_json(root / "exposure_simulation.json")
    if not isinstance(exposure, Mapping) or not exposure.get("historical_replay"):
        raise RuntimeError("exposure_simulation.json is missing or incomplete.")

    exposure_rows = _rows_from_payload(exposure, "historical_replay")
    opportunity_rows = _indexed_rows(_rows_from_payload(_read_json(root / "opportunity_risk_snapshot.json"), "historical_replay"))
    style_rows = _indexed_rows(_rows_from_payload(_read_json(root / "historical_style_context.json"), "rows"))
    structural_rows = _indexed_rows(_rows_from_payload(_read_json(root / "structural_hazard_dataset.json"), ""))
    shadow = _read_json(root / "shadow_equity_curve.json")
    risk_rows = _indexed_rows(_rows_from_payload(shadow.get("decisions") if isinstance(shadow, Mapping) else [], ""))
    macro_rows = _indexed_rows(_rows_from_payload(_read_json(root / "macro_context_history.json"), "rows"))

    rows = [
        _enrich_row(
            row,
            opportunity_rows=opportunity_rows,
            style_rows=style_rows,
            structural_rows=structural_rows,
            risk_rows=risk_rows,
            macro_rows=macro_rows,
        )
        for row in exposure_rows
    ]
    coverage = _field_coverage(rows)
    time_safety = _time_safety(rows)
    fully_populated = sum(
        1
        for row in rows
        if isinstance(row.get("data_quality"), Mapping)
        and not (row.get("data_quality") or {}).get("missing_numeric_fields")
    )
    fully_populated_non_macro = sum(
        1
        for row in rows
        if isinstance(row.get("exposure_context"), Mapping)
        and all((row.get("exposure_context") or {}).get(field) is not None for field in NON_MACRO_NUMERIC_FIELDS)
    )
    missing_macro_history = not any(
        (row.get("exposure_context") or {}).get("macro_score") is not None
        for row in rows
        if isinstance(row.get("exposure_context"), Mapping)
    )
    summary = {
        "row_count": len(rows),
        "as_of": (exposure.get("metadata") or {}).get("as_of"),
        "exposure_level_distribution": _distribution(
            (row.get("exposure_context") or {}).get("exposure_level")
            for row in rows
            if isinstance(row.get("exposure_context"), Mapping)
        ),
        "future_label_distribution": _distribution(
            "failure"
            if (row.get("future_label") or {}).get("failure")
            else "missed_opportunity"
            if (row.get("future_label") or {}).get("missed_opportunity")
            else "neutral"
            for row in rows
            if isinstance(row.get("future_label"), Mapping)
        ),
        "field_coverage": coverage,
        "fully_populated_rows": fully_populated,
        "fully_populated_rate": _share(fully_populated, len(rows)),
        "fully_populated_non_macro_rows": fully_populated_non_macro,
        "fully_populated_non_macro_rate": _share(fully_populated_non_macro, len(rows)),
        "missing_macro_history": missing_macro_history,
        "time_safety": time_safety,
        "key_read": (
            "Numeric context is now attached to the exposure replay without changing rules; "
            + (
                "macro history remains unavailable and is represented as null."
                if missing_macro_history
                else "macro score and confidence are populated from release-date-safe macro context history."
            )
        ),
    }
    return {
        "metadata": {
            "engine": "V5.6 Numeric Context Enrichment for Exposure Replay",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": summary["as_of"],
            "source_engine": (exposure.get("metadata") or {}).get("engine"),
            "purpose": "Attach time-safe numeric context to historical qualitative exposure signals without changing mapper rules.",
        },
        "summary": summary,
        "rows": rows,
        "data_quality": {
            "feature_date_lte_signal_date": time_safety["feature_date_lte_signal_date"],
            "no_future_fill": True,
            "missing_values_are_null": True,
            "never_fill_missing_with_zero": True,
            "source_files": {
                "exposure": "exposure_simulation.json",
                "opportunity_risk": "opportunity_risk_snapshot.json",
                "style_context": "historical_style_context.json",
                "market_structure": "structural_hazard_dataset.json",
                "risk_score": "shadow_equity_curve.json/decisions",
                "macro": "macro_context_history.json if available; otherwise null",
            },
        },
        "constraints": {
            "audit_only": True,
            "does_not_modify_mapper": True,
            "does_not_modify_exposure_levels": True,
            "does_not_add_formal_state": True,
            "no_parameter_optimization": True,
            "no_percentage_exposure": True,
            "no_etf_code": True,
            "no_asset_weight": True,
            "no_portfolio_weight": True,
            "no_trade_signal": True,
            "no_order_generation": True,
            "no_broker_connection": True,
            "no_return_optimization": True,
        },
    }


def write_exposure_numeric_context(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
