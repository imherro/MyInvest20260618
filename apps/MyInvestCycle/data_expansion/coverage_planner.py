from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping

from backtest.full_cycle_validation import build_data_coverage_audit
from config import DATA_DIR
from core.data_loader import normalize_trade_date


TARGET_START = "20150101"
TARGET_END = "20260708"
MACRO_WARMUP_START = "20140101"

MACRO_REQUIRED = (
    "M1_growth",
    "M2_growth",
    "social_financing_growth",
    "PMI",
    "CPI",
    "PPI",
    "SHIBOR",
    "CN10Y",
    "USD_CNH_offshore",
)
ETF_PROXY_REQUIRED = ("510300.SH", "510500.SH", "511880.SH")


@dataclass(frozen=True)
class ExpansionTarget:
    name: str
    target_start: str
    target_end: str
    warmup_start: str | None
    required_items: tuple[str, ...]
    source: str
    output: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


TARGETS = (
    ExpansionTarget(
        name="macro_history",
        target_start=TARGET_START,
        target_end=TARGET_END,
        warmup_start=MACRO_WARMUP_START,
        required_items=MACRO_REQUIRED,
        source="Tushare macro/fx/rate endpoints via macro.tushare_macro_adapter",
        output="data/macro/*.json",
    ),
    ExpansionTarget(
        name="industry_history",
        target_start=TARGET_START,
        target_end=TARGET_END,
        warmup_start=None,
        required_items=("SW2021 L1 industry indexes",),
        source="Tushare index_daily with cached SW2021 L1 universe",
        output="data/cache/index_daily_801xxx_SI.csv",
    ),
    ExpansionTarget(
        name="market_structure_history",
        target_start=TARGET_START,
        target_end=TARGET_END,
        warmup_start=None,
        required_items=("000001.SH", "000300.SH", "000905.SH", "market_daily breadth cache", "HSGT liquidity proxy"),
        source="Tushare index_daily, daily market rows and moneyflow_hsgt cache",
        output="data/cache/index_daily_*.csv and data/cache/market_daily_*.csv",
    ),
    ExpansionTarget(
        name="etf_proxy_history",
        target_start=TARGET_START,
        target_end=TARGET_END,
        warmup_start=None,
        required_items=ETF_PROXY_REQUIRED,
        source="Tushare fund_daily",
        output="data/cache/fund_daily_*.csv",
    ),
)


def read_previous_validation_window(path: str | Path = DATA_DIR / "v2_full_cycle_validation.json") -> dict[str, object]:
    import json

    artifact = Path(path)
    if not artifact.exists():
        return {"available": False}
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    metadata = payload.get("metadata") if isinstance(payload, Mapping) else {}
    coverage = payload.get("coverage_audit") if isinstance(payload, Mapping) else {}
    return {
        "available": True,
        "validation_window": (metadata or {}).get("validation_window"),
        "operational_validation_window": (coverage or {}).get("operational_validation_window"),
        "blocker_count": (coverage or {}).get("blocker_count"),
        "full_cycle_claim": (metadata or {}).get("full_cycle_claim"),
    }


def build_expansion_plan(
    *,
    target_start: str = TARGET_START,
    target_end: str = TARGET_END,
) -> dict[str, object]:
    start = normalize_trade_date(target_start)
    end = normalize_trade_date(target_end)
    coverage_before = read_previous_validation_window()
    current_coverage = build_data_coverage_audit(desired_start=start, desired_end=end)
    return {
        "target": f"{start}-{end}",
        "macro_warmup_start": MACRO_WARMUP_START,
        "available_before": coverage_before,
        "current_coverage": {
            "operational_validation_window": current_coverage.get("operational_validation_window"),
            "blocker_count": current_coverage.get("blocker_count"),
            "can_cover_desired_window": current_coverage.get("can_cover_desired_window"),
        },
        "targets": [target.to_dict() for target in TARGETS],
        "constraints": {
            "data_expansion_only": True,
            "no_strategy_rule_change": True,
            "no_threshold_tuning": True,
            "no_allocation_change": True,
            "no_new_alpha_factor": True,
            "no_manual_label_fill": True,
        },
    }
