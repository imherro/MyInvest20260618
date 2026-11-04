from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import random
import time
from typing import Optional

import pandas as pd

from config.settings import FORCE_MOCK_DATA, MOCK_STOCK_COUNT, TUSHARE_TOKEN
from data.cache_manager import CacheManager
from data.trade_calendar import format_api_date, get_latest_trading_date, normalize_trade_date
from engine.theme_engine import TUSHARE_THEME_MATCH_KEYWORDS, classify_theme_name


@dataclass(frozen=True)
class MarketData:
    trade_date: str
    stock_basic: pd.DataFrame
    daily: pd.DataFrame
    daily_basic: pd.DataFrame
    financial_indicator: pd.DataFrame
    theme_membership: pd.DataFrame
    mock_mode: bool
    source: str
    data_version: str


class TushareDataLoader:
    def __init__(
        self,
        token: str | None = None,
        force_mock: bool | None = None,
        cache: CacheManager | None = None,
    ) -> None:
        self.token = token if token is not None else TUSHARE_TOKEN
        self.force_mock = FORCE_MOCK_DATA if force_mock is None else force_mock
        self.cache = cache or CacheManager()

    def get_universe(self) -> list[str]:
        return self.load_market_data().stock_basic["ts_code"].tolist()

    def get_daily_data(self, trade_date: str | None = None) -> pd.DataFrame:
        market_data = self.load_market_data(trade_date)
        return market_data.daily.merge(
            market_data.daily_basic,
            on=["ts_code", "trade_date"],
            how="left",
            suffixes=("", "_basic"),
        )

    def load_market_data(self, trade_date: str | None = None) -> MarketData:
        normalized_date = get_latest_trading_date(normalize_trade_date(trade_date))
        if not self.force_mock and self.token:
            try:
                return self._load_tushare_market_data(normalized_date)
            except Exception:
                pass
        return self._load_mock_market_data(normalized_date)

    def _load_tushare_market_data(self, trade_date: str) -> MarketData:
        import tushare as ts

        ts.set_token(self.token)
        pro = ts.pro_api(self.token)
        calendar = self._cached_dataframe(
            "calendar",
            f"trade_cal_{trade_date[:4]}",
            lambda: pro.trade_cal(
                exchange="SSE",
                start_date=f"{trade_date[:4]}0101",
                end_date=trade_date,
                fields="cal_date,is_open",
            ),
        )
        latest_trade_date = get_latest_trading_date(trade_date, calendar)
        start_date = (
            datetime.strptime(latest_trade_date, "%Y%m%d") - timedelta(days=260)
        ).strftime("%Y%m%d")
        window_calendar = self._cached_dataframe(
            "calendar",
            f"trade_cal_{start_date}_{latest_trade_date}",
            lambda: pro.trade_cal(
                exchange="SSE",
                start_date=start_date,
                end_date=latest_trade_date,
                fields="cal_date,is_open",
            ),
        )

        stock_basic = self._cached_dataframe(
            "universe",
            "stock_basic_L",
            lambda: pro.stock_basic(
                exchange="",
                list_status="L",
                fields="ts_code,symbol,name,area,industry,list_date",
            ),
            max_age_seconds=24 * 60 * 60,
        )
        daily = self._cached_dataframe(
            "daily",
            f"daily_window_v3_{start_date}_{latest_trade_date}",
            lambda: self._load_daily_window(
                pro,
                window_calendar,
                start_date,
                latest_trade_date,
            ),
        )
        if daily.empty:
            raise ValueError("Tushare returned no daily rows")

        latest_trade_date = str(daily["trade_date"].max())
        daily_basic = self._cached_dataframe(
            "basic",
            f"daily_basic_{latest_trade_date}",
            lambda: pro.daily_basic(
                trade_date=latest_trade_date,
                fields="ts_code,trade_date,pe,pb,turnover_rate,volume_ratio",
            ),
        )
        if daily_basic.empty:
            raise ValueError("Tushare returned no daily_basic rows")
        financial_indicator = self._cached_dataframe(
            "basic",
            f"financial_indicator_v2_{latest_trade_date}",
            lambda: self._load_recent_financial_indicator(
                pro,
                self._recent_report_periods(latest_trade_date, count=2),
            ),
        )
        theme_membership = self._cached_dataframe(
            "theme",
            "growth_theme_membership_v1",
            lambda: self._load_growth_theme_membership(pro),
            max_age_seconds=7 * 24 * 60 * 60,
        )

        return MarketData(
            trade_date=latest_trade_date,
            stock_basic=stock_basic,
            daily=daily,
            daily_basic=daily_basic,
            financial_indicator=financial_indicator,
            theme_membership=theme_membership,
            mock_mode=False,
            source="tushare",
            data_version=self._data_version(
                "tushare",
                stock_basic,
                daily,
                daily_basic,
                financial_indicator,
                theme_membership,
            ),
        )

    def _load_mock_market_data(self, trade_date: str) -> MarketData:
        trade_date = get_latest_trading_date(trade_date)
        rng = random.Random(int(trade_date))
        end = pd.Timestamp(datetime.strptime(trade_date, "%Y%m%d"))
        dates = pd.bdate_range(end=end, periods=140)

        stocks = []
        daily_rows = []
        basic_rows = []
        financial_rows = []
        industries = ["Bank", "Tech", "Pharma", "Consumer", "Energy", "Auto"]

        for idx in range(MOCK_STOCK_COUNT):
            symbol = f"{idx + 1:06d}"
            suffix = "SZ" if idx % 2 == 0 else "SH"
            ts_code = f"{symbol}.{suffix}"
            is_st = idx in {4, 17}
            is_suspended = idx in {8, 23}
            name = f"{'*ST ' if is_st else ''}MockStock{idx + 1:02d}"
            industry = industries[idx % len(industries)]
            stocks.append(
                {
                    "ts_code": ts_code,
                    "symbol": symbol,
                    "name": name,
                    "area": "CN",
                    "industry": industry,
                    "list_date": "20180101",
                }
            )

            base_price = 8 + idx * 0.7 + rng.random() * 2
            drift = 0.0005 + (idx % 7) * 0.0006
            prices = []
            last_price = base_price
            for date_index, day in enumerate(dates):
                shock = rng.uniform(-0.018, 0.022)
                last_price = max(2.0, last_price * (1 + drift + shock))
                prices.append((day.strftime("%Y%m%d"), round(last_price, 2)))

                if date_index == len(dates) - 1 and is_suspended:
                    continue

                pre_close = prices[-2][1] if len(prices) > 1 else base_price
                pct_chg = (last_price / pre_close - 1) * 100
                daily_rows.append(
                    {
                        "ts_code": ts_code,
                        "trade_date": day.strftime("%Y%m%d"),
                        "close": round(last_price, 2),
                        "pre_close": round(pre_close, 2),
                        "pct_chg": round(pct_chg, 4),
                        "vol": round(10000 + rng.random() * 90000, 2),
                        "amount": round(last_price * (1000 + rng.random() * 5000), 2),
                        "is_suspended": is_suspended
                        and date_index == len(dates) - 1,
                    }
                )

            latest_date = dates[-1].strftime("%Y%m%d")
            pe = 9 + (idx % 12) * 2.3 + rng.random() * 3
            pb = 0.8 + (idx % 8) * 0.22 + rng.random() * 0.2
            roe = 6 + (idx % 10) * 1.6 + rng.random() * 2
            basic_rows.append(
                {
                    "ts_code": ts_code,
                    "trade_date": latest_date,
                    "pe": round(pe, 4),
                    "pb": round(pb, 4),
                    "roe": round(roe, 4),
                    "turnover_rate": round(1 + rng.random() * 6, 4),
                    "volume_ratio": round(0.7 + rng.random() * 1.8, 4),
                }
            )
            current_period, previous_period = self._recent_report_periods(latest_date, count=2)
            revenue_growth = -5 + (idx % 12) * 2.5 + rng.random() * 3
            profit_growth = -8 + (idx % 10) * 3.2 + rng.random() * 4
            roe_delta = -1.5 + (idx % 6) * 0.55 + rng.random() * 0.4
            financial_rows.extend(
                [
                    {
                        "ts_code": ts_code,
                        "end_date": previous_period,
                        "roe": round(max(0.1, roe - roe_delta), 4),
                        "revenue_growth_yoy": round(revenue_growth - rng.uniform(-2.0, 2.5), 4),
                        "net_profit_growth_yoy": round(profit_growth - rng.uniform(-3.0, 3.5), 4),
                        "ocf_to_profit": round(0.50 + (idx % 8) * 0.10 + rng.random() * 0.18, 4),
                    },
                    {
                        "ts_code": ts_code,
                        "end_date": current_period,
                        "roe": round(roe, 4),
                        "revenue_growth_yoy": round(revenue_growth, 4),
                        "net_profit_growth_yoy": round(profit_growth, 4),
                        "ocf_to_profit": round(0.55 + (idx % 8) * 0.12 + rng.random() * 0.2, 4),
                    },
                ]
            )

        stock_basic = pd.DataFrame(stocks)
        daily = pd.DataFrame(daily_rows)
        daily_basic = pd.DataFrame(basic_rows)
        financial_indicator = pd.DataFrame(financial_rows)
        theme_membership = self._build_mock_theme_membership(stock_basic)

        return MarketData(
            trade_date=dates[-1].strftime("%Y%m%d"),
            stock_basic=stock_basic,
            daily=daily,
            daily_basic=daily_basic,
            financial_indicator=financial_indicator,
            theme_membership=theme_membership,
            mock_mode=True,
            source="mock",
            data_version=self._data_version(
                "mock",
                stock_basic,
                daily,
                daily_basic,
                financial_indicator,
                theme_membership,
            ),
        )

    def _cached_dataframe(
        self,
        namespace: str,
        key: str,
        fetcher,
        max_age_seconds: int | None = None,
    ) -> pd.DataFrame:
        cached = self.cache.get_dataframe(namespace, key, max_age_seconds=max_age_seconds)
        if cached is not None:
            return cached

        frame = fetcher()
        if frame is None:
            frame = pd.DataFrame()
        self.cache.set_dataframe(namespace, key, frame)
        return frame

    def _load_daily_window(
        self,
        pro,
        calendar: pd.DataFrame,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        if not calendar.empty and {"cal_date", "is_open"} <= set(calendar.columns):
            open_dates = (
                calendar[
                    (calendar["cal_date"].astype(str) >= start_date)
                    & (calendar["cal_date"].astype(str) <= end_date)
                    & (pd.to_numeric(calendar["is_open"], errors="coerce") == 1)
                ]["cal_date"]
                .astype(str)
                .sort_values()
                .tolist()
            )
        else:
            open_dates = [
                day.strftime("%Y%m%d")
                for day in pd.bdate_range(
                    start=datetime.strptime(start_date, "%Y%m%d"),
                    end=datetime.strptime(end_date, "%Y%m%d"),
                )
            ]

        frames = []
        for day in open_dates:
            try:
                frame = self._cached_dataframe(
                    "daily",
                    f"daily_by_date_{day}",
                    lambda day=day: self._fetch_daily_with_retry(pro, day),
                )
            except Exception:
                continue
            if not frame.empty:
                frames.append(frame)
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    @staticmethod
    def _fetch_daily_with_retry(pro, trade_date: str, attempts: int = 3) -> pd.DataFrame:
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                return pro.daily(trade_date=trade_date)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt < attempts - 1:
                    time.sleep(0.5 * (attempt + 1))
        if last_error is not None:
            raise last_error
        return pd.DataFrame()

    def _load_financial_indicator(self, pro, period: str) -> pd.DataFrame:
        try:
            return pro.fina_indicator(
                period=period,
                fields="ts_code,end_date,roe,or_yoy,netprofit_yoy,ocf_to_profit",
            )
        except Exception:
            return pd.DataFrame(
                columns=[
                    "ts_code",
                    "end_date",
                    "roe",
                    "or_yoy",
                    "netprofit_yoy",
                    "ocf_to_profit",
                ]
            )

    def _load_recent_financial_indicator(self, pro, periods: list[str]) -> pd.DataFrame:
        frames = [self._load_financial_indicator(pro, period) for period in periods]
        frames = [frame for frame in frames if not frame.empty]
        if not frames:
            return pd.DataFrame(
                columns=[
                    "ts_code",
                    "end_date",
                    "roe",
                    "or_yoy",
                    "netprofit_yoy",
                    "ocf_to_profit",
                ]
            )
        return pd.concat(frames, ignore_index=True)

    def _load_growth_theme_membership(self, pro) -> pd.DataFrame:
        indexes = self._load_tushare_theme_index(pro)
        if indexes.empty:
            return pd.DataFrame(columns=["ts_code", "theme_name", "theme_group", "theme_source"])

        indexes["theme_group"] = indexes["theme_name"].map(classify_theme_name)
        indexes = indexes.dropna(subset=["theme_group"])
        if indexes.empty:
            return pd.DataFrame(columns=["ts_code", "theme_name", "theme_group", "theme_source"])

        frames = []
        for _, theme in indexes.head(80).iterrows():
            try:
                members = pro.ths_member(
                    ts_code=theme["theme_code"],
                    fields="ts_code,con_code,con_name",
                )
            except Exception:
                continue
            if members is None or members.empty:
                continue
            code_column = "con_code" if "con_code" in members.columns else "ts_code"
            if code_column not in members.columns:
                continue
            frames.append(
                pd.DataFrame(
                    {
                        "ts_code": members[code_column].astype(str),
                        "theme_name": str(theme["theme_name"]),
                        "theme_group": str(theme["theme_group"]),
                        "theme_source": "tushare_ths",
                    }
                )
            )
        if not frames:
            return pd.DataFrame(columns=["ts_code", "theme_name", "theme_group", "theme_source"])
        return pd.concat(frames, ignore_index=True).drop_duplicates()

    @staticmethod
    def _load_tushare_theme_index(pro) -> pd.DataFrame:
        attempts = [
            lambda: pro.ths_index(exchange="A", type="N", fields="ts_code,name"),
            lambda: pro.ths_index(type="N", fields="ts_code,name"),
            lambda: pro.ths_index(fields="ts_code,name"),
        ]
        for attempt in attempts:
            try:
                indexes = attempt()
            except Exception:
                continue
            if indexes is None or indexes.empty or not {"ts_code", "name"} <= set(indexes.columns):
                continue
            normalized = indexes.rename(columns={"ts_code": "theme_code", "name": "theme_name"})
            match_text = normalized["theme_name"].fillna("").astype(str)
            matched = pd.Series(False, index=normalized.index)
            for keyword in TUSHARE_THEME_MATCH_KEYWORDS:
                matched = matched | match_text.str.contains(keyword, case=False, regex=False, na=False)
            return normalized.loc[matched, ["theme_code", "theme_name"]].drop_duplicates()
        return pd.DataFrame(columns=["theme_code", "theme_name"])

    @staticmethod
    def _build_mock_theme_membership(stock_basic: pd.DataFrame) -> pd.DataFrame:
        if stock_basic.empty:
            return pd.DataFrame(columns=["ts_code", "theme_name", "theme_group", "theme_source"])
        rows = []
        theme_by_industry = {
            "Tech": ("AI算力", "AI算力"),
            "Auto": ("新能源智能车", "新能源智能车"),
            "Pharma": ("创新药医疗", "创新药医疗"),
        }
        for _, stock in stock_basic.iterrows():
            theme = theme_by_industry.get(str(stock.get("industry") or ""))
            if theme is None:
                continue
            rows.append(
                {
                    "ts_code": stock["ts_code"],
                    "theme_name": theme[0],
                    "theme_group": theme[1],
                    "theme_source": "mock",
                }
            )
        return pd.DataFrame(rows, columns=["ts_code", "theme_name", "theme_group", "theme_source"])

    @staticmethod
    def _latest_report_period(trade_date: str) -> str:
        parsed = datetime.strptime(trade_date, "%Y%m%d")
        year = parsed.year
        candidates = [f"{year}1231", f"{year}0930", f"{year}0630", f"{year}0331"]
        for candidate in candidates:
            if candidate <= trade_date:
                return candidate
        return f"{year - 1}1231"

    @classmethod
    def _recent_report_periods(cls, trade_date: str, count: int) -> list[str]:
        latest = cls._latest_report_period(trade_date)
        latest_year = int(latest[:4])
        periods = []
        for year in range(latest_year, latest_year - 3, -1):
            periods.extend([f"{year}1231", f"{year}0930", f"{year}0630", f"{year}0331"])
        periods = [period for period in periods if period <= latest]
        return periods[: max(count, 1)]

    @staticmethod
    def _data_version(source: str, *frames: pd.DataFrame) -> str:
        digest = hashlib.sha256(source.encode("utf-8"))
        for frame in frames:
            if frame.empty:
                digest.update(b"empty")
                continue
            normalized = frame.copy()
            normalized = normalized.reindex(sorted(normalized.columns), axis=1)
            normalized = normalized.astype(str).sort_values(list(normalized.columns))
            hashed = pd.util.hash_pandas_object(normalized, index=False).values
            digest.update(hashed.tobytes())
        return digest.hexdigest()[:20]
