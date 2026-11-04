"""Data loading layer for TASK 1."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

from tenbagger.config import compact_date, default_start_date, get_setting
from tenbagger.schema import STANDARD_COLUMNS, empty_standard_frame, ensure_standard_schema


DEFAULT_REQUEST_INTERVAL_SECONDS = 0.4


@dataclass(frozen=True)
class LoadResult:
    frame: pd.DataFrame
    source: str
    requested_codes: list[str]
    loaded_codes: list[str]


class TenBaggerDataLoader:
    """Unified interface for TASK 1 data ingestion."""

    def __init__(
        self,
        token: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        request_interval: float | None = None,
    ) -> None:
        self.token = token or get_setting("TUSHARE_TOKEN")
        self.start_date = compact_date(start_date or default_start_date())
        self.end_date = compact_date(end_date)
        configured_interval = (
            get_setting("TUSHARE_REQUEST_INTERVAL_SECONDS", str(DEFAULT_REQUEST_INTERVAL_SECONDS))
            if request_interval is None
            else request_interval
        )
        self.request_interval = max(float(configured_interval), 0.0)

    def load_tushare(self, universe: Iterable[str]) -> LoadResult:
        """Load daily market, valuation, and financial data from TuShare."""

        if not self.token:
            raise RuntimeError("TUSHARE_TOKEN is required in .env or environment variables.")

        import tushare as ts

        ts.set_token(self.token)
        pro = ts.pro_api()

        basics = self._stock_basic(pro)
        requested_codes = self._normalize_universe(universe)

        frames: list[pd.DataFrame] = []
        loaded_codes: list[str] = []
        errors: dict[str, str] = {}

        for ts_code in requested_codes:
            try:
                stock_frame = self._load_one_tushare_stock(pro, basics, ts_code)
            except Exception as exc:  # pragma: no cover - defensive around remote APIs
                errors[ts_code] = str(exc)
                continue

            if not stock_frame.empty:
                frames.append(stock_frame)
                loaded_codes.append(ts_code)

            if self.request_interval > 0:
                time.sleep(self.request_interval)

        if not frames:
            detail = "; ".join(f"{code}: {message}" for code, message in errors.items())
            raise RuntimeError(f"TuShare returned no usable rows. {detail}")

        combined = pd.concat(frames, ignore_index=True)
        combined = ensure_standard_schema(combined)
        combined.attrs["load_errors"] = errors
        return LoadResult(
            frame=combined,
            source="tushare",
            requested_codes=requested_codes,
            loaded_codes=loaded_codes,
        )

    def load_baostock(self, *_args, **_kwargs) -> pd.DataFrame:
        """BaoStock interface placeholder for TASK 1 multi-source contract."""

        return empty_standard_frame()

    def load_qmt_positions(self, *_args, **_kwargs) -> pd.DataFrame:
        """QMT positions interface placeholder for read-only holdings import."""

        return empty_standard_frame()

    def load_yfinance(self, *_args, **_kwargs) -> pd.DataFrame:
        """yfinance interface placeholder for overseas comparable assets."""

        return empty_standard_frame()

    def load_all(self, universe: Iterable[str]) -> LoadResult:
        """Load the current TASK 1 primary source."""

        return self.load_tushare(universe=universe)

    def _stock_basic(self, pro) -> pd.DataFrame:
        fields = "ts_code,symbol,name,area,industry,list_date"
        return pro.stock_basic(exchange="", list_status="L", fields=fields)

    def _normalize_universe(self, universe: Iterable[str]) -> list[str]:
        requested_codes = list(
            dict.fromkeys(str(code).strip().upper() for code in universe if str(code).strip())
        )
        if not requested_codes:
            raise ValueError("DataLoader requires an explicit non-empty universe.")
        return requested_codes

    def _load_one_tushare_stock(self, pro, basics: pd.DataFrame, ts_code: str) -> pd.DataFrame:
        daily = pro.daily(
            ts_code=ts_code,
            start_date=self.start_date,
            end_date=self.end_date,
            fields="ts_code,trade_date,open,high,low,close",
        )
        if daily.empty:
            return empty_standard_frame()

        daily_basic = pro.daily_basic(
            ts_code=ts_code,
            start_date=self.start_date,
            end_date=self.end_date,
            fields="ts_code,trade_date,pe,pb,total_mv",
        )
        fundamentals = self._load_fundamentals(pro, ts_code)

        frame = daily.merge(daily_basic, on=["ts_code", "trade_date"], how="left")
        frame = frame.rename(columns={"trade_date": "date", "total_mv": "market_cap"})
        frame["date_dt"] = pd.to_datetime(frame["date"], format="%Y%m%d", errors="coerce")

        if not fundamentals.empty:
            frame = pd.merge_asof(
                frame.sort_values("date_dt"),
                fundamentals.sort_values("asof_dt"),
                left_on="date_dt",
                right_on="asof_dt",
                direction="backward",
            )
            frame["ts_code"] = frame["ts_code_x"].fillna(frame.get("ts_code_y"))
            frame = frame.drop(columns=[column for column in ["ts_code_x", "ts_code_y"] if column in frame])
        else:
            frame["revenue"] = pd.NA
            frame["net_profit"] = pd.NA
            frame["roe"] = pd.NA
            frame["ann_date"] = pd.NA
            frame["report_period"] = pd.NA
            frame["operating_cashflow"] = pd.NA
            frame["debt_ratio"] = pd.NA

        meta = basics[basics["ts_code"] == ts_code].head(1)
        if not meta.empty:
            for column in ["name", "industry", "area", "list_date"]:
                frame[column] = meta.iloc[0].get(column)

        frame["source"] = "tushare"
        frame["date"] = pd.to_datetime(frame["date"], format="%Y%m%d", errors="coerce").dt.strftime("%Y-%m-%d")
        frame = frame.dropna(subset=["date"])
        frame = frame.sort_values(["ts_code", "date"]).reset_index(drop=True)
        return ensure_standard_schema(frame)

    def _load_fundamentals(self, pro, ts_code: str) -> pd.DataFrame:
        finance_start = str(int(self.start_date[:4]) - 2) + "0101"

        income = pro.income(
            ts_code=ts_code,
            start_date=finance_start,
            end_date=self.end_date,
            fields="ts_code,ann_date,end_date,total_revenue,n_income",
        )
        indicator = pro.fina_indicator(
            ts_code=ts_code,
            start_date=finance_start,
            end_date=self.end_date,
            fields="ts_code,ann_date,end_date,roe",
        )
        cashflow = pro.cashflow(
            ts_code=ts_code,
            start_date=finance_start,
            end_date=self.end_date,
            fields="ts_code,ann_date,end_date,n_cashflow_act",
        )
        balance = pro.balancesheet(
            ts_code=ts_code,
            start_date=finance_start,
            end_date=self.end_date,
            fields="ts_code,ann_date,end_date,total_liab,total_assets",
        )

        income = self._latest_by_period(income).rename(
            columns={"total_revenue": "revenue", "n_income": "net_profit"}
        )
        indicator = self._latest_by_period(indicator)
        cashflow = self._latest_by_period(cashflow).rename(
            columns={"n_cashflow_act": "operating_cashflow"}
        )
        balance = self._latest_by_period(balance)
        if not balance.empty:
            balance["debt_ratio"] = pd.to_numeric(
                balance["total_liab"],
                errors="coerce",
            ) / pd.to_numeric(balance["total_assets"], errors="coerce").replace({0: pd.NA})

        fund = pd.merge(
            income[["ts_code", "ann_date", "end_date", "revenue", "net_profit"]],
            indicator[["ts_code", "ann_date", "end_date", "roe"]],
            on=["ts_code", "end_date"],
            how="outer",
            suffixes=("_income", "_indicator"),
        )
        fund = pd.merge(
            fund,
            cashflow[["ts_code", "ann_date", "end_date", "operating_cashflow"]],
            on=["ts_code", "end_date"],
            how="outer",
            suffixes=("", "_cashflow"),
        )
        balance_columns = ["ts_code", "ann_date", "end_date", "debt_ratio"]
        if balance.empty:
            balance = pd.DataFrame(columns=balance_columns)
        fund = pd.merge(
            fund,
            balance[balance_columns],
            on=["ts_code", "end_date"],
            how="outer",
            suffixes=("", "_balance"),
        )

        if fund.empty:
            return fund

        fund["ann_date"] = fund.apply(self._choose_announcement_date, axis=1)
        fund["report_period"] = fund["end_date"]
        fund["asof_dt"] = pd.to_datetime(
            fund["ann_date"].fillna(fund["end_date"]),
            format="%Y%m%d",
            errors="coerce",
        )
        fund = fund.dropna(subset=["asof_dt"]).sort_values("asof_dt")
        return fund[
            [
                "ts_code",
                "asof_dt",
                "ann_date",
                "report_period",
                "revenue",
                "net_profit",
                "roe",
                "operating_cashflow",
                "debt_ratio",
            ]
        ]

    @staticmethod
    def _latest_by_period(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        result = df.copy()
        result["ann_date"] = result["ann_date"].fillna(result["end_date"])
        result = result.sort_values(["end_date", "ann_date"])
        return result.drop_duplicates(["ts_code", "end_date"], keep="last")

    @staticmethod
    def _choose_announcement_date(row: pd.Series) -> str | None:
        candidates = [
            row.get("ann_date_income"),
            row.get("ann_date_indicator"),
            row.get("ann_date"),
            row.get("ann_date_cashflow"),
            row.get("ann_date_balance"),
            row.get("end_date"),
        ]
        valid = [str(value) for value in candidates if pd.notna(value)]
        if not valid:
            return None
        return max(valid)


def standard_columns() -> list[str]:
    return list(STANDARD_COLUMNS)
