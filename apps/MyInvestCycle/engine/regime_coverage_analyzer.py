from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import pandas as pd

from core.data_loader import normalize_trade_date
from engine.regime_transition_matrix import REGIMES


def expected_trade_dates(index_df: pd.DataFrame, *, start_date: str, end_date: str) -> list[str]:
    start = normalize_trade_date(start_date)
    end = normalize_trade_date(end_date)
    if start > end:
        raise ValueError("start_date must be earlier than or equal to end_date")
    if index_df.empty:
        return []
    if "trade_date" not in index_df.columns:
        raise KeyError("index_df must contain trade_date")

    dates = index_df["trade_date"].astype(str).str.replace(r"\.0$", "", regex=True)
    return dates[(dates >= start) & (dates <= end)].drop_duplicates().sort_values().tolist()


def market_daily_cache_coverage(
    trade_dates: Iterable[str],
    *,
    cache_dir: Path,
) -> dict[str, object]:
    expected = [normalize_trade_date(date) for date in trade_dates]
    available: list[str] = []
    missing: list[str] = []
    for trade_date in expected:
        path = cache_dir / f"market_daily_{trade_date}.csv"
        if path.exists():
            available.append(trade_date)
        else:
            missing.append(trade_date)

    total = len(expected)
    covered = len(available)
    return {
        "total_days": total,
        "covered_days": covered,
        "missing_days": len(missing),
        "coverage_ratio": round(covered / total, 6) if total else 0.0,
        "available_sample": available[:10],
        "missing_sample": missing[:10],
    }


def regime_distribution(
    regime_items: Iterable[Mapping[str, object]],
    *,
    regimes: Sequence[str] = REGIMES,
) -> dict[str, object]:
    items = list(regime_items)
    total = len(items)
    counts = {regime: 0 for regime in regimes}
    for item in items:
        regime = str(item.get("regime", ""))
        if regime in counts:
            counts[regime] += 1

    distribution = {
        regime: round(count / total, 6) if total else 0.0
        for regime, count in counts.items()
    }
    missing_regimes = [regime for regime, count in counts.items() if count == 0]
    max_share = max(distribution.values()) if distribution else 0.0
    nonzero_shares = [share for share in distribution.values() if share > 0]
    min_nonzero_share = min(nonzero_shares) if nonzero_shares else 0.0

    return {
        "observations": total,
        "regime_counts": counts,
        "regime_distribution": distribution,
        "missing_regimes": missing_regimes,
        "max_share": round(max_share, 6),
        "min_nonzero_share": round(min_nonzero_share, 6),
        "transition_share": distribution.get("transition", 0.0),
    }


def regime_duration_summary(
    regime_items: Iterable[Mapping[str, object]],
    *,
    regimes: Sequence[str] = REGIMES,
) -> dict[str, object]:
    ordered = sorted(
        (
            {
                "trade_date": str(item["trade_date"]),
                "regime": str(item["regime"]),
            }
            for item in regime_items
            if "trade_date" in item and "regime" in item
        ),
        key=lambda item: item["trade_date"],
    )
    streaks = {regime: [] for regime in regimes}
    if not ordered:
        return {
            regime: {"segments": 0, "max_duration": 0, "avg_duration": 0.0}
            for regime in regimes
        }

    current_regime = ordered[0]["regime"]
    current_length = 1
    for item in ordered[1:]:
        regime = item["regime"]
        if regime == current_regime:
            current_length += 1
            continue
        if current_regime in streaks:
            streaks[current_regime].append(current_length)
        current_regime = regime
        current_length = 1
    if current_regime in streaks:
        streaks[current_regime].append(current_length)

    return {
        regime: {
            "segments": len(lengths),
            "max_duration": max(lengths) if lengths else 0,
            "avg_duration": round(sum(lengths) / len(lengths), 4) if lengths else 0.0,
        }
        for regime, lengths in streaks.items()
    }


def build_coverage_audit(
    *,
    expected_dates: Sequence[str],
    cache_coverage: Mapping[str, object],
    regime_items: Sequence[Mapping[str, object]],
    skipped: Sequence[Mapping[str, str]],
    coverage_threshold: float = 0.90,
    regimes: Sequence[str] = REGIMES,
) -> dict[str, object]:
    distribution = regime_distribution(regime_items, regimes=regimes)
    durations = regime_duration_summary(regime_items, regimes=regimes)
    covered_days = int(cache_coverage["covered_days"])
    total_days = int(cache_coverage["total_days"])
    coverage_ratio = float(cache_coverage["coverage_ratio"])
    transition_share = float(distribution["transition_share"])
    missing_regimes = list(distribution["missing_regimes"])

    warnings: list[str] = []
    if coverage_ratio < coverage_threshold:
        warnings.append("coverage_below_threshold")
    if missing_regimes:
        warnings.append("missing_regime_labels")
    if transition_share > 0.50:
        warnings.append("transition_overconcentration")
    if skipped:
        warnings.append("regime_sequence_skipped_dates")

    coverage_status = "pass" if coverage_ratio >= coverage_threshold else "fail"
    label_warnings = {"missing_regime_labels", "transition_overconcentration"}
    label_status = "fail" if any(warning in label_warnings for warning in warnings) else "pass"
    return {
        "total_days": total_days,
        "covered_days": covered_days,
        "missing_days": int(cache_coverage["missing_days"]),
        "coverage_ratio": coverage_ratio,
        "coverage_threshold": coverage_threshold,
        "coverage_status": coverage_status,
        "label_status": label_status,
        "audit_status": "pass" if not warnings else "fail",
        "regime_distribution": distribution["regime_distribution"],
        "regime_counts": distribution["regime_counts"],
        "missing_regimes": missing_regimes,
        "duration_summary": durations,
        "label_imbalance": {
            "max_share": distribution["max_share"],
            "min_nonzero_share": distribution["min_nonzero_share"],
            "transition_share": transition_share,
        },
        "expected_sample": list(expected_dates[:10]),
        "missing_cache_sample": list(cache_coverage["missing_sample"]),
        "skipped_days": len(skipped),
        "skipped_sample": list(skipped[:10]),
        "warnings": warnings,
    }


def save_coverage_audit(audit: Mapping[str, object], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
