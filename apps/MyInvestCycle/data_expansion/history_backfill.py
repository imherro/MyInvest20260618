from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from config import BASE_DIR, DATA_DIR
from core.benchmark_loader import load_benchmark_daily
from core.data_loader import get_index_daily, normalize_trade_date
from core.liquidity import get_moneyflow_hsgt
from data_expansion.coverage_planner import (
    ETF_PROXY_REQUIRED,
    MACRO_REQUIRED,
    MACRO_WARMUP_START,
    TARGET_END,
    TARGET_START,
)
from industry_structure.industry_loader import load_industry_panel
from macro.macro_cache_writer import write_macro_records
from macro.tushare_macro_adapter import fetch_macro_indicator_from_tushare


def _display_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(BASE_DIR).as_posix()
    except ValueError:
        return resolved.as_posix()


def backfill_macro_history(
    *,
    start_date: str = MACRO_WARMUP_START,
    end_date: str = TARGET_END,
    indicators: Iterable[str] = MACRO_REQUIRED,
) -> dict[str, object]:
    results = []
    output_files: dict[str, str] = {}
    for indicator in indicators:
        result = fetch_macro_indicator_from_tushare(indicator, start_date, end_date)
        results.append(result.to_dict())
        if result.records:
            output = write_macro_records(indicator, result.records, data_dir=DATA_DIR / "macro", merge=True)
            output_files[indicator] = _display_path(output)
    return {
        "target": {"start": start_date, "end": end_date},
        "results": results,
        "output_files": output_files,
    }


def backfill_industry_history(
    *,
    start_date: str = TARGET_START,
    end_date: str = TARGET_END,
) -> dict[str, object]:
    assets, frames, status = load_industry_panel(
        start_date,
        end_date,
        cache_only=False,
        refresh_prices=False,
    )
    ranges = {}
    for code, frame in frames.items():
        dates = frame["trade_date"].astype(str).str.replace(r"\.0$", "", regex=True)
        ranges[code] = {
            "rows": int(len(frame)),
            "start": str(dates.min()) if not dates.empty else None,
            "end": str(dates.max()) if not dates.empty else None,
        }
    return {
        "target": {"start": start_date, "end": end_date},
        "asset_count": len(assets),
        "available_count": len(frames),
        "status": status,
        "ranges": ranges,
    }


def backfill_market_structure_history(
    *,
    start_date: str = TARGET_START,
    end_date: str = TARGET_END,
    index_codes: tuple[str, ...] = ("000001.SH", "000300.SH", "000905.SH"),
) -> dict[str, object]:
    ranges = {}
    errors = {}
    for code in index_codes:
        try:
            frame = get_index_daily(code, start_date, end_date)
        except Exception as exc:
            errors[code] = str(exc)
            continue
        dates = frame["trade_date"].astype(str).str.replace(r"\.0$", "", regex=True)
        ranges[code] = {
            "rows": int(len(frame)),
            "start": str(dates.min()) if not dates.empty else None,
            "end": str(dates.max()) if not dates.empty else None,
        }
    hsgt_ranges = []
    for year in range(int(start_date[:4]), int(end_date[:4]) + 1):
        chunk_start = f"{year}0101"
        chunk_end = end_date if year == int(end_date[:4]) else f"{year}1231"
        try:
            frame = get_moneyflow_hsgt(chunk_start, chunk_end)
        except Exception as exc:
            errors[f"moneyflow_hsgt_{year}"] = str(exc)
            continue
        dates = frame["trade_date"].astype(str).str.replace(r"\.0$", "", regex=True)
        hsgt_ranges.append(
            {
                "year": year,
                "rows": int(len(frame)),
                "start": str(dates.min()) if not dates.empty else None,
                "end": str(dates.max()) if not dates.empty else None,
            }
        )
    return {
        "target": {"start": start_date, "end": end_date},
        "index_ranges": ranges,
        "hsgt_yearly_ranges": hsgt_ranges,
        "errors": errors,
        "market_daily_backfill": "use scripts/full_history_backfill.py for missing daily breadth rows; coverage is audited by expansion_audit",
    }


def backfill_etf_proxy_history(
    *,
    start_date: str = TARGET_START,
    end_date: str = TARGET_END,
    codes: Iterable[str] = ETF_PROXY_REQUIRED,
) -> dict[str, object]:
    ranges = {}
    errors = {}
    for code in codes:
        try:
            frame = load_benchmark_daily(code, start_date, end_date, cache_only=False, refresh=False)
        except Exception as exc:
            errors[code] = str(exc)
            continue
        dates = frame["trade_date"].astype(str).str.replace(r"\.0$", "", regex=True)
        ranges[code] = {
            "rows": int(len(frame)),
            "start": str(dates.min()) if not dates.empty else None,
            "end": str(dates.max()) if not dates.empty else None,
        }
    return {
        "target": {"start": start_date, "end": end_date},
        "ranges": ranges,
        "errors": errors,
    }


def run_history_backfill(
    *,
    start_date: str = TARGET_START,
    end_date: str = TARGET_END,
    macro_warmup_start: str = MACRO_WARMUP_START,
) -> dict[str, object]:
    start = normalize_trade_date(start_date)
    end = normalize_trade_date(end_date)
    warmup = normalize_trade_date(macro_warmup_start)
    return {
        "engine": "V2.6.2 Historical Data Foundation Expansion Backfill",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "target": {"start": start, "end": end, "macro_warmup_start": warmup},
        "macro": backfill_macro_history(start_date=warmup, end_date=end),
        "industry": backfill_industry_history(start_date=start, end_date=end),
        "market_structure": backfill_market_structure_history(start_date=start, end_date=end),
        "etf_proxy": backfill_etf_proxy_history(start_date=start, end_date=end),
        "constraints": {
            "data_expansion_only": True,
            "no_strategy_rule_change": True,
            "no_threshold_tuning": True,
            "no_allocation_change": True,
            "no_new_alpha_factor": True,
            "no_manual_label_fill": True,
        },
    }
