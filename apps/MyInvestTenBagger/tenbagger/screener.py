"""Hard filters and candidate selection for TASK 3."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class HardFilterConfig:
    max_market_cap: float = 200e8
    min_revenue_growth: float = 0.15
    min_roe: float = 0.08
    max_debt_ratio: float = 0.65
    max_drawdown_floor: float = -0.60
    excluded_industries: tuple[str, ...] = ("银行", "地产", "全国地产", "区域地产", "保险")


class HardFilter:
    """Apply structural hard filters before ranking TenBagger candidates."""

    def __init__(self, config: HardFilterConfig | None = None) -> None:
        self.config = config or HardFilterConfig()

    def apply_filters(self, factors: pd.DataFrame, latest_only: bool = True) -> pd.DataFrame:
        if factors.empty:
            return factors.copy()

        data = factors.copy()
        if latest_only:
            data = data[data["date"] == data["date"].max()].copy()

        data["pass_market_cap"] = pd.to_numeric(data["market_cap"], errors="coerce").fillna(float("inf")) < self.config.max_market_cap
        data["pass_revenue_growth"] = pd.to_numeric(data["revenue_growth_yoy"], errors="coerce").fillna(-float("inf")) > self.config.min_revenue_growth
        data["pass_roe"] = pd.to_numeric(data["roe"], errors="coerce").fillna(-float("inf")) > self.config.min_roe
        data["pass_debt_ratio"] = pd.to_numeric(data.get("debt_ratio", 0.0), errors="coerce").fillna(float("inf")) < self.config.max_debt_ratio
        data["pass_drawdown"] = pd.to_numeric(data.get("max_drawdown_120d", 0.0), errors="coerce").fillna(-1.0) >= self.config.max_drawdown_floor
        data["pass_industry"] = ~data.get("industry", pd.Series("", index=data.index)).astype(str).isin(self.config.excluded_industries)

        pass_columns = [
            "pass_market_cap",
            "pass_revenue_growth",
            "pass_roe",
            "pass_debt_ratio",
            "pass_drawdown",
            "pass_industry",
        ]
        data["is_candidate"] = data[pass_columns].all(axis=1)
        data["fail_reasons"] = data.apply(self._fail_reasons, axis=1)
        return data.sort_values(["is_candidate", "tenbagger_score"], ascending=[False, False])

    @staticmethod
    def top_candidates(filtered: pd.DataFrame, limit: int = 20) -> pd.DataFrame:
        if filtered.empty:
            return filtered.copy()
        return filtered[filtered["is_candidate"]].head(limit).copy()

    @staticmethod
    def near_misses(filtered: pd.DataFrame, limit: int = 20) -> pd.DataFrame:
        if filtered.empty:
            return filtered.copy()
        return filtered[~filtered["is_candidate"]].head(limit).copy()

    @staticmethod
    def _fail_reasons(row: pd.Series) -> str:
        reasons: list[str] = []
        checks = {
            "market_cap": row.get("pass_market_cap", False),
            "revenue_growth": row.get("pass_revenue_growth", False),
            "roe": row.get("pass_roe", False),
            "debt_ratio": row.get("pass_debt_ratio", False),
            "drawdown": row.get("pass_drawdown", False),
            "industry": row.get("pass_industry", False),
        }
        for name, passed in checks.items():
            if not bool(passed):
                reasons.append(name)
        return ",".join(reasons)
