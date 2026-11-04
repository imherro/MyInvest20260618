from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from config import DATA_DIR
from macro.indicator_registry import get_all_indicators
from macro.macro_loader import DEFAULT_MACRO_DATA_DIR, load_macro_indicators
from macro.macro_score_engine import (
    COMPONENT_INDICATORS,
    COMPONENT_WEIGHTS,
    aggregate_macro_score,
    component_score,
    score_indicator,
)
from macro.macro_state_classifier import classify_macro_state
from macro.release_calendar import filter_available_records
from macro.schema import MacroIndicatorRecord, normalize_date


DEFAULT_OUTPUT_PATH = DATA_DIR / "macro_context_history.json"

RAW_CONTEXT_INDICATORS = (
    "PE_percentile",
    "PB_percentile",
    "ERP",
    "M1_growth",
    "M2_growth",
    "M1_M2_spread",
    "social_financing_growth",
    "SHIBOR",
    "CN10Y",
    "US10Y",
    "USD_CNH_offshore",
    "PMI",
    "CPI",
    "PPI",
)

SCORING_INDICATORS = tuple(
    dict.fromkeys(
        [
            *get_all_indicators(),
            *(indicator for indicators in COMPONENT_INDICATORS.values() for indicator in indicators),
        ]
    )
)

CONTEXT_FIELDS = (
    "macro_score",
    "macro_confidence",
    "macro_state",
    "valuation_score",
    "credit_score",
    "economy_score",
    "external_score",
    *RAW_CONTEXT_INDICATORS,
)


def _read_json(path: Path) -> object:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _date_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text if len(text) == 8 and text.isdigit() else None


def _share(count: int, total: int) -> float:
    return round(count / total, 6) if total else 0.0


def _distribution(values: Iterable[object]) -> dict[str, dict[str, object]]:
    counter = Counter(str(value or "unknown") for value in values)
    total = sum(counter.values())
    return {
        key: {"count": count, "share": _share(count, total)}
        for key, count in sorted(counter.items())
    }


def _load_exposure_signal_dates(data_dir: Path) -> list[str]:
    exposure = _read_json(data_dir / "exposure_simulation.json")
    rows = exposure.get("historical_replay") if isinstance(exposure, Mapping) else None
    if not isinstance(rows, list):
        raise RuntimeError("exposure_simulation.json is missing historical_replay.")
    dates = sorted({_date_text(row.get("date")) for row in rows if isinstance(row, Mapping)})
    return [date for date in dates if date]


def _latest_available_record(
    records: Sequence[MacroIndicatorRecord],
    decision_date: str,
) -> MacroIndicatorRecord | None:
    available = filter_available_records(list(records), decision_date)
    if not available:
        return None
    return sorted(available, key=lambda item: (item.observation_date, item.release_date, item.effective_date))[-1]


def _confidence(aggregate: Mapping[str, object], components: Mapping[str, Mapping[str, object]]) -> float | None:
    macro_score = aggregate.get("macro_score")
    if macro_score is None:
        return None
    used_indicators = {
        indicator
        for payload in components.values()
        for indicator in payload.get("used_indicators", [])
    }
    configured_indicators = {
        indicator
        for indicators in COMPONENT_INDICATORS.values()
        for indicator in indicators
    }
    coverage = len(used_indicators) / len(configured_indicators) if configured_indicators else 0.0
    available_component_weight = float(aggregate.get("available_component_weight") or 0.0)
    configured_component_weight = float(aggregate.get("configured_component_weight") or 1.0)
    component_coverage = available_component_weight / configured_component_weight if configured_component_weight else 0.0
    consistency = float(aggregate.get("consistency") or 0.0)
    return round(max(0.0, min(1.0, 0.45 * coverage + 0.35 * component_coverage + 0.20 * consistency)), 4)


def _trace_from_record(record: MacroIndicatorRecord | None, *, source: str, reason: str | None = None) -> dict[str, object]:
    if record is None:
        return {
            "available": False,
            "value": None,
            "observation_date": None,
            "release_date": None,
            "effective_date": None,
            "source": source,
            "quality_status": "missing",
            "reason": reason or "no_time_safe_record",
        }
    return {
        "available": record.value is not None,
        "value": record.value,
        "observation_date": record.observation_date,
        "release_date": record.release_date,
        "effective_date": record.effective_date,
        "source": record.source,
        "quality_status": record.quality_status,
        "reason": None if record.value is not None else "record_value_missing",
    }


def _score_trace(
    *,
    value: object,
    source: str,
    used_indicators: Sequence[str],
    latest_release_date: str | None,
    latest_effective_date: str | None,
    reason: str | None = None,
) -> dict[str, object]:
    return {
        "available": value is not None,
        "value": value,
        "observation_date": None,
        "release_date": latest_release_date,
        "effective_date": latest_effective_date,
        "source": source,
        "quality_status": "derived",
        "used_indicators": list(used_indicators),
        "reason": reason,
    }


def _latest_dates(records: Iterable[MacroIndicatorRecord]) -> tuple[str | None, str | None]:
    items = list(records)
    release_dates = [record.release_date for record in items if record.release_date]
    effective_dates = [record.effective_date for record in items if record.effective_date]
    return (max(release_dates) if release_dates else None, max(effective_dates) if effective_dates else None)


def _derived_m1_m2_trace(
    records: Mapping[str, MacroIndicatorRecord | None],
) -> tuple[float | None, dict[str, object]]:
    m1 = records.get("M1_growth")
    m2 = records.get("M2_growth")
    if m1 is None or m2 is None or m1.value is None or m2.value is None:
        return None, {
            "available": False,
            "value": None,
            "observation_date": None,
            "release_date": None,
            "effective_date": None,
            "source": "derived:M1_growth-M2_growth",
            "quality_status": "missing",
            "used_indicators": ["M1_growth", "M2_growth"],
            "reason": "derived_inputs_missing",
        }
    release = max(m1.release_date, m2.release_date)
    effective = max(m1.effective_date, m2.effective_date)
    observation = max(m1.observation_date, m2.observation_date)
    value = round(float(m1.value) - float(m2.value), 4)
    return value, {
        "available": True,
        "value": value,
        "observation_date": observation,
        "release_date": release,
        "effective_date": effective,
        "source": "derived:M1_growth-M2_growth",
        "quality_status": "derived",
        "used_indicators": ["M1_growth", "M2_growth"],
        "reason": None,
    }


def _context_for_date(
    decision_date: str,
    records_by_indicator: Mapping[str, Sequence[MacroIndicatorRecord]],
) -> dict[str, object]:
    latest_records = {
        indicator: _latest_available_record(records_by_indicator.get(indicator, []), decision_date)
        for indicator in SCORING_INDICATORS
    }
    indicator_scores = {
        indicator: score_indicator(indicator, latest_records.get(indicator))
        for indicator in SCORING_INDICATORS
    }
    components = {
        component: component_score(indicator_scores, indicators)
        for component, indicators in COMPONENT_INDICATORS.items()
    }
    aggregate = aggregate_macro_score(components)
    macro_score = aggregate.get("macro_score")
    macro_confidence = _confidence(aggregate, components)
    macro_state = classify_macro_state(None if macro_score is None else float(macro_score), components)

    used_records = [
        latest_records[indicator]
        for payload in components.values()
        for indicator in payload.get("used_indicators", [])
        if latest_records.get(indicator) is not None
    ]
    latest_release, latest_effective = _latest_dates(record for record in used_records if record is not None)

    macro_context: dict[str, object] = {
        "macro_score": None if macro_score is None else round(float(macro_score), 4),
        "macro_confidence": macro_confidence,
        "macro_state": macro_state,
    }
    source_trace: dict[str, dict[str, object]] = {
        "macro_score": _score_trace(
            value=macro_context["macro_score"],
            source="macro_score_engine.aggregate_macro_score",
            used_indicators=[
                indicator
                for payload in components.values()
                for indicator in payload.get("used_indicators", [])
            ],
            latest_release_date=latest_release,
            latest_effective_date=latest_effective,
            reason=None if macro_context["macro_score"] is not None else "no_scored_macro_components",
        ),
        "macro_confidence": _score_trace(
            value=macro_context["macro_confidence"],
            source="historical_macro_context.confidence",
            used_indicators=[
                indicator
                for payload in components.values()
                for indicator in payload.get("used_indicators", [])
            ],
            latest_release_date=latest_release,
            latest_effective_date=latest_effective,
            reason=None if macro_context["macro_confidence"] is not None else "no_scored_macro_components",
        ),
        "macro_state": _score_trace(
            value=macro_state,
            source="macro_state_classifier.classify_macro_state",
            used_indicators=[
                indicator
                for payload in components.values()
                for indicator in payload.get("used_indicators", [])
            ],
            latest_release_date=latest_release,
            latest_effective_date=latest_effective,
            reason=None if macro_score is not None else "no_scored_macro_components",
        ),
    }

    for component in COMPONENT_WEIGHTS:
        payload = components.get(component, {})
        score = payload.get("score")
        field = f"{component}_score"
        used = [str(indicator) for indicator in payload.get("used_indicators", [])]
        used_component_records = [latest_records.get(indicator) for indicator in used]
        release, effective = _latest_dates(record for record in used_component_records if record is not None)
        macro_context[field] = None if score is None else round(float(score), 4)
        source_trace[field] = _score_trace(
            value=macro_context[field],
            source=f"macro_score_engine.component_score.{component}",
            used_indicators=used,
            latest_release_date=release,
            latest_effective_date=effective,
            reason=None if score is not None else "component_indicators_missing",
        )

    for indicator in RAW_CONTEXT_INDICATORS:
        if indicator == "M1_M2_spread":
            value, trace = _derived_m1_m2_trace(latest_records)
        else:
            record = latest_records.get(indicator)
            value = None if record is None else record.value
            trace = _trace_from_record(record, source=f"data/macro/{indicator}.json")
        macro_context[indicator] = value
        source_trace[indicator] = trace

    missing_fields = [field for field in CONTEXT_FIELDS if macro_context.get(field) is None]
    return {
        "date": decision_date,
        "macro_context": macro_context,
        "component_scores": {
            component: {
                "score": None if payload.get("score") is None else round(float(payload["score"]), 4),
                "available_weight": payload.get("available_weight"),
                "used_indicators": payload.get("used_indicators"),
                "missing_indicators": payload.get("missing_indicators"),
            }
            for component, payload in components.items()
        },
        "indicator_scores": {
            indicator: score.to_dict()
            for indicator, score in indicator_scores.items()
        },
        "source_trace": source_trace,
        "data_quality": {
            "release_date_lte_signal_date": all(
                trace.get("release_date") is None or str(trace.get("release_date")) <= decision_date
                for trace in source_trace.values()
            ),
            "effective_date_lte_signal_date": all(
                trace.get("effective_date") is None or str(trace.get("effective_date")) <= decision_date
                for trace in source_trace.values()
            ),
            "available_fields": [field for field in CONTEXT_FIELDS if macro_context.get(field) is not None],
            "missing_fields": missing_fields,
            "null_means_unavailable_not_zero": True,
        },
    }


def _field_coverage(rows: Sequence[Mapping[str, object]]) -> dict[str, dict[str, object]]:
    total = len(rows)
    coverage = {}
    for field in CONTEXT_FIELDS:
        count = sum(
            1
            for row in rows
            if isinstance(row.get("macro_context"), Mapping)
            and (row.get("macro_context") or {}).get(field) is not None
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
        decision_date = str(row.get("date") or "")
        trace_map = row.get("source_trace") if isinstance(row.get("source_trace"), Mapping) else {}
        for field, trace in trace_map.items():
            if not isinstance(trace, Mapping):
                continue
            for date_key in ("release_date", "effective_date"):
                value = trace.get(date_key)
                if value is None:
                    continue
                checked += 1
                if str(value) > decision_date:
                    violations.append({"date": decision_date, "field": field, date_key: value})
    return {
        "release_and_effective_lte_signal_date": not violations,
        "checked_values": checked,
        "violation_count": len(violations),
        "violation_examples": violations[:10],
        "no_future_fill": True,
    }


def build_macro_context_history(
    data_dir: str | Path = DATA_DIR,
    *,
    macro_data_dir: str | Path = DEFAULT_MACRO_DATA_DIR,
    start_date: str | int = "20140101",
) -> dict[str, object]:
    root = Path(data_dir)
    dates = _load_exposure_signal_dates(root)
    if not dates:
        raise RuntimeError("No exposure signal dates available.")
    start = normalize_date(start_date)
    end = max(dates)
    records_by_indicator = load_macro_indicators(get_all_indicators(), start, end, data_dir=macro_data_dir)
    rows = [_context_for_date(date, records_by_indicator) for date in dates]
    coverage = _field_coverage(rows)
    time_safety = _time_safety(rows)
    summary = {
        "row_count": len(rows),
        "as_of": end,
        "field_coverage": coverage,
        "macro_score_coverage": coverage["macro_score"],
        "valuation_coverage": {
            field: coverage[field]
            for field in ("PE_percentile", "PB_percentile", "ERP", "valuation_score")
        },
        "macro_state_distribution": _distribution(
            (row.get("macro_context") or {}).get("macro_state")
            for row in rows
            if isinstance(row.get("macro_context"), Mapping)
        ),
        "time_safety": time_safety,
        "key_read": (
            "Historical macro context is available for exposure replay using release/effective-date safety; "
            "valuation fields remain missing because no local PE/PB/ERP history is present."
        ),
    }
    return {
        "metadata": {
            "engine": "V5.7 Historical Macro Context Enrichment",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of": end,
            "source": "local data/macro cache",
            "purpose": "Attach release-date-safe macro numeric context to exposure replay dates without changing allocation rules.",
        },
        "summary": summary,
        "rows": rows,
        "data_quality": {
            "release_date_lte_signal_date": time_safety["release_and_effective_lte_signal_date"],
            "effective_date_lte_signal_date": time_safety["release_and_effective_lte_signal_date"],
            "no_future_fill": True,
            "missing_values_are_null": True,
            "never_fill_missing_with_zero": True,
            "valuation_history_available": False,
            "loaded_indicators": sorted(records_by_indicator),
        },
        "constraints": {
            "audit_only": True,
            "macro_context_only": True,
            "does_not_modify_exposure_mapper": True,
            "does_not_modify_v4_or_v5_state": True,
            "does_not_add_rules": True,
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


def write_macro_context_history(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
