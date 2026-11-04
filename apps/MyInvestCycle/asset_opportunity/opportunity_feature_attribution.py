from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import mean
from typing import Mapping

from config import DATA_DIR


DEFAULT_INPUT_PATH = DATA_DIR / "opportunity_feature_validation.json"
DEFAULT_OUTPUT_PATH = DATA_DIR / "opportunity_feature_attribution.json"
REGIME_LABELS = ("PARTICIPATE", "PROTECT_BUT_PARTICIPATE", "WAIT", "AVOID")


def _read_json(path: str | Path) -> dict[str, object]:
    target = Path(path)
    if not target.exists():
        return {}
    payload = json.loads(target.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _as_mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _project_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _mean_ic(source: Mapping[str, object]) -> float | None:
    value = source.get("mean_ic")
    return float(value) if isinstance(value, (int, float)) else None


def _sign(value: float | None, threshold: float = 0.04) -> str:
    if value is None:
        return "none"
    if value >= threshold:
        return "positive"
    if value <= -threshold:
        return "negative"
    return "flat"


def _source_alignment(proxy: Mapping[str, object], etf: Mapping[str, object]) -> str:
    proxy_sign = _sign(_mean_ic(proxy))
    etf_sign = _sign(_mean_ic(etf))
    if proxy_sign == "none" or etf_sign == "none":
        return "insufficient"
    if proxy_sign == "flat" and etf_sign == "flat":
        return "both_flat"
    if proxy_sign == etf_sign:
        return "aligned"
    if proxy_sign == "flat" or etf_sign == "flat":
        return "one_side_only"
    return "conflicting"


def _regime_mean(source: Mapping[str, object], label: str) -> float | None:
    regimes = _as_mapping(source.get("regime_breakdown"))
    item = _as_mapping(regimes.get(label))
    value = item.get("mean_ic")
    return float(value) if isinstance(value, (int, float)) else None


def _regime_sample(source: Mapping[str, object], label: str) -> int:
    regimes = _as_mapping(source.get("regime_breakdown"))
    item = _as_mapping(regimes.get(label))
    value = item.get("sample_count")
    return int(value) if isinstance(value, int) else 0


def _regime_consistency(proxy: Mapping[str, object], etf: Mapping[str, object]) -> dict[str, object]:
    rows = []
    active_signs = []
    for label in REGIME_LABELS:
        proxy_ic = _regime_mean(proxy, label)
        etf_ic = _regime_mean(etf, label)
        proxy_sample = _regime_sample(proxy, label)
        etf_sample = _regime_sample(etf, label)
        proxy_sign = _sign(proxy_ic)
        etf_sign = _sign(etf_ic)
        combined_values = [value for value in (proxy_ic, etf_ic) if isinstance(value, (int, float))]
        combined_ic = round(mean(combined_values), 6) if combined_values else None
        combined_sign = _sign(combined_ic)
        if combined_sign in {"positive", "negative"}:
            active_signs.append(combined_sign)
        rows.append(
            {
                "two_axis_label": label,
                "proxy_sample_count": proxy_sample,
                "etf_sample_count": etf_sample,
                "proxy_mean_ic": proxy_ic,
                "etf_mean_ic": etf_ic,
                "proxy_sign": proxy_sign,
                "etf_sign": etf_sign,
                "combined_mean_ic": combined_ic,
                "combined_sign": combined_sign,
            }
        )
    unique_active = sorted(set(active_signs))
    if not active_signs:
        label = "no_regime_signal"
    elif len(unique_active) == 1 and len(active_signs) >= 2:
        label = "consistent_context_signal"
    elif len(unique_active) == 1:
        label = "single_context_signal"
    else:
        label = "mixed_or_conflicting_context_signal"
    return {
        "status": label,
        "active_context_count": len(active_signs),
        "active_signs": unique_active,
        "regimes": rows,
    }


def _retention(proxy: Mapping[str, object], etf: Mapping[str, object], alignment: str, regime_status: str) -> str:
    proxy_status = str(proxy.get("status") or "insufficient")
    etf_status = str(etf.get("status") or "insufficient")
    supported = {"visible", "weak"}
    if proxy_status == "insufficient" and etf_status == "insufficient":
        return "insufficient"
    if alignment == "aligned" and proxy_status in supported and etf_status in supported and regime_status != "mixed_or_conflicting_context_signal":
        return "research_candidate"
    if proxy_status in supported or etf_status in supported:
        return "watch"
    return "reject_for_now"


def _attribution_row(result: Mapping[str, object]) -> dict[str, object]:
    proxy = _as_mapping(result.get("research_proxy"))
    etf = _as_mapping(result.get("tradable_etf"))
    alignment = _source_alignment(proxy, etf)
    regime = _regime_consistency(proxy, etf)
    return {
        "feature_group": result.get("feature_group"),
        "feature_field": result.get("feature_field"),
        "feature_key": result.get("feature_key"),
        "horizon_sessions": result.get("horizon_sessions"),
        "research_proxy_mean_ic": proxy.get("mean_ic"),
        "research_proxy_status": proxy.get("status"),
        "tradable_etf_mean_ic": etf.get("mean_ic"),
        "tradable_etf_status": etf.get("status"),
        "proxy_etf_alignment": alignment,
        "regime_consistency": regime,
        "retention": _retention(proxy, etf, alignment, str(regime.get("status"))),
        "interpretation": "feature_attribution_only_not_a_score_or_weight",
    }


def build_opportunity_feature_attribution(
    *,
    input_path: str | Path = DEFAULT_INPUT_PATH,
) -> dict[str, object]:
    validation = _read_json(input_path)
    if not validation:
        raise RuntimeError("opportunity_feature_validation.json is missing; run scripts/run_opportunity_feature_validation.py first.")
    validation_metadata = _as_mapping(validation.get("metadata"))
    validation_summary = _as_mapping(validation.get("summary"))
    rows = [_attribution_row(row) for row in validation.get("feature_results") or [] if isinstance(row, Mapping)]
    retention_counts = Counter(str(row.get("retention") or "unknown") for row in rows)
    regime_counts = Counter(str(_as_mapping(row.get("regime_consistency")).get("status") or "unknown") for row in rows)
    return {
        "metadata": {
            "engine": "V7.4 Opportunity Feature Attribution & Stability Audit",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source_engine": validation_metadata.get("engine"),
            "source_file": _project_path(input_path),
            "purpose": "Attribute fixed V7.3 feature validation results and decide research retention only; no score, weights, ranking, allocation, or trade signal.",
        },
        "summary": {
            "source_result_count": validation_summary.get("result_count"),
            "attribution_count": len(rows),
            "retention_counts": dict(sorted(retention_counts.items())),
            "regime_consistency_counts": dict(sorted(regime_counts.items())),
            "ready_for_scoring": False,
            "ready_for_ranking": False,
            "ready_for_allocation": False,
            "ready_for_trade": False,
            "conclusion": "feature_attribution_not_ready_for_opportunity_score",
            "key_read": "V7.4 keeps feature attribution research-only; retention labels are not scores, weights, ranks, or trading instructions.",
        },
        "feature_attribution": rows,
        "time_safety": {
            "uses_fixed_v7_3_validation_only": True,
            "does_not_recompute_features": True,
            "does_not_recompute_forward_returns": True,
            "future_returns_used_only_in_source_validation": True,
            "future_returns_not_used_for_scoring": True,
        },
        "data_quality": {
            "source_result_count_matches_attribution": validation_summary.get("result_count") == len(rows),
            "feature_definitions_fixed": True,
            "no_new_feature_search": True,
            "no_scoring": True,
            "no_feature_weighting": True,
            "no_ranking": True,
            "no_top_n": True,
            "no_allocation": True,
            "no_parameter_optimization": True,
        },
        "constraints": {
            "attribution_only": True,
            "does_not_create_opportunity_score": True,
            "does_not_create_feature_weight": True,
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


def write_opportunity_feature_attribution(
    payload: Mapping[str, object],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
