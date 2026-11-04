from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class IndicatorDefinition:
    name: str
    category: str
    frequency: str
    source: str
    release_lag_days: int
    importance: str
    fallback_policy: str
    description: str = ""
    adapter: str = "tushare"
    source_detail: str = ""
    value_field: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "frequency": self.frequency,
            "source": self.source,
            "release_lag_days": self.release_lag_days,
            "importance": self.importance,
            "fallback_policy": self.fallback_policy,
            "description": self.description,
            "adapter": self.adapter,
            "source_detail": self.source_detail,
            "value_field": self.value_field,
        }


INDICATOR_DEFINITIONS: dict[str, IndicatorDefinition] = {
    "M1_growth": IndicatorDefinition(
        name="M1_growth",
        category="credit",
        frequency="monthly",
        source="tushare",
        release_lag_days=15,
        importance="high",
        fallback_policy="none",
        description="China M1 money supply year-over-year growth.",
        source_detail="cn_m.m1_yoy",
        value_field="m1_yoy",
    ),
    "M2_growth": IndicatorDefinition(
        name="M2_growth",
        category="credit",
        frequency="monthly",
        source="tushare",
        release_lag_days=15,
        importance="high",
        fallback_policy="none",
        description="China M2 money supply year-over-year growth.",
        source_detail="cn_m.m2_yoy",
        value_field="m2_yoy",
    ),
    "social_financing_growth": IndicatorDefinition(
        name="social_financing_growth",
        category="credit",
        frequency="monthly",
        source="tushare",
        release_lag_days=15,
        importance="high",
        fallback_policy="none",
        description="Year-over-year growth computed from social financing stock.",
        source_detail="sf_month.stk_endval; YoY computed from same month previous year",
        value_field="stk_endval_yoy",
    ),
    "new_loans": IndicatorDefinition(
        name="new_loans",
        category="credit",
        frequency="monthly",
        source="tushare",
        release_lag_days=15,
        importance="medium",
        fallback_policy="missing_until_source_verified",
        description="New RMB loans. Registered for V2 but no verified local adapter yet.",
        adapter="none",
        source_detail="not_verified",
        value_field="",
    ),
    "PMI": IndicatorDefinition(
        name="PMI",
        category="economy",
        frequency="monthly",
        source="tushare",
        release_lag_days=1,
        importance="high",
        fallback_policy="none",
        description="China official manufacturing PMI.",
        source_detail="cn_pmi.PMI010000",
        value_field="PMI010000",
    ),
    "CPI": IndicatorDefinition(
        name="CPI",
        category="economy",
        frequency="monthly",
        source="tushare",
        release_lag_days=10,
        importance="medium",
        fallback_policy="none",
        description="China national CPI year-over-year growth.",
        source_detail="cn_cpi.nt_yoy",
        value_field="nt_yoy",
    ),
    "PPI": IndicatorDefinition(
        name="PPI",
        category="economy",
        frequency="monthly",
        source="tushare",
        release_lag_days=10,
        importance="medium",
        fallback_policy="none",
        description="China PPI year-over-year growth.",
        source_detail="cn_ppi.ppi_yoy",
        value_field="ppi_yoy",
    ),
    "SHIBOR": IndicatorDefinition(
        name="SHIBOR",
        category="rate",
        frequency="daily",
        source="tushare",
        release_lag_days=0,
        importance="high",
        fallback_policy="none",
        description="Shanghai interbank offered rate, 3-month tenor.",
        source_detail="shibor.3m",
        value_field="3m",
    ),
    "CN10Y": IndicatorDefinition(
        name="CN10Y",
        category="rate",
        frequency="daily",
        source="tushare",
        release_lag_days=0,
        importance="high",
        fallback_policy="missing_if_yc_cb_permission_denied",
        description="China government bond 10-year yield. Local Tushare permission may be required.",
        source_detail="yc_cb.y10 candidate; permission dependent",
        value_field="y10",
    ),
    "US10Y": IndicatorDefinition(
        name="US10Y",
        category="external",
        frequency="daily",
        source="tushare",
        release_lag_days=0,
        importance="medium",
        fallback_policy="none",
        description="US Treasury 10-year constant maturity yield.",
        source_detail="us_tycr.y10",
        value_field="y10",
    ),
    "USD_CNH_offshore": IndicatorDefinition(
        name="USD_CNH_offshore",
        category="external",
        frequency="daily",
        source="tushare",
        release_lag_days=0,
        importance="medium",
        fallback_policy="USDCNH.FXCM_offshore_proxy",
        description="Offshore USD/CNH exchange rate used as external RMB pressure proxy.",
        source_detail="fx_daily.USDCNH.FXCM.bid_close",
        value_field="bid_close",
    ),
}


def get_indicator_definition(name: str) -> IndicatorDefinition:
    try:
        return INDICATOR_DEFINITIONS[name]
    except KeyError as exc:
        raise KeyError(f"Unknown macro indicator: {name}") from exc


def get_all_indicators() -> tuple[str, ...]:
    return tuple(INDICATOR_DEFINITIONS)


def get_all_indicator_definitions() -> tuple[IndicatorDefinition, ...]:
    return tuple(INDICATOR_DEFINITIONS.values())


def registry_as_dict() -> dict[str, dict[str, Any]]:
    return {name: definition.to_dict() for name, definition in INDICATOR_DEFINITIONS.items()}
