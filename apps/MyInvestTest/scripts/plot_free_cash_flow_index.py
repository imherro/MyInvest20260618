from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests


TODAY = datetime.now().strftime("%Y%m%d")
DEFAULT_CODE = "480092.CNI"
DEFAULT_CNINDEX_CODE = "480092"
DEFAULT_NAME = "国证自由现金流全收益指数"
DEFAULT_START_DATE = "20160101"
DEFAULT_TURNING_REVERSAL = 0.15
DEFAULT_Y_SCALE = "log"
TUSHARE_API_URL = "http://api.tushare.pro"
THEME_LATEST_API_URL = "https://theme.okbbc.com/api/latest"

MARKET_CYCLE_BLOCKS: list[dict[str, str | None]] = [
    {"state": "bear", "start_date": "20150615", "end_date": "20160127", "label": "2015-2016 股灾熊市"},
    {"state": "bull", "start_date": "20160128", "end_date": "20180129", "label": "2016-2018 结构牛"},
    {"state": "bear", "start_date": "20180130", "end_date": "20190104", "label": "2018 去杠杆熊市"},
    {"state": "bull", "start_date": "20190107", "end_date": "20210218", "label": "2019-2021 结构牛"},
    {"state": "bear", "start_date": "20210219", "end_date": "20240923", "label": "2021-2024 长熊"},
    {"state": "bull", "start_date": "20240924", "end_date": None, "label": "2024 至今修复牛"},
]

MAINLINE_INDEXES: list[dict[str, Any]] = [
    {"group": "A股策略", "name": "自由现金流R", "code": "480092.CNI", "api": "main", "default": False, "return_type": "全收益"},
    {"group": "A股策略", "name": "国信价值全收益", "code": "H21052.CSI", "api": "index_daily", "default": False, "return_type": "全收益"},
    {"group": "A股策略", "name": "创成长R", "code": "CN2296.CNI", "api": "cnindex_daily", "default": False, "return_type": "全收益"},
    {"group": "A股策略", "name": "中证红利收益", "code": "H00922.CSI", "api": "index_daily", "default": False, "return_type": "全收益"},
    {"group": "A股宽基", "name": "上证收益", "code": "000888.SH", "api": "index_daily", "default": False, "return_type": "全收益"},
    {"group": "A股宽基", "name": "沪深300收益", "code": "H00300.CSI", "api": "index_daily", "default": True, "return_type": "全收益"},
    {"group": "A股宽基", "name": "中证500收益", "code": "H00905.CSI", "api": "index_daily", "default": False, "return_type": "全收益"},
    {"group": "A股宽基", "name": "中证1000全收益", "code": "H00852.CSI", "api": "index_daily", "default": False, "return_type": "全收益"},
    {"group": "A股宽基", "name": "中证2000全收益", "code": "932000CNY010.CSI", "api": "index_daily", "default": False, "return_type": "全收益"},
    {"group": "A股宽基", "name": "创业板R", "code": "399606.SZ", "api": "index_daily", "default": False, "return_type": "全收益"},
    {"group": "A股宽基", "name": "科创50(全)", "code": "000688CNY01.CSI", "api": "index_daily", "default": False, "return_type": "全收益"},
    {"group": "第一主线：AI科技与自主可控", "name": "人工智能主题全收益", "code": "H20713.CSI", "api": "index_daily", "default": False, "return_type": "全收益"},
    {"group": "第一主线：AI科技与自主可控", "name": "算力基础设施全收益", "code": "931688CNY010.CSI", "api": "index_daily", "default": False, "return_type": "全收益"},
    {"group": "第一主线：AI科技与自主可控", "name": "芯片产业全收益", "code": "H20007.CSI", "api": "index_daily", "default": False, "return_type": "全收益"},
    {"group": "第一主线：AI科技与自主可控", "name": "半导体材料设备全收益", "code": "931743CNY010.CSI", "api": "index_daily", "default": False, "return_type": "全收益"},
    {"group": "第一主线：AI科技与自主可控", "name": "通信设备全收益", "code": "H21160.CSI", "api": "index_daily", "default": False, "return_type": "全收益"},
    {"group": "第一主线：AI科技与自主可控", "name": "卫星产业全收益", "code": "931594CNY01.CSI", "api": "index_daily", "default": False, "return_type": "全收益"},
    {"group": "第二主线：再通胀、资源品和反内卷盈利修复", "name": "钢铁全收益", "code": "H20606.CSI", "api": "index_daily", "default": False, "return_type": "全收益"},
    {"group": "第二主线：再通胀、资源品和反内卷盈利修复", "name": "煤炭全收益", "code": "H20596.CSI", "api": "index_daily", "default": False, "return_type": "全收益"},
    {"group": "第二主线：再通胀、资源品和反内卷盈利修复", "name": "细分化工全收益", "code": "H00813.CSI", "api": "index_daily", "default": False, "return_type": "全收益"},
    {"group": "第二主线：再通胀、资源品和反内卷盈利修复", "name": "细分有色全收益", "code": "H00811.CSI", "api": "index_daily", "default": False, "return_type": "全收益"},
    {"group": "第二主线：再通胀、资源品和反内卷盈利修复", "name": "稀土产业全收益", "code": "H20598.CSI", "api": "index_daily", "default": False, "return_type": "全收益"},
    {"group": "第三主线：电力能源与先进制造", "name": "绿色电力全收益", "code": "931897CNY01.CSI", "api": "index_daily", "default": False, "return_type": "全收益"},
    {"group": "第三主线：电力能源与先进制造", "name": "电力公用事业全收益", "code": "H20199.CSI", "api": "index_daily", "default": False, "return_type": "全收益"},
    {"group": "第三主线：电力能源与先进制造", "name": "智选电网主题全收益", "code": "932611CNY010.CSI", "api": "index_daily", "default": False, "return_type": "全收益"},
    {"group": "第三主线：电力能源与先进制造", "name": "储能主题全收益", "code": "931747CNY01.CSI", "api": "index_daily", "default": False, "return_type": "全收益"},
    {"group": "第三主线：电力能源与先进制造", "name": "机床全收益", "code": "931866CNY01.CSI", "api": "index_daily", "default": False, "return_type": "全收益"},
    {"group": "第三主线：电力能源与先进制造", "name": "机器人全收益", "code": "H20590.CSI", "api": "index_daily", "default": False, "return_type": "全收益"},
    {"group": "第三主线：电力能源与先进制造", "name": "通用航空全收益", "code": "931855CNY010.CSI", "api": "index_daily", "default": False, "return_type": "全收益"},
    {"group": "历史主线", "name": "中证传媒全收益", "code": "H20319.CSI", "api": "index_daily", "default": False, "return_type": "全收益"},
    {"group": "历史主线", "name": "动漫游戏全收益", "code": "H20901.CSI", "api": "index_daily", "default": False, "return_type": "全收益"},
    {"group": "历史主线", "name": "大消费360全收益", "code": "H00997.CSI", "api": "index_daily", "default": False, "return_type": "全收益"},
    {"group": "历史主线", "name": "中证白酒全收益", "code": "H20539.CSI", "api": "index_daily", "default": False, "return_type": "全收益"},
    {"group": "历史主线", "name": "全指医药全收益", "code": "H00991.CSI", "api": "index_daily", "default": False, "return_type": "全收益"},
    {"group": "历史主线", "name": "沪港深创新药全收益", "code": "921409.CSI", "api": "index_daily", "default": False, "return_type": "全收益"},
    {"group": "历史主线", "name": "全指银行全收益", "code": "H20180.CSI", "api": "index_daily", "default": False, "return_type": "全收益"},
    {"group": "历史主线", "name": "上证证券全收益", "code": "H40105.CSI", "api": "index_daily", "default": False, "return_type": "全收益"},
    {"group": "历史主线", "name": "沪深300非银全收益", "code": "H20035.CSI", "api": "index_daily", "default": False, "return_type": "全收益"},
    {"group": "历史主线", "name": "房地产全收益", "code": "931775CNY01.CSI", "api": "index_daily", "default": False, "return_type": "全收益"},
    {"group": "历史主线", "name": "新能源全收益", "code": "H20771.CSI", "api": "index_daily", "default": False, "return_type": "全收益"},
    {"group": "历史主线", "name": "军工全收益", "code": "H20229.CSI", "api": "index_daily", "default": False, "return_type": "全收益"},
    {"group": "大类资产", "name": "上海金 Au99.99", "code": "Au99.99", "api": "sge_daily", "default": False, "return_type": "现货价格"},
    {"group": "大类资产", "name": "30年国债利息再投资", "code": "931080CNY050.CSI", "api": "index_daily", "default": False, "return_type": "利息再投资"},
    {"group": "大类资产", "name": "有色期货ETF", "code": "159980.SZ", "api": "fund_daily_adj", "default": False, "return_type": "ETF复权"},
    {"group": "大类资产", "name": "能源化工ETF", "code": "159981.SZ", "api": "fund_daily_adj", "default": False, "return_type": "ETF复权"},
    {"group": "海外市场", "name": "标普500全收益", "code": "^SP500TR", "api": "yahoo_daily", "default": False, "return_type": "全收益", "currency": "USD"},
    {"group": "海外市场", "name": "纳斯达克综合全收益", "code": "^XCMP", "api": "yahoo_daily", "default": False, "return_type": "全收益", "currency": "USD"},
    {"group": "海外市场", "name": "全球股票ETF VT", "code": "VT", "api": "yahoo_adj_daily", "default": False, "return_type": "ETF复权", "currency": "USD"},
    {"group": "海外市场", "name": "全球除美国ETF VXUS", "code": "VXUS", "api": "yahoo_adj_daily", "default": False, "return_type": "ETF复权", "currency": "USD"},
    {"group": "海外市场", "name": "美国自由现金流ETF COWZ", "code": "COWZ", "api": "yahoo_adj_daily", "default": False, "return_type": "ETF复权", "currency": "USD"},
]

HOT_MAINLINE_INDEX_MAP: dict[str, list[str]] = {
    "new_energy_power_equipment": ["H20771.CSI"],
    "ai_compute_communications": ["931688CNY010.CSI"],
    "hard_tech_semiconductor": ["H20007.CSI", "931743CNY010.CSI"],
    "resources_cycle": ["H00805.CSI"],
    "high_end_manufacturing_robotics_defense": ["H20590.CSI"],
    "infrastructure_materials": ["801710.SI", "801720.SI"],
    "consumption_media": ["801120.SI", "801760.SI"],
    "innovative_medicine": ["H21152.CSI", "801150.SI"],
}

_TUSHARE_CACHE: dict[tuple[str, str, str, str], pd.DataFrame] = {}


@dataclass
class IndexSeries:
    code: str
    name: str
    source: str
    data: pd.DataFrame
    base_date: str = "20121231"
    note: str = ""


def load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def normalize_trade_date(value: Any) -> str:
    text = str(value)
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return pd.to_datetime(value).strftime("%Y-%m-%d")


def compact_trade_date(value: Any) -> str:
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return text
    return pd.to_datetime(value).strftime("%Y%m%d")


def tushare_token() -> str:
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        raise RuntimeError("未找到 TUSHARE_TOKEN，无法获取主线指数行情。")
    return token


def fetch_tushare_daily(api_name: str, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    start = compact_trade_date(start_date)
    end = compact_trade_date(end_date)
    cache_key = (api_name, ts_code, start, end)
    if cache_key in _TUSHARE_CACHE:
        return _TUSHARE_CACHE[cache_key].copy()

    if api_name == "sw_daily":
        fields = "ts_code,trade_date,close,pct_change,name"
    elif api_name == "sge_daily":
        fields = "ts_code,trade_date,close"
    else:
        fields = "ts_code,trade_date,close,pct_chg"

    response = requests.post(
        TUSHARE_API_URL,
        json={
            "api_name": api_name,
            "token": tushare_token(),
            "params": {"ts_code": ts_code, "start_date": start, "end_date": end},
            "fields": fields,
        },
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"Tushare {api_name} {ts_code} 返回异常：{payload.get('msg')}")

    data = payload.get("data") or {}
    columns = data.get("fields") or []
    items = data.get("items") or []
    frame = pd.DataFrame(items, columns=columns)
    if frame.empty:
        _TUSHARE_CACHE[cache_key] = frame
        return frame.copy()

    frame["trade_date"] = frame["trade_date"].astype(str)
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    if "pct_change" in frame.columns and "pct_chg" not in frame.columns:
        frame = frame.rename(columns={"pct_change": "pct_chg"})
    if "pct_chg" in frame.columns:
        frame["pct_chg"] = pd.to_numeric(frame["pct_chg"], errors="coerce")
    frame = frame.dropna(subset=["trade_date", "close"]).sort_values("trade_date")
    frame = frame.drop_duplicates("trade_date", keep="last").reset_index(drop=True)
    _TUSHARE_CACHE[cache_key] = frame
    return frame.copy()


def fetch_tushare_sge_daily(ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    start_year = int(compact_trade_date(start_date)[:4])
    end_year = int(compact_trade_date(end_date)[:4])
    frames: list[pd.DataFrame] = []
    for year in range(start_year, end_year + 1):
        chunk_start = max(compact_trade_date(start_date), f"{year}0101")
        chunk_end = min(compact_trade_date(end_date), f"{year}1231")
        frame = fetch_tushare_daily("sge_daily", ts_code, chunk_start, chunk_end)
        if not frame.empty:
            frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=["trade_date", "close"])
    return pd.concat(frames, ignore_index=True).drop_duplicates("trade_date").sort_values("trade_date")


def fetch_tushare_fund_daily_adj(ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    daily = fetch_tushare_daily("fund_daily", ts_code, start_date, end_date)
    if daily.empty:
        return daily
    response = requests.post(
        TUSHARE_API_URL,
        json={
            "api_name": "fund_adj",
            "token": tushare_token(),
            "params": {
                "ts_code": ts_code,
                "start_date": compact_trade_date(start_date),
                "end_date": compact_trade_date(end_date),
            },
            "fields": "ts_code,trade_date,adj_factor",
        },
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"Tushare fund_adj {ts_code} 返回异常：{payload.get('msg')}")
    data = payload.get("data") or {}
    factors = pd.DataFrame(data.get("items") or [], columns=data.get("fields") or [])
    if factors.empty:
        raise RuntimeError(f"Tushare fund_adj {ts_code} 没有返回复权因子。")
    factors["trade_date"] = factors["trade_date"].astype(str)
    factors["adj_factor"] = pd.to_numeric(factors["adj_factor"], errors="coerce")
    frame = daily.merge(factors[["trade_date", "adj_factor"]], on="trade_date", how="left")
    frame["adj_factor"] = frame["adj_factor"].ffill().bfill()
    frame["close"] = frame["close"] * frame["adj_factor"]
    return frame.dropna(subset=["close"]).reset_index(drop=True)


def fetch_yahoo_daily(symbol: str, start_date: str, end_date: str, adjusted: bool = False) -> pd.DataFrame:
    start = pd.Timestamp(normalize_trade_date(start_date), tz="UTC")
    end = pd.Timestamp(normalize_trade_date(end_date), tz="UTC") + pd.Timedelta(days=1)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{requests.utils.quote(symbol, safe='')}"
    response = requests.get(
        url,
        params={
            "period1": int(start.timestamp()),
            "period2": int(end.timestamp()),
            "interval": "1d",
            "events": "history",
        },
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=60,
    )
    response.raise_for_status()
    chart = response.json().get("chart") or {}
    if chart.get("error"):
        raise RuntimeError(f"Yahoo {symbol} 返回异常：{chart['error']}")
    result = (chart.get("result") or [None])[0]
    if not result:
        return pd.DataFrame(columns=["trade_date", "close"])
    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators") or {}
    closes = ((indicators.get("quote") or [{}])[0].get("close") or [])
    if adjusted:
        adjusted_closes = ((indicators.get("adjclose") or [{}])[0].get("adjclose") or [])
        if len(adjusted_closes) == len(timestamps):
            closes = adjusted_closes
    frame = pd.DataFrame(
        {
            "trade_date": [pd.to_datetime(value, unit="s", utc=True).strftime("%Y%m%d") for value in timestamps],
            "close": closes,
        }
    )
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    return frame.dropna(subset=["close"]).drop_duplicates("trade_date").sort_values("trade_date")


def fetch_mainline_candidate(
    item: dict[str, Any], series: IndexSeries, start_date: str, end_date: str
) -> tuple[pd.DataFrame, str]:
    api_name = str(item["api"])
    if api_name == "main":
        return series.data[["trade_date", "close"]].copy(), series.source
    if api_name == "cnindex_daily":
        return fetch_cnindex_daily(str(item["code"]).split(".")[0], start_date, end_date), "国证官网"
    if api_name == "sge_daily":
        return fetch_tushare_sge_daily(str(item["code"]), start_date, end_date), "上海黄金交易所/Tushare"
    if api_name == "fund_daily_adj":
        return fetch_tushare_fund_daily_adj(str(item["code"]), start_date, end_date), "Tushare ETF复权"
    if api_name == "yahoo_daily":
        return fetch_yahoo_daily(str(item["code"]), start_date, end_date), "Yahoo Finance"
    if api_name == "yahoo_adj_daily":
        return fetch_yahoo_daily(str(item["code"]), start_date, end_date, adjusted=True), "Yahoo Finance复权"
    return fetch_tushare_daily(api_name, str(item["code"]), start_date, end_date), "Tushare"


def frame_to_close_points(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    return [
        {
            "trade_date": normalize_trade_date(row.trade_date),
            "close": float(row.close),
        }
        for row in frame.itertuples(index=False)
    ]


def fetch_latest_theme_context() -> dict[str, Any]:
    empty = {
        "source": THEME_LATEST_API_URL,
        "basisDate": "",
        "generatedAt": "",
        "hotMainlines": [],
        "hotByCode": {},
        "error": "",
    }
    try:
        response = requests.get(THEME_LATEST_API_URL, timeout=40)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        return {**empty, "error": str(exc)}

    result = payload.get("result") or payload
    ranking = result.get("mainline_ranking") or []
    hot_mainlines: list[dict[str, Any]] = []
    hot_by_code: dict[str, list[dict[str, Any]]] = {}

    for fallback_rank, row in enumerate(ranking[:8], start=1):
        theme_id = str(row.get("theme_id") or "")
        proxies = HOT_MAINLINE_INDEX_MAP.get(theme_id, [])
        rank = int(row.get("rank") or fallback_rank)
        item = {
            "rank": rank,
            "themeId": theme_id,
            "themeName": str(row.get("theme_name") or row.get("theme") or theme_id),
            "score": row.get("mainline_score_v6"),
            "lifecycle": str(row.get("lifecycle_state_label") or row.get("lifecycle_state") or ""),
            "cycleStage": str(row.get("cycle_stage_label") or row.get("cycle_stage") or ""),
            "proxies": proxies,
        }
        hot_mainlines.append(item)
        for code in proxies:
            hot_by_code.setdefault(code, []).append(
                {
                    "rank": item["rank"],
                    "themeId": item["themeId"],
                    "themeName": item["themeName"],
                    "score": item["score"],
                    "lifecycle": item["lifecycle"],
                    "cycleStage": item["cycleStage"],
                }
            )

    return {
        "source": THEME_LATEST_API_URL,
        "basisDate": str(result.get("basis_date") or ""),
        "generatedAt": str(result.get("generated_at") or result.get("generated_at_iso") or ""),
        "hotMainlines": hot_mainlines,
        "hotByCode": hot_by_code,
        "error": "",
    }


def clip_market_cycle_blocks(blocks: list[dict[str, Any]], start: str, end: str) -> list[dict[str, Any]]:
    result = []
    for block in blocks:
        block_start = compact_trade_date(block.get("start_date"))
        raw_end = block.get("end_date") or end
        block_end = compact_trade_date(raw_end)
        if block_end < start or block_start > end:
            continue
        clipped_start = max(block_start, start)
        clipped_end = min(block_end, end)
        result.append(
            {
                "state": str(block.get("state") or "range"),
                "start_date": normalize_trade_date(clipped_start),
                "end_date": normalize_trade_date(clipped_end),
                "label": str(block.get("short_label") or block.get("label") or block.get("theme_title") or ""),
            }
        )
    return result


def load_market_context(start_date: str, end_date: str) -> dict[str, Any]:
    start = compact_trade_date(start_date)
    end = compact_trade_date(end_date)
    blocks = clip_market_cycle_blocks(MARKET_CYCLE_BLOCKS, start, end)
    source = "Tushare 上证指数行情 + 内置长期牛熊主周期切分"
    try:
        series = frame_to_close_points(fetch_tushare_daily("index_daily", "000001.SH", start, end))
    except Exception:
        series = []

    return {
        "source": source,
        "series": series,
        "cycleBlocks": blocks,
    }


def parse_percent(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("%"):
        text = text[:-1]
    try:
        return float(text)
    except ValueError:
        return None


def fetch_cnindex_daily(index_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    url = "https://www.cnindex.com.cn/market/market/getIndexDailyDataWithDataFormat"
    response = requests.get(
        url,
        params={
            "indexCode": index_code,
            "startDate": normalize_trade_date(start_date),
            "endDate": normalize_trade_date(end_date),
            "frequency": "day",
        },
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": f"https://www.cnindex.com.cn/module/index-detail.html?act_menu=1&indexCode={index_code}",
        },
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 200:
        raise RuntimeError(f"国证官网接口返回异常：{payload.get('message')}")

    rows = payload.get("data", {}).get("data", [])
    parsed: list[dict[str, Any]] = []
    for row in rows:
        if len(row) < 10:
            continue
        parsed.append(
            {
                "trade_date": normalize_trade_date(row[0]),
                "open": row[3],
                "high": row[2],
                "low": row[4],
                "close": row[5],
                "change": row[6],
                "pct_chg": parse_percent(row[7]),
                "amount": row[8],
                "vol": row[9],
            }
        )

    data = pd.DataFrame(parsed)
    if data.empty:
        return data

    for col in ("open", "high", "low", "close", "change", "pct_chg", "amount", "vol"):
        data[col] = pd.to_numeric(data[col], errors="coerce")
    data = data.dropna(subset=["trade_date", "close"])
    data = data.sort_values("trade_date").drop_duplicates("trade_date", keep="last")
    return data.reset_index(drop=True)


def filter_by_date(data: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    start = normalize_trade_date(start_date)
    end = normalize_trade_date(end_date)
    return data[(data["trade_date"] >= start) & (data["trade_date"] <= end)].copy().reset_index(drop=True)


def add_turning_point_flags(data: pd.DataFrame, reversal_threshold: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    data = data.copy().reset_index(drop=True)
    data["turning_high"] = False
    data["turning_low"] = False

    record_columns = ["sequence", "turning_type", "point_type", "trade_date", "close"]
    if data.empty:
        return data, pd.DataFrame(columns=record_columns)

    closes = [float(value) for value in data["close"].to_list()]
    if reversal_threshold <= 0:
        raise ValueError("拐点反转阈值必须大于 0。")

    pivots: list[dict[str, Any]] = []

    def add_pivot(row_index: int, turning_type: str, point_type: str) -> None:
        if pivots and pivots[-1]["row_index"] == row_index:
            return
        pivots.append(
            {
                "row_index": row_index,
                "turning_type": turning_type,
                "point_type": point_type,
                "trade_date": data.at[row_index, "trade_date"],
                "close": closes[row_index],
            }
        )

    trend = 0
    high_idx = 0
    low_idx = 0

    for idx in range(1, len(closes)):
        close = closes[idx]

        if trend == 0:
            if close >= closes[high_idx]:
                high_idx = idx
            if close <= closes[low_idx]:
                low_idx = idx

            has_enough_range = closes[high_idx] / closes[low_idx] - 1 >= reversal_threshold
            if not has_enough_range:
                continue

            if low_idx < high_idx:
                add_pivot(low_idx, "low", "起点低点")
                trend = 1
            else:
                add_pivot(high_idx, "high", "起点高点")
                trend = -1
            continue

        if trend > 0:
            if close >= closes[high_idx]:
                high_idx = idx
                continue
            drawdown = (closes[high_idx] - close) / closes[high_idx]
            if drawdown >= reversal_threshold:
                add_pivot(high_idx, "high", "确认高点")
                trend = -1
                low_idx = idx
            continue

        if close <= closes[low_idx]:
            low_idx = idx
            continue
        rebound = (close - closes[low_idx]) / closes[low_idx]
        if rebound >= reversal_threshold:
            add_pivot(low_idx, "low", "确认低点")
            trend = 1
            high_idx = idx

    if trend == 0:
        add_pivot(0, "flat", "起点/横盘")
    else:
        last_idx = high_idx if trend > 0 else low_idx
        last_type = "high" if trend > 0 else "low"
        add_pivot(last_idx, last_type, "末段高点" if trend > 0 else "末段低点")

    records: list[dict[str, Any]] = []
    for sequence, pivot in enumerate(pivots, start=1):
        row_index = pivot["row_index"]
        if pivot["turning_type"] == "high":
            data.at[row_index, "turning_high"] = True
        elif pivot["turning_type"] == "low":
            data.at[row_index, "turning_low"] = True
        records.append(
            {
                "sequence": sequence,
                "turning_type": pivot["turning_type"],
                "point_type": pivot["point_type"],
                "trade_date": pivot["trade_date"],
                "close": pivot["close"],
            }
        )

    return data, pd.DataFrame(records, columns=record_columns)


def fetch_index_series(code: str, start_date: str, end_date: str, reversal_threshold: float) -> IndexSeries:
    cnindex_code = code.split(".")[0] if code.endswith(".CNI") else DEFAULT_CNINDEX_CODE
    data = fetch_cnindex_daily(cnindex_code, start_date, end_date)
    data = filter_by_date(data, start_date, end_date)
    if data.empty:
        raise RuntimeError(f"{code} 按日期过滤后没有数据。")
    return IndexSeries(
        code=code,
        name=DEFAULT_NAME if code == DEFAULT_CODE else code,
        source="国证官网 getIndexDailyDataWithDataFormat",
        data=data,
        note="拐点按标准收盘价 ZigZag 规则确认：趋势未定时等待从阶段低点到阶段高点的幅度达到阈值以确定初始方向；上升趋势中持续更新最高收盘价，回撤达到阈值后确认高点；下降趋势中持续更新最低收盘价，反弹达到阈值后确认低点；折线按确认后的高低拐点交替连接。",
    )


def write_daily_csv(series: IndexSeries, output_path: Path) -> None:
    cols = [
        col
        for col in (
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "change",
            "pct_chg",
            "vol",
            "amount",
            "turning_high",
            "turning_low",
        )
        if col in series.data.columns
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    series.data[cols].to_csv(output_path, index=False, encoding="utf-8-sig")


def write_record_csv(records: pd.DataFrame, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    records.to_csv(output_path, index=False, encoding="utf-8-sig")


def safe_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def chart_payload(series: IndexSeries, records: pd.DataFrame, y_scale: str, reversal_threshold: float) -> dict[str, Any]:
    data = series.data
    point_columns = [col for col in ("trade_date", "high", "low", "close") if col in data.columns]
    points = data[point_columns].to_dict(orient="records")
    turning_points = records[["sequence", "turning_type", "point_type", "trade_date", "close"]].to_dict(orient="records")
    turning_highs = records[records["turning_type"] == "high"][["sequence", "point_type", "trade_date", "close"]].to_dict(
        orient="records"
    )
    turning_lows = records[records["turning_type"] == "low"][["sequence", "point_type", "trade_date", "close"]].to_dict(
        orient="records"
    )
    first = points[0]
    last = points[-1]
    all_time_high = max(points, key=lambda item: item["close"])
    all_time_low = min(points, key=lambda item: item["close"])
    total_return = (last["close"] / first["close"] - 1) * 100
    return {
        "code": series.code,
        "name": series.name,
        "source": series.source,
        "baseDate": series.base_date,
        "note": series.note,
        "yScale": y_scale,
        "reversalThreshold": reversal_threshold,
        "first": first,
        "last": last,
        "rows": len(points),
        "totalReturn": total_return,
        "allTimeHigh": all_time_high,
        "allTimeLow": all_time_low,
        "turningPointCount": len(turning_points),
        "turningHighCount": len(turning_highs),
        "turningLowCount": len(turning_lows),
        "turningRows": records.to_dict(orient="records"),
        "points": points,
        "turningPoints": turning_points,
        "turningHighs": turning_highs,
        "turningLows": turning_lows,
        "marketContext": load_market_context(first["trade_date"], last["trade_date"]),
    }


def build_mainline_payload(series: IndexSeries) -> dict[str, Any]:
    first = series.data.iloc[0]
    last = series.data.iloc[-1]
    start_date = str(first["trade_date"])
    end_date = str(last["trade_date"])
    hot_context = fetch_latest_theme_context()
    hot_by_code = hot_context.get("hotByCode") or {}
    candidates: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []

    for item in MAINLINE_INDEXES:
        try:
            frame, source = fetch_mainline_candidate(item, series, start_date, end_date)
            points = frame_to_close_points(frame)
            if len(points) < 2:
                failures.append({"code": item["code"], "name": item["name"], "reason": "有效行情不足"})
                continue
            hot_themes = hot_by_code.get(item["code"], [])
            hot_rank = min((int(theme["rank"]) for theme in hot_themes), default=None)
            candidates.append(
                {
                    "group": item["group"],
                    "name": item["name"],
                    "code": item["code"],
                    "source": source,
                    "default": bool(item.get("default")),
                    "returnType": str(item.get("return_type") or "价格指数"),
                    "currency": str(item.get("currency") or "CNY"),
                    "hotRank": hot_rank,
                    "hotThemes": hot_themes,
                    "firstDate": points[0]["trade_date"],
                    "lastDate": points[-1]["trade_date"],
                    "rows": len(points),
                    "series": points,
                }
            )
        except Exception as exc:
            failures.append({"code": item["code"], "name": item["name"], "reason": str(exc)})

    try:
        fx_series = frame_to_close_points(fetch_yahoo_daily("CNY=X", start_date, end_date))
    except Exception as exc:
        fx_series = []
        failures.append({"code": "CNY=X", "name": "美元兑人民币", "reason": str(exc)})

    return {
        "analysis": {
            "firstDate": start_date,
            "lastDate": end_date,
        },
        "candidates": candidates,
        "usdCnySeries": fx_series,
        "failures": failures,
        "hotContext": hot_context,
        "cycleBlocks": load_market_context(start_date, end_date)["cycleBlocks"],
        "sourceNote": "股票与债券优先采用全收益或利息再投资口径；黄金采用上金所现货；海外指数可切换美元或人民币口径。",
    }


def write_mainline_background_html(
    series: IndexSeries, output_path: Path, payload: dict[str, Any] | None = None
) -> None:
    payload = payload or build_mainline_payload(series)
    html_template = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>资产配置研究</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #17202a;
      --muted: #66717f;
      --line: #d8dee8;
      --bg: #f5f7f9;
      --panel: #ffffff;
      --main: #147a61;
      --accent: #2f63b7;
      --warn: #b45f06;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
      background: var(--bg);
      color: var(--ink);
    }
    body.chart-fullscreen {
      overflow: hidden;
    }
    .site-header {
      background: rgba(255, 255, 255, 0.94);
      border-bottom: 1px solid var(--line);
    }
    .site-nav {
      width: min(1560px, calc(100vw - 28px));
      min-height: 50px;
      margin: 0 auto;
      display: flex;
      align-items: center;
      gap: 16px;
      overflow-x: auto;
      white-space: nowrap;
    }
    .brand {
      color: var(--ink);
      font-weight: 800;
      text-decoration: none;
    }
    .site-nav a:not(.brand) {
      color: var(--muted);
      font-size: 13px;
      text-decoration: none;
    }
    .site-nav a.active {
      color: var(--main);
      font-weight: 700;
    }
    main {
      width: min(1560px, calc(100vw - 28px));
      margin: 8px auto 28px;
    }
    main:fullscreen {
      width: 100vw;
      min-height: 100vh;
      margin: 0;
      padding: 18px;
      overflow: auto;
      background: var(--bg);
    }
    main.fullscreen-view {
      position: fixed;
      inset: 0;
      z-index: 1000;
      width: 100vw;
      height: 100vh;
      margin: 0;
      padding: 18px;
      overflow: auto;
      background: var(--bg);
    }
    .page-head {
      display: grid;
      grid-template-columns: auto minmax(0, 1fr);
      gap: 12px;
      align-items: center;
      margin-bottom: 8px;
    }
    h1 {
      margin: 0;
      font-size: 18px;
      line-height: 1.2;
      letter-spacing: 0;
      white-space: nowrap;
    }
    .subtitle {
      margin: 8px 0 0;
      max-width: 920px;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.7;
    }
    .source-note {
      justify-self: end;
      max-width: none;
      padding: 0;
      border: 0;
      border-radius: 0;
      background: transparent;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.4;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .notice {
      display: none;
      margin: 0 0 16px;
      padding: 14px 16px;
      border-left: 4px solid var(--main);
      background: #ffffff;
      border-radius: 8px;
      box-shadow: 0 10px 28px rgba(23, 32, 42, 0.05);
    }
    .notice strong {
      display: block;
      margin-bottom: 4px;
      font-size: 16px;
    }
    .notice p {
      margin: 0;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.7;
    }
    .stats {
      display: none;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 14px;
    }
    .stat {
      min-width: 0;
      padding: 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }
    .stat .label {
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 6px;
    }
    .stat .value {
      display: block;
      font-weight: 800;
      font-size: 22px;
      line-height: 1.2;
    }
    .workspace {
      display: grid;
      grid-template-columns: 340px minmax(0, 1fr);
      gap: 14px;
      align-items: start;
    }
    .workspace > * {
      min-width: 0;
    }
    .controls,
    .chart-panel,
    .table-panel {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: 0 10px 28px rgba(23, 32, 42, 0.05);
    }
    .controls {
      padding: 10px;
      position: sticky;
      top: 58px;
      max-height: calc(100vh - 68px);
      overflow: auto;
    }
    .control-title {
      margin: 0 0 10px;
      font-size: 14px;
    }
    .observation-settings {
      margin-bottom: 12px;
      border-bottom: 1px solid var(--line);
    }
    .observation-settings summary {
      margin: -2px 0 10px;
      padding: 4px 2px 10px;
      color: var(--ink);
      font-size: 14px;
      font-weight: 700;
      cursor: pointer;
      user-select: none;
    }
    .observation-settings:not([open]) summary {
      margin-bottom: 0;
    }
    .control-line {
      display: grid;
      gap: 8px;
      margin-bottom: 14px;
    }
    .control-line label,
    .option-line {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      color: var(--ink);
      font-size: 13px;
      line-height: 1.5;
    }
    select {
      width: 100%;
      min-height: 36px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #ffffff;
      color: var(--ink);
      padding: 0 10px;
      font: inherit;
    }
    input[type="date"] {
      width: 100%;
      min-height: 34px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #ffffff;
      color: var(--ink);
      padding: 0 8px;
      font: inherit;
    }
    .date-range {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin-bottom: 8px;
    }
    .date-range label {
      display: grid;
      gap: 4px;
      color: var(--muted);
      font-size: 11px;
    }
    input[type="checkbox"] {
      width: 16px;
      height: 16px;
      accent-color: var(--main);
      flex: 0 0 auto;
    }
    input[type="range"] {
      width: 100%;
      accent-color: var(--main);
    }
    .range-control {
      display: grid;
      gap: 5px;
      margin-bottom: 12px;
    }
    .range-control label {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      color: var(--ink);
      font-size: 13px;
    }
    .range-control output {
      color: var(--main);
      font-weight: 800;
    }
    .button-row {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
      margin-bottom: 8px;
    }
    button {
      min-height: 34px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #ffffff;
      color: var(--ink);
      font: inherit;
      font-weight: 700;
      cursor: pointer;
    }
    button.primary {
      border-color: var(--main);
      background: var(--main);
      color: #ffffff;
    }
    button:disabled {
      opacity: 0.45;
      cursor: default;
    }
    .picker-group {
      border-top: 1px solid var(--line);
      padding-top: 12px;
      margin-top: 12px;
    }
    .hot-panel {
      border-top: 1px solid var(--line);
      border-bottom: 1px solid var(--line);
      padding: 12px 0;
      margin: 12px 0;
    }
    .hot-list {
      display: grid;
      gap: 8px;
    }
    .hot-item {
      padding: 9px 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcfd;
      font-size: 12px;
      line-height: 1.55;
    }
    .hot-item strong {
      display: block;
      margin-bottom: 3px;
      color: var(--ink);
      font-size: 13px;
    }
    .hot-item small {
      display: block;
      color: var(--muted);
      font-size: 11px;
    }
    .hot-rank,
    .hot-badge {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 18px;
      padding: 0 6px;
      border-radius: 999px;
      background: #fff1df;
      color: #9b5700;
      font-size: 11px;
      font-weight: 800;
      white-space: nowrap;
    }
    .picker-group h3 {
      margin: 0 0 8px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 800;
    }
    .index-option {
      display: grid;
      grid-template-columns: 18px minmax(0, 1fr);
      gap: 8px;
      align-items: center;
      min-height: 30px;
      color: var(--ink);
      font-size: 13px;
    }
    .index-option span {
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .index-option small {
      color: var(--muted);
      font-size: 11px;
    }
    .chart-panel {
      padding: 10px;
    }
    .chart-wrap {
      position: relative;
    }
    .chart-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      margin-bottom: 10px;
      color: var(--muted);
      font-size: 12px;
    }
    .chart-actions {
      display: inline-flex;
      align-items: center;
      gap: 10px;
      white-space: nowrap;
    }
    .chart-actions button {
      min-height: 30px;
      padding: 0 10px;
      font-size: 12px;
    }
    canvas {
      display: block;
      width: 100%;
      height: 720px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
      cursor: crosshair;
    }
    .chart-tooltip {
      position: absolute;
      z-index: 4;
      display: none;
      min-width: 220px;
      max-width: min(420px, calc(100% - 24px));
      max-height: 60%;
      overflow: auto;
      padding: 9px 11px;
      border: 1px solid rgba(23, 32, 42, 0.22);
      border-radius: 6px;
      background: rgba(255, 255, 255, 0.96);
      box-shadow: 0 5px 18px rgba(23, 32, 42, 0.16);
      color: var(--ink);
      font-size: 12px;
      line-height: 1.45;
      pointer-events: none;
    }
    .chart-tooltip strong {
      display: block;
      margin-bottom: 5px;
      font-size: 13px;
    }
    .chart-tooltip-row {
      display: grid;
      grid-template-columns: 9px minmax(90px, 1fr) auto;
      gap: 7px;
      align-items: center;
      white-space: nowrap;
    }
    .chart-tooltip-dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
    }
    main:fullscreen canvas {
      height: max(650px, calc(100vh - 350px));
    }
    main.fullscreen-view canvas {
      height: max(680px, calc(100vh - 350px));
    }
    .legend {
      display: flex;
      flex-wrap: wrap;
      gap: 8px 14px;
      margin-top: 10px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.5;
    }
    .legend span {
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .swatch {
      width: 18px;
      height: 3px;
      border-radius: 999px;
      background: currentColor;
      flex: 0 0 auto;
    }
    .table-panel {
      margin-top: 14px;
      padding: 14px;
      overflow-x: auto;
    }
    .table-panel h2 {
      margin: 0 0 10px;
      font-size: 16px;
    }
    table {
      width: 100%;
      min-width: 1040px;
      border-collapse: collapse;
      font-size: 13px;
    }
    th,
    td {
      padding: 9px 8px;
      border-bottom: 1px solid var(--line);
      text-align: right;
      white-space: nowrap;
    }
    th:first-child,
    td:first-child,
    th:nth-child(2),
    td:nth-child(2) {
      text-align: left;
    }
    th {
      color: var(--muted);
      font-size: 12px;
      font-weight: 800;
    }
    th.sortable {
      cursor: pointer;
      user-select: none;
      color: #46505c;
    }
    th.sortable:hover,
    th.sortable.active {
      color: var(--ink);
      background: #f3f6fa;
    }
    .sort-mark {
      display: inline-block;
      min-width: 12px;
      margin-left: 4px;
      color: var(--accent);
      font-size: 11px;
    }
    .positive { color: #b03a2e; }
    .negative { color: #237447; }
    .empty {
      padding: 12px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.7;
    }
    .drawdown-list {
      min-width: 150px;
      white-space: normal;
      line-height: 1.65;
    }
    .drawdown-list b {
      margin-right: 8px;
    }
    .analytics-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
      margin-top: 14px;
    }
    .analysis-panel {
      min-width: 0;
      padding: 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: 0 10px 28px rgba(23, 32, 42, 0.05);
    }
    .analysis-panel.correlation-panel {
      grid-column: 1 / -1;
    }
    .analysis-panel.portfolio-panel {
      grid-column: 1 / -1;
    }
    .analysis-panel h2 {
      margin: 0 0 4px;
      font-size: 16px;
    }
    .panel-note {
      margin: 0 0 12px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.5;
    }
    .method-help {
      position: relative;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 18px;
      height: 18px;
      margin-left: 5px;
      border: 1px solid var(--line);
      border-radius: 50%;
      color: var(--muted);
      font-size: 12px;
      cursor: help;
      vertical-align: middle;
    }
    .method-help::after {
      position: absolute;
      z-index: 8;
      top: 24px;
      left: 0;
      display: none;
      width: min(420px, 70vw);
      padding: 10px 12px;
      border: 1px solid rgba(23, 32, 42, 0.22);
      border-radius: 6px;
      background: #ffffff;
      box-shadow: 0 6px 20px rgba(23, 32, 42, 0.18);
      color: #46505c;
      content: attr(data-tooltip);
      font-size: 12px;
      font-weight: 400;
      line-height: 1.65;
      white-space: normal;
    }
    .method-help:hover::after,
    .method-help:focus::after {
      display: block;
    }
    .matrix-wrap { overflow: auto; }
    .correlation-table {
      width: auto;
      min-width: 100%;
      table-layout: fixed;
    }
    .correlation-table th,
    .correlation-table td {
      width: 64px;
      min-width: 64px;
      height: 42px;
      padding: 5px;
      text-align: center;
      white-space: normal;
      line-height: 1.25;
    }
    .correlation-table th:first-child,
    .correlation-table td:first-child {
      position: sticky;
      left: 0;
      z-index: 1;
      width: 150px;
      min-width: 150px;
      background: #ffffff;
      text-align: left;
    }
    .portfolio-block + .portfolio-block {
      margin-top: 16px;
      padding-top: 14px;
      border-top: 1px solid var(--line);
    }
    .portfolio-title {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 8px;
      color: var(--ink);
      font-size: 13px;
      font-weight: 800;
    }
    .weight-stack {
      display: flex;
      width: 100%;
      height: 18px;
      overflow: hidden;
      border: 1px solid var(--line);
    }
    .weight-segment {
      min-width: 1px;
      height: 100%;
    }
    .weight-list {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 7px 12px;
      margin-top: 10px;
    }
    .weight-item {
      display: grid;
      grid-template-columns: 9px minmax(0, 1fr) auto;
      gap: 6px;
      align-items: center;
      min-width: 0;
      color: var(--muted);
      font-size: 12px;
    }
    .weight-item i {
      width: 8px;
      height: 8px;
    }
    .weight-item span {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    @media (max-width: 980px) {
      .page-head {
        grid-template-columns: 1fr;
      }
      .source-note {
        justify-self: stretch;
      }
      .stats {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
      .workspace {
        grid-template-columns: 1fr;
      }
      .controls {
        position: static;
        max-height: none;
      }
      .chart-head {
        align-items: flex-start;
        flex-direction: column;
      }
      .chart-actions {
        flex-wrap: wrap;
        white-space: normal;
      }
      canvas {
        height: 520px;
      }
      .analytics-grid {
        grid-template-columns: 1fr;
      }
      .analysis-panel.correlation-panel {
        grid-column: auto;
      }
      .weight-list {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body>
<div data-myinvest-header></div>
<script src="https://invest.okbbc.com/header.js" charset="utf-8" defer></script>
<header class="site-header">
  <nav class="site-nav" aria-label="研究入口">
    <a class="brand" href="/index.html">研究入口</a>
    <a href="/480092_CNI_new_high_low.html">Log回归通道</a>
    <a href="/480092_CNI_zigzag_strategy.html">ZigZag拐点策略</a>
    <a class="active" href="/480092_CNI_mainline_background.html">资产配置研究</a>
    <a href="/480092_CNI_alpha.html">资产 Alpha 研究</a>
    <a href="/480092_CNI_strategy_portfolio.html">策略组合研究</a>
    <a href="/480092_CNI_daily.csv">日线数据</a>
    <a href="/480092_CNI_record_points.csv">拐点记录</a>
  </nav>
</header>
<main id="pageRoot">
  <header class="page-head">
    <h1>资产配置研究</h1>
    <div class="source-note" id="sourceNote"></div>
  </header>

  <section class="stats" id="summaryCards" aria-label="概览"></section>

  <section class="workspace">
    <aside class="controls" aria-label="资产选择">
      <details class="observation-settings">
        <summary>观察设置</summary>
      <div class="control-line">
        <label for="displayMode">显示方式</label>
        <select id="displayMode">
          <option value="normalized">归一化走势</option>
          <option value="relative">相对比较基准</option>
        </select>
      </div>
      <div class="control-line">
        <label for="benchmarkSelect">比较基准</label>
        <select id="benchmarkSelect"></select>
      </div>
      <div class="control-line">
        <label for="currencyMode">海外指数口径</label>
        <select id="currencyMode">
          <option value="cny">人民币</option>
          <option value="usd">美元</option>
        </select>
      </div>
      <div class="range-control">
        <label>虚拟组合</label>
        <label class="option-line"><span>等权</span><input id="equalWeightToggle" type="checkbox"></label>
        <label class="option-line"><span>风险平价</span><input id="riskParityToggle" type="checkbox"></label>
        <label class="option-line"><span>分组风险平价</span><input id="groupRiskParityToggle" type="checkbox" checked></label>
      </div>
      <div class="date-range">
        <label>开始日期<input id="startDateInput" type="date"></label>
        <label>结束日期<input id="endDateInput" type="date"></label>
      </div>
      <div class="range-control">
        <label for="drawdownThreshold">回撤标注阈值 <output id="drawdownThresholdValue">15%</output></label>
        <input id="drawdownThreshold" type="range" min="5" max="70" step="1" value="15">
      </div>
      <label class="option-line"><span>牛熊背景</span><input id="cycleToggle" type="checkbox" checked></label>
      <label class="option-line"><span>阶段标签</span><input id="labelToggle" type="checkbox" checked></label>
      <div class="button-row">
        <button class="primary" id="selectDefault" type="button">默认沪深300</button>
        <button id="resetRange" type="button">全部时间</button>
        <button id="clearSelection" type="button">清空</button>
      </div>
      </details>
      <h2 class="control-title">资产与主线</h2>
      <div id="indexPicker"></div>
    </aside>

    <div>
      <section class="chart-panel">
        <div class="chart-head">
          <span id="chartTitle"></span>
          <span class="chart-actions"><span>红色背景为牛市，绿色背景为熊市</span><button id="restoreChartRange" type="button">恢复全区间</button><button id="fullscreenButton" type="button">全屏</button></span>
        </div>
        <div class="chart-wrap">
          <canvas id="mainlineChart" aria-label="资产配置研究图"></canvas>
          <div class="chart-tooltip" id="chartTooltip" role="status"></div>
        </div>
        <div class="legend" id="legend"></div>
      </section>

      <section class="table-panel">
        <h2 id="fullTableTitle">所选区间排序</h2>
        <div id="fullTable"></div>
      </section>

      <section class="analytics-grid" aria-label="组合分析">
        <section class="analysis-panel correlation-panel">
          <h2>日收益相关性矩阵</h2>
          <p class="panel-note">按所选区间的共同交易日进行两两计算，至少需要20个共同收益样本。</p>
          <div class="matrix-wrap" id="correlationMatrix"></div>
        </section>
        <section class="analysis-panel portfolio-panel">
          <h2>虚拟组合资产比例 <span class="method-help" tabindex="0" aria-label="查看计算方法" data-tooltip="日收益率为 P(t) / P(t-1) - 1，优先采用全收益指数。季度等权在每季度首个交易日令各资产权重为 1/N。普通风险平价按调仓日前60个交易日波动率的倒数直接分配。分组风险平价先在每个风险组内部按波动率倒数分配，再用形成的组内组合60日波动率倒数分配组间权重，最终资产权重=组权重×组内权重；相似资产不会因数量增加而重复占用多份组间风险预算。所有方式均按季度再平衡，不使用当日及未来数据，季度内权重随涨跌自然漂移。该方法未使用完整协方差矩阵，不等同于 ERC 模型。">i</span></h2>
          <p class="panel-note">显示区间末日实际权重；季度调仓后，权重随资产涨跌自然漂移。</p>
          <div id="portfolioWeights"></div>
        </section>
      </section>
    </div>
  </section>
</main>

<script>
const payload = __PAYLOAD__;
const pageRoot = document.getElementById("pageRoot");
const canvas = document.getElementById("mainlineChart");
const ctx = canvas.getContext("2d");
const chartTooltip = document.getElementById("chartTooltip");
const picker = document.getElementById("indexPicker");
const legend = document.getElementById("legend");
const displayMode = document.getElementById("displayMode");
const benchmarkSelect = document.getElementById("benchmarkSelect");
const currencyMode = document.getElementById("currencyMode");
const equalWeightToggle = document.getElementById("equalWeightToggle");
const riskParityToggle = document.getElementById("riskParityToggle");
const groupRiskParityToggle = document.getElementById("groupRiskParityToggle");
const startDateInput = document.getElementById("startDateInput");
const endDateInput = document.getElementById("endDateInput");
const drawdownThreshold = document.getElementById("drawdownThreshold");
const drawdownThresholdValue = document.getElementById("drawdownThresholdValue");
const cycleToggle = document.getElementById("cycleToggle");
const labelToggle = document.getElementById("labelToggle");
const chartTitle = document.getElementById("chartTitle");
const fullTable = document.getElementById("fullTable");
const fullTableTitle = document.getElementById("fullTableTitle");
const summaryCards = document.getElementById("summaryCards");
const sourceNote = document.getElementById("sourceNote");
const fullscreenButton = document.getElementById("fullscreenButton");
const restoreChartRange = document.getElementById("restoreChartRange");
const correlationMatrix = document.getElementById("correlationMatrix");
const portfolioWeights = document.getElementById("portfolioWeights");
const colors = ["#1565c0", "#d84315", "#2e7d32", "#7b1fa2", "#c69200", "#00838f", "#c62828", "#5d4037", "#3949ab", "#558b2f", "#ad1457", "#00695c", "#ef6c00", "#6a1b9a", "#0277bd", "#9e9d24", "#4527a0", "#00897b", "#e53935", "#7cb342", "#8e24aa", "#039be5", "#f4511e", "#43a047"];
const candidateRaw = new Map(payload.candidates.map((item) => [item.code, normalizeRaw(item.series)]));
const dateList = Array.from(new Set(payload.candidates.flatMap((item) => (item.series || []).map((point) => point.trade_date)))).sort();
const fxRaw = normalizeRaw(payload.usdCnySeries || []);
const fxByDate = new Map(fxRaw.map((point) => [point.date, point.close]));
let viewStartDate = payload.analysis.firstDate;
let viewEndDate = payload.analysis.lastDate;
let dragStartX = null;
let dragCurrentX = null;
const equalWeightCode = "EQUAL_WEIGHT_VIRTUAL";
const riskParityCode = "RISK_PARITY_VIRTUAL";
const groupRiskParityCode = "GROUP_RISK_PARITY_VIRTUAL";
const fullTableSort = { key: "annual", direction: "desc" };
let hoverPoint = null;
let chartGeometry = null;

function normalizeRaw(series) {
  return (series || [])
    .map((point) => ({ date: point.trade_date, close: Number(point.close) }))
    .filter((point) => point.date && Number.isFinite(point.close) && point.close > 0)
    .sort((left, right) => left.date.localeCompare(right.date));
}

function normalizeSeries(raw) {
  if (!raw.length) return [];
  const base = raw[0].close;
  return raw.map((point) => ({ date: point.date, value: point.close / base, close: point.close }));
}

function pointWithIndex(point, indexMap) {
  const index = indexMap.get(point.date);
  if (index === undefined) return null;
  return { ...point, index };
}

function indexForDate(date, preferEnd = false, dates = dateList) {
  let low = 0;
  let high = dates.length;
  while (low < high) {
    const mid = Math.floor((low + high) / 2);
    if (dates[mid] < date) low = mid + 1;
    else high = mid;
  }
  if (dates[low] === date) return low;
  if (preferEnd) return Math.max(0, low - 1);
  return Math.min(dates.length - 1, low);
}

function visibleDates() {
  return dateList.filter((date) => date >= viewStartDate && date <= viewEndDate);
}

function fxForDate(date) {
  if (fxByDate.has(date)) return fxByDate.get(date);
  const index = indexForDate(date, true, fxRaw.map((point) => point.date));
  return fxRaw[index] ? fxRaw[index].close : NaN;
}

function fmtPct(value, digits = 1) {
  if (!Number.isFinite(value)) return "-";
  const text = `${(value * 100).toFixed(digits)}%`;
  if (value > 0) return `<span class="positive">+${text}</span>`;
  if (value < 0) return `<span class="negative">${text}</span>`;
  return text;
}

function fmtPlainPct(value, digits = 1) {
  if (!Number.isFinite(value)) return "-";
  return `${value > 0 ? "+" : ""}${(value * 100).toFixed(digits)}%`;
}

function fmtDateRange(startDate, endDate) {
  if (!startDate || !endDate) return "-";
  if (startDate === endDate) return startDate;
  return `${startDate} 至 ${endDate}`;
}

function fmtCommonMaxDrawdownRange(stats) {
  if (!stats || !stats.commonMaxDrawdownRange) return "-";
  return `${fmtPlainPct(stats.commonMaxDrawdownRange.low)} 至 ${fmtPlainPct(stats.commonMaxDrawdownRange.high)}`;
}

function fmtHistoricalDrawdowns(events) {
  if (!events || !events.length) return "-";
  return `<div class="drawdown-list" title="按发生顺序列出所选区间内超过阈值的各次最大回撤">${events.map((event) => `<b>${(event.drawdown * 100).toFixed(1)}%</b>`).join(" ")}</div>`;
}

function fmtRatio(value) {
  if (!Number.isFinite(value)) return "-";
  return value.toFixed(2);
}

function fmtMultiple(value) {
  if (!Number.isFinite(value)) return "-";
  return `${value.toFixed(2)}x`;
}

function dateDiffDays(start, end) {
  return Math.max(1, (new Date(end).getTime() - new Date(start).getTime()) / 86400000);
}

function maxDrawdownValue(points) {
  if (points.length < 2) return NaN;
  let peak = points[0].close;
  let maxDrawdown = 0;
  for (const point of points) {
    if (point.close > peak) peak = point.close;
    const drawdown = point.close / peak - 1;
    if (drawdown < maxDrawdown) maxDrawdown = drawdown;
  }
  return maxDrawdown;
}

function percentile(sortedValues, ratio) {
  if (!sortedValues.length) return NaN;
  const position = (sortedValues.length - 1) * ratio;
  const low = Math.floor(position);
  const high = Math.ceil(position);
  if (low === high) return sortedValues[low];
  return sortedValues[low] + (sortedValues[high] - sortedValues[low]) * (position - low);
}

function commonMaxDrawdownRange(points) {
  const windowDays = 365;
  const minWindowDays = 250;
  const values = [];
  let startIndex = 0;
  for (let endIndex = 1; endIndex < points.length; endIndex++) {
    while (startIndex < endIndex && dateDiffDays(points[startIndex].date, points[endIndex].date) > windowDays) {
      startIndex += 1;
    }
    if (dateDiffDays(points[startIndex].date, points[endIndex].date) < minWindowDays) continue;
    const value = maxDrawdownValue(points.slice(startIndex, endIndex + 1));
    if (Number.isFinite(value)) values.push(value);
  }
  if (!values.length) return null;
  values.sort((left, right) => left - right);
  const low = percentile(values, 0.25);
  const high = percentile(values, 0.75);
  return { low, high, mid: (low + high) / 2, count: values.length };
}

function segmentStats(raw, startDate, endDate, includeCommonDrawdown = false) {
  const points = raw.filter((point) => point.date >= startDate && point.date <= endDate);
  if (points.length < 2) return null;
  const first = points[0];
  const last = points[points.length - 1];
  const ratio = last.close / first.close;
  const days = dateDiffDays(first.date, last.date);
  let peak = points[0].close;
  let peakDate = points[0].date;
  let maxDrawdown = 0;
  let maxDrawdownStartDate = points[0].date;
  let maxDrawdownEndDate = points[0].date;
  let currentPeak = points[0].close;
  let currentPeakDate = points[0].date;
  for (const point of points) {
    if (point.close > peak) {
      peak = point.close;
      peakDate = point.date;
    }
    const drawdown = point.close / peak - 1;
    if (drawdown < maxDrawdown) {
      maxDrawdown = drawdown;
      maxDrawdownStartDate = peakDate;
      maxDrawdownEndDate = point.date;
    }
    if (point.close >= currentPeak) {
      currentPeak = point.close;
      currentPeakDate = point.date;
    }
  }
  const currentDrawdown = last.close / currentPeak - 1;
  const annual = Math.pow(ratio, 365 / days) - 1;
  const dailyReturns = [];
  for (let index = 1; index < points.length; index++) {
    const dailyReturn = points[index].close / points[index - 1].close - 1;
    if (Number.isFinite(dailyReturn)) dailyReturns.push(dailyReturn);
  }
  const meanDaily = dailyReturns.length ? dailyReturns.reduce((sum, value) => sum + value, 0) / dailyReturns.length : NaN;
  const variance = dailyReturns.length > 1
    ? dailyReturns.reduce((sum, value) => sum + Math.pow(value - meanDaily, 2), 0) / (dailyReturns.length - 1)
    : NaN;
  const dailyVolatility = Math.sqrt(variance);
  const volatility = Number.isFinite(dailyVolatility) ? dailyVolatility * Math.sqrt(252) : NaN;
  const sharpe = Number.isFinite(dailyVolatility) && dailyVolatility > 0 ? meanDaily / dailyVolatility * Math.sqrt(252) : NaN;
  const calmar = maxDrawdown < 0 ? annual / Math.abs(maxDrawdown) : NaN;
  const commonRange = includeCommonDrawdown ? commonMaxDrawdownRange(points) : null;
  return {
    firstDate: first.date,
    lastDate: last.date,
    total: ratio - 1,
    annual,
    volatility,
    sharpe,
    calmar,
    maxDrawdown,
    maxDrawdownStartDate,
    maxDrawdownEndDate,
    currentDrawdown,
    currentDrawdownStartDate: currentPeakDate,
    currentDrawdownEndDate: last.date,
    commonMaxDrawdownRange: commonRange,
    days,
  };
}

function selectedCandidates() {
  const checked = new Set(
    Array.from(document.querySelectorAll(".index-check:checked")).map((input) => input.value)
  );
  return payload.candidates.filter((item) => checked.has(item.code));
}

function assetRaw(asset) {
  if (asset.synthetic) return asset.series || [];
  let raw = candidateRaw.get(asset.code) || [];
  if (asset.currency === "USD" && currencyMode.value === "cny") {
    raw = raw.map((point) => {
      const fx = fxForDate(point.date);
      return { ...point, close: Number.isFinite(fx) ? point.close * fx : point.close };
    });
  }
  return raw;
}

function quarterKey(date) {
  const month = Number(date.slice(5, 7));
  return `${date.slice(0, 4)}-Q${Math.floor((month - 1) / 3) + 1}`;
}

function buildEqualWeightRaw(assets = selectedCandidates()) {
  if (assets.length < 2) return [];
  const dates = visibleDates();
  const maps = assets.map((asset) => new Map(assetRaw(asset).map((point) => [point.date, point.close])));
  const lastValues = Array(assets.length).fill(undefined);
  let previousValues = null;
  let weights = assets.map(() => 1 / assets.length);
  let lastRebalanceQuarter = null;
  let level = 1000;
  const result = [];
  for (const date of dates) {
    maps.forEach((map, index) => {
      if (map.has(date)) lastValues[index] = map.get(date);
    });
    if (lastValues.some((value) => !Number.isFinite(value) || value <= 0)) continue;
    if (previousValues === null) {
      result.push({ date, close: level });
      previousValues = [...lastValues];
      lastRebalanceQuarter = quarterKey(date);
      continue;
    }
    const dailyReturns = lastValues.map((value, index) => value / previousValues[index] - 1);
    const quarter = quarterKey(date);
    if (quarter !== lastRebalanceQuarter) {
      weights = assets.map(() => 1 / assets.length);
      lastRebalanceQuarter = quarter;
    }
    const portfolioReturn = dailyReturns.reduce((sum, value, index) => sum + value * weights[index], 0);
    level *= 1 + portfolioReturn;
    result.push({ date, close: level });
    const growth = 1 + portfolioReturn;
    if (growth > 0) weights = weights.map((weight, index) => weight * (1 + dailyReturns[index]) / growth);
    previousValues = [...lastValues];
  }
  result.currentWeights = [...weights];
  result.lastRebalanceQuarter = lastRebalanceQuarter;
  return result;
}

function sampleVolatility(values) {
  if (values.length < 2) return NaN;
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  const variance = values.reduce((sum, value) => sum + Math.pow(value - mean, 2), 0) / (values.length - 1);
  return Math.sqrt(variance);
}

function assetRiskGroup(asset) {
  const codeGroups = {
    "480092.CNI": "策略防御",
    "H21052.CSI": "策略防御",
    "H00922.CSI": "策略防御",
    "CN2296.CNI": "策略成长",
    "H20319.CSI": "传媒游戏",
    "H20901.CSI": "传媒游戏",
    "H00997.CSI": "消费",
    "H20539.CSI": "消费",
    "H00991.CSI": "医药",
    "921409.CSI": "医药",
    "H20180.CSI": "金融",
    "H40105.CSI": "金融",
    "H20035.CSI": "金融",
    "931775CNY01.CSI": "地产",
    "H20771.CSI": "新能源",
    "H20229.CSI": "军工",
    "Au99.99": "黄金",
    "931080CNY050.CSI": "长期国债",
    "159980.SZ": "工业金属商品",
    "159981.SZ": "能源化工商品",
  };
  if (codeGroups[asset.code]) return codeGroups[asset.code];
  if (asset.group === "A股宽基") return "A股宽基";
  if ((asset.group || "").startsWith("第一主线")) return "AI科技与自主可控";
  if ((asset.group || "").startsWith("第二主线")) return "资源周期与盈利修复";
  if ((asset.group || "").startsWith("第三主线")) return "电力能源与先进制造";
  if (asset.group === "海外市场") return "海外股票";
  return asset.group || asset.name;
}

function groupedInitialWeights(assets) {
  const groups = new Map();
  assets.forEach((asset, index) => {
    const group = assetRiskGroup(asset);
    if (!groups.has(group)) groups.set(group, []);
    groups.get(group).push(index);
  });
  const groupWeight = 1 / groups.size;
  const weights = assets.map(() => 0);
  for (const indexes of groups.values()) {
    indexes.forEach((index) => { weights[index] = groupWeight / indexes.length; });
  }
  return weights;
}

function groupedRiskParityWeights(assets, histories) {
  const groups = new Map();
  assets.forEach((asset, index) => {
    const group = assetRiskGroup(asset);
    if (!groups.has(group)) groups.set(group, []);
    groups.get(group).push(index);
  });
  const groupModels = [];
  for (const [name, indexes] of groups) {
    const inverseVolatilities = indexes.map((index) => {
      const volatility = sampleVolatility(histories[index].slice(-60));
      return Number.isFinite(volatility) && volatility > 1e-8 ? 1 / volatility : 0;
    });
    const inverseTotal = inverseVolatilities.reduce((sum, value) => sum + value, 0);
    if (!(inverseTotal > 0)) return null;
    const internalWeights = inverseVolatilities.map((value) => value / inverseTotal);
    const groupReturns = Array.from({ length: 60 }, (_, offset) => (
      indexes.reduce((sum, index, position) => sum + internalWeights[position] * histories[index].slice(-60)[offset], 0)
    ));
    const groupVolatility = sampleVolatility(groupReturns);
    if (!Number.isFinite(groupVolatility) || groupVolatility <= 1e-8) return null;
    groupModels.push({ name, indexes, internalWeights, inverseVolatility: 1 / groupVolatility });
  }
  const groupInverseTotal = groupModels.reduce((sum, group) => sum + group.inverseVolatility, 0);
  if (!(groupInverseTotal > 0)) return null;
  const weights = assets.map(() => 0);
  groupModels.forEach((group) => {
    const groupWeight = group.inverseVolatility / groupInverseTotal;
    group.indexes.forEach((index, position) => {
      weights[index] = groupWeight * group.internalWeights[position];
    });
  });
  return weights;
}

function buildRiskParityRaw(assets = selectedCandidates()) {
  if (assets.length < 2) return [];
  const dates = visibleDates();
  const maps = assets.map((asset) => new Map(assetRaw(asset).map((point) => [point.date, point.close])));
  const lastValues = Array(assets.length).fill(undefined);
  const histories = assets.map(() => []);
  let previousValues = null;
  let weights = assets.map(() => 1 / assets.length);
  let lastRebalanceQuarter = null;
  let level = 1000;
  const result = [];
  for (const date of dates) {
    maps.forEach((map, index) => {
      if (map.has(date)) lastValues[index] = map.get(date);
    });
    if (lastValues.some((value) => !Number.isFinite(value) || value <= 0)) continue;
    if (previousValues === null) {
      result.push({ date, close: level });
      previousValues = [...lastValues];
      lastRebalanceQuarter = quarterKey(date);
      continue;
    }
    const dailyReturns = lastValues.map((value, index) => value / previousValues[index] - 1);
    const quarter = quarterKey(date);
    if (quarter !== lastRebalanceQuarter) {
      if (histories.every((history) => history.length >= 60)) {
        const inverseVolatilities = histories.map((history) => {
          const volatility = sampleVolatility(history.slice(-60));
          return Number.isFinite(volatility) && volatility > 1e-8 ? 1 / volatility : 0;
        });
        const totalInverseVolatility = inverseVolatilities.reduce((sum, value) => sum + value, 0);
        if (totalInverseVolatility > 0) {
          weights = inverseVolatilities.map((value) => value / totalInverseVolatility);
        }
      }
      lastRebalanceQuarter = quarter;
    }
    const portfolioReturn = dailyReturns.reduce((sum, value, index) => sum + value * weights[index], 0);
    level *= 1 + portfolioReturn;
    result.push({ date, close: level });
    const growth = 1 + portfolioReturn;
    if (growth > 0) weights = weights.map((weight, index) => weight * (1 + dailyReturns[index]) / growth);
    dailyReturns.forEach((value, index) => {
      histories[index].push(value);
      if (histories[index].length > 60) histories[index].shift();
    });
    previousValues = [...lastValues];
  }
  result.currentWeights = [...weights];
  result.lastRebalanceQuarter = lastRebalanceQuarter;
  return result;
}

function buildGroupedRiskParityRaw(assets = selectedCandidates()) {
  if (assets.length < 2) return [];
  const dates = visibleDates();
  const maps = assets.map((asset) => new Map(assetRaw(asset).map((point) => [point.date, point.close])));
  const lastValues = Array(assets.length).fill(undefined);
  const histories = assets.map(() => []);
  let previousValues = null;
  let weights = groupedInitialWeights(assets);
  let lastRebalanceQuarter = null;
  let level = 1000;
  const result = [];
  for (const date of dates) {
    maps.forEach((map, index) => {
      if (map.has(date)) lastValues[index] = map.get(date);
    });
    if (lastValues.some((value) => !Number.isFinite(value) || value <= 0)) continue;
    if (previousValues === null) {
      result.push({ date, close: level });
      previousValues = [...lastValues];
      lastRebalanceQuarter = quarterKey(date);
      continue;
    }
    const dailyReturns = lastValues.map((value, index) => value / previousValues[index] - 1);
    const quarter = quarterKey(date);
    if (quarter !== lastRebalanceQuarter) {
      if (histories.every((history) => history.length >= 60)) {
        weights = groupedRiskParityWeights(assets, histories) || weights;
      }
      lastRebalanceQuarter = quarter;
    }
    const portfolioReturn = dailyReturns.reduce((sum, value, index) => sum + value * weights[index], 0);
    level *= 1 + portfolioReturn;
    result.push({ date, close: level });
    const growth = 1 + portfolioReturn;
    if (growth > 0) weights = weights.map((weight, index) => weight * (1 + dailyReturns[index]) / growth);
    dailyReturns.forEach((value, index) => {
      histories[index].push(value);
      if (histories[index].length > 60) histories[index].shift();
    });
    previousValues = [...lastValues];
  }
  result.currentWeights = [...weights];
  result.lastRebalanceQuarter = lastRebalanceQuarter;
  return result;
}

function selectedAssets() {
  const baseAssets = selectedCandidates();
  const assets = [...baseAssets];
  const equalWeightSeries = equalWeightToggle.checked ? buildEqualWeightRaw(baseAssets) : [];
  const riskParitySeries = riskParityToggle.checked ? buildRiskParityRaw(baseAssets) : [];
  const groupRiskParitySeries = groupRiskParityToggle.checked ? buildGroupedRiskParityRaw(baseAssets) : [];
  if (equalWeightSeries.length >= 2) {
    assets.push({
      group: "虚拟组合",
      name: "所选指数季度等权",
      code: equalWeightCode,
      returnType: "季度等权再平衡",
      currency: currencyMode.value === "cny" ? "CNY" : "混合本币",
      synthetic: true,
      series: equalWeightSeries,
      components: baseAssets.map((asset, index) => ({ asset, weight: equalWeightSeries.currentWeights[index] })),
      lastRebalanceQuarter: equalWeightSeries.lastRebalanceQuarter,
    });
  }
  if (riskParitySeries.length >= 2) {
    assets.push({
      group: "虚拟组合",
      name: "所选指数风险平价",
      code: riskParityCode,
      returnType: "60日波动率倒数/季度再平衡",
      currency: currencyMode.value === "cny" ? "CNY" : "混合本币",
      synthetic: true,
      series: riskParitySeries,
      components: baseAssets.map((asset, index) => ({ asset, weight: riskParitySeries.currentWeights[index] })),
      lastRebalanceQuarter: riskParitySeries.lastRebalanceQuarter,
    });
  }
  if (groupRiskParitySeries.length >= 2) {
    assets.push({
      group: "虚拟组合",
      name: "所选指数分组风险平价",
      code: groupRiskParityCode,
      returnType: "两层60日波动率倒数/季度再平衡",
      currency: currencyMode.value === "cny" ? "CNY" : "混合本币",
      synthetic: true,
      series: groupRiskParitySeries,
      components: baseAssets.map((asset, index) => ({ asset, weight: groupRiskParitySeries.currentWeights[index], riskGroup: assetRiskGroup(asset) })),
      lastRebalanceQuarter: groupRiskParitySeries.lastRebalanceQuarter,
    });
  }
  return assets;
}

function drawdownEvents(raw, threshold = Number(drawdownThreshold.value) / 100) {
  const points = raw.filter((point) => point.date >= viewStartDate && point.date <= viewEndDate && point.close > 0);
  if (points.length < 2) return [];
  const events = [];
  let peak = points[0];
  let trough = points[0];
  let inDrawdown = false;
  const closeEvent = (recoveryDate = null) => {
    const drawdown = trough.close / peak.close - 1;
    if (inDrawdown && drawdown <= -threshold) {
      events.push({
        peakDate: peak.date,
        peakClose: peak.close,
        troughDate: trough.date,
        troughClose: trough.close,
        recoveryDate,
        drawdown,
      });
    }
  };
  for (let index = 1; index < points.length; index++) {
    const point = points[index];
    if (point.close >= peak.close) {
      closeEvent(point.date);
      peak = point;
      trough = point;
      inDrawdown = false;
    } else {
      inDrawdown = true;
      if (point.close < trough.close) trough = point;
    }
  }
  closeEvent(null);
  return events;
}

function latestDrawdownRecovery(raw) {
  const points = raw.filter((point) => point.date >= viewStartDate && point.date <= viewEndDate && point.close > 0);
  const events = drawdownEvents(raw);
  if (!points.length || !events.length) return null;
  const event = events[events.length - 1];
  const current = points[points.length - 1];
  return {
    drawdown: event.drawdown,
    rebound: current.close / event.troughClose - 1,
    peakDate: event.peakDate,
    troughDate: event.troughDate,
    currentDate: current.date,
  };
}

function candidateNameForCode(code) {
  const item = payload.candidates.find((candidate) => candidate.code === code);
  return item ? `${item.name}` : code;
}

function renderHotMainlines() {
  const hot = (payload.hotContext && payload.hotContext.hotMainlines) || [];
  if (!hot.length) {
    return;
  }
}

function renderPicker() {
  const groups = new Map();
  for (const item of payload.candidates) {
    if (!groups.has(item.group)) groups.set(item.group, []);
    groups.get(item.group).push(item);
  }
  const groupOrder = [
    "A股策略",
    "A股宽基",
    "海外市场",
    "大类资产",
    "第一主线：AI科技与自主可控",
    "第二主线：再通胀、资源品和反内卷盈利修复",
    "第三主线：电力能源与先进制造",
    "历史主线",
  ];
  const groupRank = new Map(groupOrder.map((group, index) => [group, index]));
  const orderedGroups = Array.from(groups.entries()).sort((left, right) => (
    (groupRank.get(left[0]) ?? groupOrder.length) - (groupRank.get(right[0]) ?? groupOrder.length)
  ));
  picker.innerHTML = orderedGroups.map(([group, items]) => {
    const options = items.map((item) => `
      <label class="index-option" title="${item.name} ${item.code}">
        <input class="index-check" type="checkbox" value="${item.code}" ${item.default ? "checked" : ""}>
        <span>${item.name} <small>${item.code}</small></span>
      </label>
    `).join("");
    return `<div class="picker-group"><h3>${group}</h3>${options}</div>`;
  }).join("");
  for (const input of document.querySelectorAll(".index-check")) {
    input.addEventListener("change", update);
  }
}

function renderBenchmarkOptions() {
  const previous = benchmarkSelect.value || "H00300.CSI";
  const selected = selectedCandidates();
  benchmarkSelect.innerHTML = selected.map((item) => `<option value="${item.code}">${item.name}</option>`).join("");
  if (selected.some((item) => item.code === previous)) benchmarkSelect.value = previous;
  else if (selected.some((item) => item.code === "H00300.CSI")) benchmarkSelect.value = "H00300.CSI";
  else if (selected.length) benchmarkSelect.value = selected[0].code;
}

function resizeCanvas() {
  const rect = canvas.getBoundingClientRect();
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.max(1, Math.floor(rect.width * ratio));
  canvas.height = Math.max(1, Math.floor(rect.height * ratio));
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  return { width: rect.width, height: rect.height };
}

function dynamicColor(index) {
  if (index < colors.length) return colors[index];
  const hue = Math.round((index * 137.508) % 360);
  return `hsl(${hue} 68% ${index % 2 ? 38 : 48}%)`;
}

function syntheticColor(code) {
  if (code === equalWeightCode) return "#111827";
  if (code === riskParityCode) return "#374151";
  if (code === groupRiskParityCode) return "#6b7280";
  return "#111827";
}

function buildDisplaySeries() {
  const mode = displayMode.value;
  const dates = visibleDates();
  const indexMap = new Map(dates.map((date, index) => [date, index]));
  const selected = selectedAssets();
  const normalizedByCode = new Map();
  const rawByCode = new Map();
  selected.forEach((item) => {
    const raw = assetRaw(item).filter((point) => point.date >= viewStartDate && point.date <= viewEndDate);
    rawByCode.set(item.code, raw);
    normalizedByCode.set(item.code, normalizeSeries(raw));
  });
  const benchmarkCode = benchmarkSelect.value;
  const benchmarkPoints = normalizedByCode.get(benchmarkCode) || [];
  const benchmarkMap = new Map(benchmarkPoints.map((point) => [point.date, point.value]));
  const seriesList = selected.map((item) => {
    let points = normalizedByCode.get(item.code) || [];
    if (mode === "relative") {
      points = points.map((point) => {
        const benchmarkValue = benchmarkMap.get(point.date);
        if (!benchmarkValue) return null;
        return { ...point, value: point.value / benchmarkValue };
      }).filter(Boolean);
    }
    const colorIndex = selected.filter((asset) => !asset.synthetic).findIndex((asset) => asset.code === item.code);
    const isBenchmark = mode === "relative" && item.code === benchmarkCode;
    return {
      code: item.code,
      name: item.name,
      color: item.synthetic ? syntheticColor(item.code) : dynamicColor(Math.max(0, colorIndex)),
      width: item.synthetic ? 1.8 : isBenchmark ? 2.8 : 1.9,
      dash: item.code === groupRiskParityCode ? [2, 3] : item.code === riskParityCode ? [9, 4] : item.synthetic ? [] : [5, 4],
      main: isBenchmark,
      synthetic: Boolean(item.synthetic),
      raw: rawByCode.get(item.code) || [],
      points: points.map((point) => pointWithIndex(point, indexMap)).filter(Boolean),
    };
  });
  return seriesList.filter((item) => item.points.length >= 2);
}

function buildYScale(seriesList) {
  const values = seriesList.flatMap((item) => item.points.map((point) => point.value)).filter((value) => value > 0);
  let min = Math.min(...values);
  let max = Math.max(...values);
  if (!Number.isFinite(min) || !Number.isFinite(max)) {
    min = 0.8;
    max = 1.2;
  }
  if (min === max) {
    min *= 0.9;
    max *= 1.1;
  }
  const logMin = Math.log(min) - 0.08;
  const logMax = Math.log(max) + 0.08;
  return { min: Math.exp(logMin), max: Math.exp(logMax), logMin, logMax };
}

function niceTicks(min, max) {
  const candidates = [0.25, 0.33, 0.5, 0.67, 0.8, 1, 1.25, 1.5, 2, 3, 4, 5, 7, 10, 14, 20];
  let ticks = candidates.filter((value) => value >= min && value <= max);
  if (ticks.length < 4) {
    ticks = [];
    const low = Math.log(min);
    const high = Math.log(max);
    for (let index = 0; index < 5; index++) {
      ticks.push(Math.exp(low + (high - low) * index / 4));
    }
  }
  return ticks;
}

function drawLine(points, x, y, color, width, dash = []) {
  if (points.length < 2) return;
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.setLineDash(dash);
  ctx.beginPath();
  points.forEach((point, index) => {
    const px = x(point.index);
    const py = y(point.value);
    if (index === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  });
  ctx.stroke();
  ctx.restore();
}

function drawDrawdownMarkers(series, x, y, seriesIndex) {
  const events = drawdownEvents(series.raw || []);
  if (!events.length) return;
  const pointByDate = new Map(series.points.map((point) => [point.date, point]));
  ctx.save();
  ctx.font = "11px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
  ctx.textAlign = "center";
  events.forEach((event, eventIndex) => {
    const point = pointByDate.get(event.troughDate);
    if (!point) return;
    const px = x(point.index);
    const py = y(point.value);
    const label = `${(event.drawdown * 100).toFixed(1)}%`;
    const offset = 16 + ((seriesIndex + eventIndex) % 4) * 13;
    const labelY = Math.min(chartGeometry.plotBottom - 3, py + offset);
    const textWidth = ctx.measureText(label).width;
    ctx.fillStyle = "rgba(255,255,255,.9)";
    ctx.fillRect(px - textWidth / 2 - 3, labelY - 10, textWidth + 6, 14);
    ctx.fillStyle = series.color;
    ctx.fillText(label, px, labelY);
    ctx.beginPath();
    ctx.arc(px, py, series.synthetic ? 4 : 3, 0, Math.PI * 2);
    ctx.fill();
  });
  ctx.restore();
}

function drawChart() {
  const { width, height } = resizeCanvas();
  const margin = { left: 70, right: 24, top: 26, bottom: 52 };
  const plotLeft = margin.left;
  const plotRight = width - margin.right;
  const plotTop = margin.top;
  const plotBottom = height - margin.bottom;
  const plotWidth = plotRight - plotLeft;
  const plotHeight = plotBottom - plotTop;
  const dates = visibleDates();
  const seriesList = buildDisplaySeries();
  const scale = buildYScale(seriesList);
  const x = (index) => plotLeft + (index / Math.max(1, dates.length - 1)) * plotWidth;
  const y = (value) => plotBottom - ((Math.log(value) - scale.logMin) / (scale.logMax - scale.logMin)) * plotHeight;
  chartGeometry = { plotLeft, plotRight, plotTop, plotBottom, plotWidth, plotHeight, seriesList, scale, dates, x, y };

  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, width, height);

  if (cycleToggle.checked) {
    for (const block of payload.cycleBlocks || []) {
      if (block.end_date < viewStartDate || block.start_date > viewEndDate) continue;
      const startIndex = indexForDate(block.start_date, false, dates);
      const endIndex = indexForDate(block.end_date, true, dates);
      const x1 = x(startIndex);
      const x2 = x(endIndex);
      ctx.fillStyle = block.state === "bull" ? "rgba(198, 60, 45, 0.075)" : "rgba(38, 132, 87, 0.085)";
      ctx.fillRect(x1, plotTop, Math.max(1, x2 - x1), plotHeight);
      if (labelToggle.checked && x2 - x1 > 80) {
        ctx.save();
        ctx.fillStyle = "rgba(23, 32, 42, 0.46)";
        ctx.font = "12px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
        ctx.fillText(block.label || "", x1 + 8, plotTop + 18);
        ctx.restore();
      }
    }
  }

  ctx.strokeStyle = "#d8dee8";
  ctx.lineWidth = 1;
  ctx.fillStyle = "#66717f";
  ctx.font = "12px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
  for (const tick of niceTicks(scale.min, scale.max)) {
    const py = y(tick);
    ctx.beginPath();
    ctx.moveTo(plotLeft, py);
    ctx.lineTo(plotRight, py);
    ctx.stroke();
    ctx.fillText(fmtMultiple(tick), 12, py + 4);
  }

  const xTicks = 6;
  for (let index = 0; index < xTicks; index++) {
    const dateIndexValue = Math.round((dates.length - 1) * index / (xTicks - 1));
    const px = x(dateIndexValue);
    ctx.strokeStyle = "#edf1f6";
    ctx.beginPath();
    ctx.moveTo(px, plotTop);
    ctx.lineTo(px, plotBottom);
    ctx.stroke();
    ctx.fillStyle = "#66717f";
    ctx.textAlign = index === 0 ? "left" : index === xTicks - 1 ? "right" : "center";
    if (dates[dateIndexValue]) ctx.fillText(dates[dateIndexValue].slice(0, 7), px, plotBottom + 28);
  }
  ctx.textAlign = "left";

  for (const item of seriesList.filter((line) => !line.main)) {
    drawLine(item.points, x, y, item.color, item.width, item.dash || []);
  }
  for (const item of seriesList.filter((line) => line.main)) {
    drawLine(item.points, x, y, item.color, item.width);
  }
  seriesList.forEach((item, index) => drawDrawdownMarkers(item, x, y, index));

  ctx.strokeStyle = "#17202a";
  ctx.lineWidth = 1;
  ctx.strokeRect(plotLeft, plotTop, plotWidth, plotHeight);

  if (hoverPoint && hoverPoint.index >= 0 && hoverPoint.index < dates.length) {
    const hoverX = x(hoverPoint.index);
    const hoverY = Math.max(plotTop, Math.min(plotBottom, hoverPoint.y));
    ctx.save();
    ctx.strokeStyle = "rgba(23, 32, 42, 0.62)";
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 3]);
    ctx.beginPath();
    ctx.moveTo(hoverX, plotTop);
    ctx.lineTo(hoverX, plotBottom);
    ctx.moveTo(plotLeft, hoverY);
    ctx.lineTo(plotRight, hoverY);
    ctx.stroke();
    ctx.restore();
  }
  if (dragStartX !== null && dragCurrentX !== null) {
    const left = Math.max(plotLeft, Math.min(dragStartX, dragCurrentX));
    const right = Math.min(plotRight, Math.max(dragStartX, dragCurrentX));
    ctx.save();
    ctx.fillStyle = "rgba(47, 99, 183, 0.14)";
    ctx.strokeStyle = "rgba(47, 99, 183, 0.75)";
    ctx.fillRect(left, plotTop, Math.max(1, right - left), plotHeight);
    ctx.strokeRect(left, plotTop, Math.max(1, right - left), plotHeight);
    ctx.restore();
  }
}

function nearestSeriesPoint(points, targetIndex) {
  if (!points.length) return null;
  let low = 0;
  let high = points.length - 1;
  while (low < high) {
    const mid = Math.floor((low + high) / 2);
    if (points[mid].index < targetIndex) low = mid + 1;
    else high = mid;
  }
  const right = points[low];
  const left = low > 0 ? points[low - 1] : null;
  if (!left) return right;
  return Math.abs(left.index - targetIndex) <= Math.abs(right.index - targetIndex) ? left : right;
}

function formatIndexValue(value) {
  if (!Number.isFinite(value)) return "-";
  return value.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function renderChartTooltip(clientX, clientY) {
  if (!hoverPoint || !chartGeometry) return;
  const mode = displayMode.value;
  const targetDate = chartGeometry.dates[hoverPoint.index];
  const rows = chartGeometry.seriesList.map((series) => {
    const point = nearestSeriesPoint(series.points, hoverPoint.index);
    if (!point) return null;
    return { series, point };
  }).filter(Boolean).sort((left, right) => right.point.value - left.point.value).map(({ series, point }) => {
    const plotted = mode === "relative" ? `相对 ${point.value.toFixed(2)}x` : `图上 ${point.value.toFixed(2)}x`;
    return `<div class="chart-tooltip-row"><i class="chart-tooltip-dot" style="background:${series.color}"></i><span>${series.name}</span><span>${formatIndexValue(point.close)} · ${plotted}</span></div>`;
  }).join("");
  chartTooltip.innerHTML = `<strong>${targetDate}</strong>${rows}`;
  chartTooltip.style.display = "block";
  const wrapRect = canvas.parentElement.getBoundingClientRect();
  const tooltipWidth = chartTooltip.offsetWidth;
  const tooltipHeight = chartTooltip.offsetHeight;
  let left = clientX - wrapRect.left + 14;
  let top = clientY - wrapRect.top + 14;
  if (left + tooltipWidth > wrapRect.width - 8) left = clientX - wrapRect.left - tooltipWidth - 14;
  if (top + tooltipHeight > wrapRect.height - 8) top = clientY - wrapRect.top - tooltipHeight - 14;
  chartTooltip.style.left = `${Math.max(8, left)}px`;
  chartTooltip.style.top = `${Math.max(8, top)}px`;
}

function renderLegend() {
  const selected = selectedAssets();
  const selectedItems = selected.map((item) => {
    const index = selected.filter((asset) => !asset.synthetic).findIndex((asset) => asset.code === item.code);
    const color = item.synthetic ? syntheticColor(item.code) : dynamicColor(Math.max(0, index));
    const swatchStyle = item.code === riskParityCode || item.code === groupRiskParityCode
      ? `background:transparent;border-top:2px ${item.code === groupRiskParityCode ? "dotted" : "dashed"} ${color};height:2px`
      : `background:${color}`;
    return `<span><i class="swatch" style="${swatchStyle}"></i>${item.name}</span>`;
  });
  legend.innerHTML = [
    `<span><i class="swatch" style="background:rgba(198,60,45,.45)"></i>牛市背景</span>`,
    `<span><i class="swatch" style="background:rgba(38,132,87,.45)"></i>熊市背景</span>`,
    ...selectedItems,
  ].join("");
}

function assetColor(asset, fallbackIndex = 0) {
  const index = selectedCandidates().findIndex((candidate) => candidate.code === asset.code);
  return dynamicColor(index >= 0 ? index : fallbackIndex);
}

function dailyReturnMap(asset) {
  const raw = assetRaw(asset).filter((point) => point.date >= viewStartDate && point.date <= viewEndDate);
  const returns = new Map();
  for (let index = 1; index < raw.length; index++) {
    const value = raw[index].close / raw[index - 1].close - 1;
    if (Number.isFinite(value)) returns.set(raw[index].date, value);
  }
  return returns;
}

function pairwiseCorrelation(leftMap, rightMap) {
  const pairs = [];
  for (const [date, left] of leftMap) {
    const right = rightMap.get(date);
    if (Number.isFinite(right)) pairs.push([left, right]);
  }
  if (pairs.length < 20) return { value: NaN, count: pairs.length };
  const leftMean = pairs.reduce((sum, pair) => sum + pair[0], 0) / pairs.length;
  const rightMean = pairs.reduce((sum, pair) => sum + pair[1], 0) / pairs.length;
  let covariance = 0;
  let leftVariance = 0;
  let rightVariance = 0;
  for (const [left, right] of pairs) {
    const leftDelta = left - leftMean;
    const rightDelta = right - rightMean;
    covariance += leftDelta * rightDelta;
    leftVariance += leftDelta * leftDelta;
    rightVariance += rightDelta * rightDelta;
  }
  const denominator = Math.sqrt(leftVariance * rightVariance);
  return { value: denominator > 0 ? covariance / denominator : NaN, count: pairs.length };
}

function correlationCellStyle(value) {
  if (!Number.isFinite(value)) return "background:#f2f4f7;color:#87909b";
  if (value === 1) return "background:#3f4854;color:#fff";
  const alpha = 0.12 + Math.min(1, Math.abs(value)) * 0.68;
  const color = value >= 0 ? `rgba(176,58,46,${alpha})` : `rgba(35,116,71,${alpha})`;
  return `background:${color};color:${Math.abs(value) >= 0.55 ? "#fff" : "#17202a"}`;
}

function renderCorrelationMatrix() {
  const assets = selectedCandidates();
  if (!assets.length) {
    correlationMatrix.innerHTML = `<div class="empty">请先选择资产。</div>`;
    return;
  }
  const returnMaps = assets.map(dailyReturnMap);
  const header = assets.map((asset) => `<th title="${asset.name}">${asset.name}</th>`).join("");
  const rows = assets.map((rowAsset, rowIndex) => {
    const cells = assets.map((columnAsset, columnIndex) => {
      const result = rowIndex === columnIndex
        ? { value: 1, count: returnMaps[rowIndex].size }
        : pairwiseCorrelation(returnMaps[rowIndex], returnMaps[columnIndex]);
      const value = Number.isFinite(result.value) ? result.value.toFixed(2) : "-";
      return `<td style="${correlationCellStyle(result.value)}" title="${rowAsset.name} / ${columnAsset.name}；共同样本 ${result.count}">${value}</td>`;
    }).join("");
    return `<tr><th title="${rowAsset.name}">${rowAsset.name}</th>${cells}</tr>`;
  }).join("");
  correlationMatrix.innerHTML = `<table class="correlation-table"><thead><tr><th>资产</th>${header}</tr></thead><tbody>${rows}</tbody></table>`;
}

function renderPortfolioWeights() {
  const portfolios = selectedAssets().filter((asset) => asset.synthetic && asset.components?.length);
  if (!portfolios.length) {
    portfolioWeights.innerHTML = `<div class="empty">至少选择两项资产，并开启一种虚拟组合。</div>`;
    return;
  }
  portfolioWeights.innerHTML = portfolios.map((portfolio) => {
    const components = portfolio.components
      .filter((item) => Number.isFinite(item.weight) && item.weight >= 0)
      .sort((left, right) => right.weight - left.weight);
    const stack = components.map((item, index) => `<i class="weight-segment" style="width:${item.weight * 100}%;background:${assetColor(item.asset, index)}" title="${item.asset.name} ${(item.weight * 100).toFixed(1)}%"></i>`).join("");
    const list = components.map((item, index) => `<div class="weight-item"><i style="background:${assetColor(item.asset, index)}"></i><span title="${item.asset.name}${item.riskGroup ? `；风险组：${item.riskGroup}` : ""}">${item.asset.name}${item.riskGroup ? ` · ${item.riskGroup}` : ""}</span><b>${(item.weight * 100).toFixed(1)}%</b></div>`).join("");
    return `<div class="portfolio-block"><div class="portfolio-title"><span>${portfolio.name}</span><span>${portfolio.lastRebalanceQuarter || "-"}</span></div><div class="weight-stack">${stack}</div><div class="weight-list">${list}</div></div>`;
  }).join("");
}

function renderAllocationAnalytics() {
  renderCorrelationMatrix();
  renderPortfolioWeights();
}

function renderSummary() {
  const selected = selectedCandidates();
  const fullStats = selected.map((item) => {
    const stats = segmentStats(assetRaw(item), viewStartDate, viewEndDate);
    return { item, stats };
  }).filter((row) => row.stats);
  const best = fullStats.sort((left, right) => right.stats.total - left.stats.total)[0];
  const failures = payload.failures || [];
  summaryCards.innerHTML = `
    <div class="stat"><span class="label">观察区间</span><span class="value">${viewStartDate} 至 ${viewEndDate}</span></div>
    <div class="stat"><span class="label">已选资产</span><span class="value">${selected.length} 条</span></div>
    <div class="stat"><span class="label">所选最强</span><span class="value">${best ? `${best.item.name} ${fmtPlainPct(best.stats.total)}` : "-"}</span></div>
  `;
  const failText = failures.length ? `；${failures.length} 条候选没有取到有效行情` : "";
  sourceNote.textContent = `优先全收益口径；选择两条以上可生成季度等权、风险平价或分组风险平价组合；可选${payload.candidates.length}条${failText}`;
  const benchmark = payload.candidates.find((item) => item.code === benchmarkSelect.value);
  chartTitle.textContent = displayMode.value === "relative"
    ? `相对${benchmark ? benchmark.name : "比较基准"}：1.00x代表同步`
    : `归一化走势：${viewStartDate} 至 ${viewEndDate}，区间起点为1.00x`;
}

function renderStageTable() {
  const assets = selectedAssets();
  const blocks = (payload.cycleBlocks || []).filter((block) => block.start_date && block.end_date);
  if (!blocks.length) {
    stageTable.innerHTML = `<div class="empty">没有可用牛熊阶段。</div>`;
    return;
  }
  const rows = blocks.map((block) => {
    const stats = assets.map((asset) => ({ asset, stats: segmentStats(assetRaw(asset), block.start_date, block.end_date) }))
      .filter((row) => row.stats);
    if (!stats.length) return "";
    stats.sort((left, right) => right.stats.total - left.stats.total);
    const mainRow = stats.find((row) => row.asset.main);
    const best = stats[0];
    const rank = mainRow ? stats.findIndex((row) => row.asset.main) + 1 : null;
    const gap = mainRow && best ? mainRow.stats.total - best.stats.total : NaN;
    return `
      <tr>
        <td>${block.label || `${block.start_date} 至 ${block.end_date}`}</td>
        <td>${block.state === "bull" ? "牛市" : block.state === "bear" ? "熊市" : "阶段"}</td>
        <td>${mainRow ? fmtPct(mainRow.stats.total) : "-"}</td>
        <td>${mainRow ? fmtPct(mainRow.stats.annual) : "-"}</td>
        <td>${mainRow ? fmtPct(mainRow.stats.maxDrawdown) : "-"}</td>
        <td>${best ? best.asset.name : "-"}</td>
        <td>${best ? fmtPct(best.stats.total) : "-"}</td>
        <td>${rank ? `${rank}/${stats.length}` : "-"}</td>
        <td>${fmtPct(gap)}</td>
      </tr>
    `;
  }).join("");
  stageTable.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>阶段</th>
          <th>类型</th>
          <th>自由现金流涨跌</th>
          <th>自由现金流年化</th>
          <th>自由现金流回撤</th>
          <th>阶段最强</th>
          <th>最强涨跌</th>
          <th>自由现金流排名</th>
          <th>相对最强</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function defaultFullSortDirection(key) {
  return ["name", "code", "group", "returnType"].includes(key) ? "asc" : "desc";
}

function fullSortValue(row, key) {
  if (key === "name") return row.asset.name || "";
  if (key === "code") return row.asset.code || "";
  if (key === "group") return row.asset.group || "";
  if (key === "returnType") return row.asset.returnType || "";
  if (key === "total") return row.stats.total;
  if (key === "annual") return row.stats.annual;
  if (key === "volatility") return row.stats.volatility;
  if (key === "sharpe") return row.stats.sharpe;
  if (key === "calmar") return row.stats.calmar;
  if (key === "maxDrawdown") return row.stats.maxDrawdown;
  if (key === "maxDrawdownDate") return row.stats.maxDrawdownEndDate || row.stats.maxDrawdownStartDate || "";
  if (key === "recovery") return row.recovery ? row.recovery.rebound : NaN;
  if (key === "historicalDrawdowns") return row.drawdownEvents.length ? Math.max(...row.drawdownEvents.map((event) => Math.abs(event.drawdown))) : 0;
  return row.stats.annual;
}

function compareFullRows(left, right) {
  const leftValue = fullSortValue(left, fullTableSort.key);
  const rightValue = fullSortValue(right, fullTableSort.key);
  const leftMissing = leftValue === null || leftValue === undefined || leftValue === "" || (typeof leftValue === "number" && !Number.isFinite(leftValue));
  const rightMissing = rightValue === null || rightValue === undefined || rightValue === "" || (typeof rightValue === "number" && !Number.isFinite(rightValue));
  let result = 0;
  if (leftMissing && rightMissing) result = 0;
  else if (leftMissing) return 1;
  else if (rightMissing) return -1;
  else if (typeof leftValue === "number" && typeof rightValue === "number") result = leftValue - rightValue;
  else result = String(leftValue).localeCompare(String(rightValue), "zh-Hans-CN", { numeric: true });
  if (result === 0) result = (left.asset.name || "").localeCompare(right.asset.name || "", "zh-Hans-CN", { numeric: true });
  return fullTableSort.direction === "asc" ? result : -result;
}

function fullHeader(label, key, title = "点击排序") {
  const active = fullTableSort.key === key;
  const mark = active ? (fullTableSort.direction === "asc" ? "↑" : "↓") : "";
  return `<th class="sortable${active ? " active" : ""}" data-sort-key="${key}" title="${title}">${label}<span class="sort-mark">${mark}</span></th>`;
}

function bindFullTableSort() {
  fullTable.querySelectorAll("th[data-sort-key]").forEach((header) => {
    header.addEventListener("click", () => {
      const key = header.dataset.sortKey;
      if (fullTableSort.key === key) {
        fullTableSort.direction = fullTableSort.direction === "asc" ? "desc" : "asc";
      } else {
        fullTableSort.key = key;
        fullTableSort.direction = defaultFullSortDirection(key);
      }
      renderFullTable();
    });
  });
}

function renderFullTable() {
  const assets = selectedAssets();
  fullTableTitle.textContent = `所选区间排序：${viewStartDate} 至 ${viewEndDate}`;
  const rows = assets.map((asset) => ({
    asset,
    stats: segmentStats(assetRaw(asset), viewStartDate, viewEndDate),
    drawdownEvents: drawdownEvents(assetRaw(asset)),
    recovery: latestDrawdownRecovery(assetRaw(asset)),
  }))
    .filter((row) => row.stats)
    .sort(compareFullRows)
    .map((row, index) => `
      <tr>
        <td>${index + 1}</td>
        <td>${row.asset.name}</td>
        <td>${row.asset.synthetic ? "虚拟" : row.asset.code}</td>
        <td>${row.asset.group || "-"}</td>
        <td>${row.asset.returnType || "-"}</td>
        <td>${fmtPct(row.stats.total)}</td>
        <td>${fmtPct(row.stats.annual)}</td>
        <td title="日收益率样本标准差 × √252">${fmtPct(row.stats.volatility)}</td>
        <td title="日收益均值 ÷ 日收益标准差 × √252；无风险利率按0计算">${fmtRatio(row.stats.sharpe)}</td>
        <td title="年化收益 ÷ 最大回撤绝对值">${fmtRatio(row.stats.calmar)}</td>
        <td>${fmtPct(row.stats.maxDrawdown)}</td>
        <td title="最大回撤谷底日期">${row.stats.maxDrawdownEndDate || "-"}</td>
        <td title="${row.recovery ? `最近回撤峰值 ${row.recovery.peakDate}，谷底 ${row.recovery.troughDate}；谷底至 ${row.recovery.currentDate} 的涨幅` : "当前区间没有达到阈值的回撤"}">${row.recovery ? `回撤 ${fmtPct(row.recovery.drawdown)} / 上升 ${fmtPct(row.recovery.rebound)}` : "-"}</td>
        <td>${fmtHistoricalDrawdowns(row.drawdownEvents)}</td>
      </tr>
    `).join("");
  fullTable.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>排名</th>
          ${fullHeader("指数", "name")}
          ${fullHeader("代码", "code")}
          ${fullHeader("分组", "group")}
          ${fullHeader("收益口径", "returnType")}
          ${fullHeader("累计涨跌", "total")}
          ${fullHeader("年化", "annual")}
          ${fullHeader("波动率", "volatility", "日收益率样本标准差乘以√252；点击排序")}
          ${fullHeader("夏普", "sharpe", "日收益夏普，按252个交易日年化，无风险利率为0；点击排序")}
          ${fullHeader("卡玛", "calmar", "年化收益除以最大回撤绝对值；点击排序")}
          ${fullHeader("最大回撤", "maxDrawdown")}
          ${fullHeader("最大回撤日期", "maxDrawdownDate")}
          ${fullHeader("当前回撤修复情况", "recovery", "最近一次达到阈值的最大回撤 / 当前值相对该回撤谷底的涨幅；点击排序")}
          ${fullHeader(`历史回撤 ≥ ${drawdownThreshold.value}%`, "historicalDrawdowns", "按标准回撤周期列出所选区间内超过阈值的峰值至谷值回撤；点击排序")}
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
  bindFullTableSort();
}

function update() {
  renderBenchmarkOptions();
  renderSummary();
  drawChart();
  renderLegend();
  renderFullTable();
  renderAllocationAnalytics();
  startDateInput.value = viewStartDate;
  endDateInput.value = viewEndDate;
  drawdownThresholdValue.textContent = `${drawdownThreshold.value}%`;
  restoreChartRange.disabled = viewStartDate === payload.analysis.firstDate && viewEndDate === payload.analysis.lastDate;
}

function resetViewRange() {
  viewStartDate = payload.analysis.firstDate;
  viewEndDate = payload.analysis.lastDate;
  dragStartX = null;
  dragCurrentX = null;
  hoverPoint = null;
  update();
}

document.getElementById("selectDefault").addEventListener("click", () => {
  for (const input of document.querySelectorAll(".index-check")) {
    const item = payload.candidates.find((candidate) => candidate.code === input.value);
    input.checked = Boolean(item && item.default);
  }
  update();
});
document.getElementById("resetRange").addEventListener("click", () => {
  resetViewRange();
});
restoreChartRange.addEventListener("click", resetViewRange);
document.getElementById("clearSelection").addEventListener("click", () => {
  for (const input of document.querySelectorAll(".index-check")) input.checked = false;
  update();
});
function setFullscreenView(active) {
  pageRoot.classList.toggle("fullscreen-view", active);
  document.body.classList.toggle("chart-fullscreen", active);
  fullscreenButton.textContent = active ? "退出全屏" : "全屏";
  update();
}

fullscreenButton.addEventListener("click", () => {
  setFullscreenView(!pageRoot.classList.contains("fullscreen-view"));
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && pageRoot.classList.contains("fullscreen-view")) {
    setFullscreenView(false);
  }
});
displayMode.addEventListener("change", update);
benchmarkSelect.addEventListener("change", update);
currencyMode.addEventListener("change", update);
cycleToggle.addEventListener("change", update);
labelToggle.addEventListener("change", update);
equalWeightToggle.addEventListener("change", update);
riskParityToggle.addEventListener("change", update);
groupRiskParityToggle.addEventListener("change", update);
drawdownThreshold.addEventListener("input", update);
window.addEventListener("resize", update);
function applyDateInputs() {
  const start = startDateInput.value;
  const end = endDateInput.value;
  if (!start || !end || start >= end) return;
  viewStartDate = start < payload.analysis.firstDate ? payload.analysis.firstDate : start;
  viewEndDate = end > payload.analysis.lastDate ? payload.analysis.lastDate : end;
  hoverPoint = null;
  update();
}
startDateInput.min = payload.analysis.firstDate;
startDateInput.max = payload.analysis.lastDate;
endDateInput.min = payload.analysis.firstDate;
endDateInput.max = payload.analysis.lastDate;
startDateInput.addEventListener("change", applyDateInputs);
endDateInput.addEventListener("change", applyDateInputs);
canvas.addEventListener("mousedown", (event) => {
  if (!chartGeometry) return;
  const rect = canvas.getBoundingClientRect();
  const mouseX = event.clientX - rect.left;
  const mouseY = event.clientY - rect.top;
  const { plotLeft, plotRight, plotTop, plotBottom } = chartGeometry;
  if (mouseX < plotLeft || mouseX > plotRight || mouseY < plotTop || mouseY > plotBottom) return;
  dragStartX = mouseX;
  dragCurrentX = mouseX;
  chartTooltip.style.display = "none";
});
canvas.addEventListener("mousemove", (event) => {
  if (!chartGeometry || !chartGeometry.dates.length) return;
  const rect = canvas.getBoundingClientRect();
  const mouseX = event.clientX - rect.left;
  const mouseY = event.clientY - rect.top;
  const { plotLeft, plotRight, plotTop, plotBottom, plotWidth } = chartGeometry;
  if (dragStartX !== null) {
    dragCurrentX = Math.max(plotLeft, Math.min(plotRight, mouseX));
    hoverPoint = null;
    chartTooltip.style.display = "none";
    drawChart();
    return;
  }
  if (mouseX < plotLeft || mouseX > plotRight || mouseY < plotTop || mouseY > plotBottom) {
    hoverPoint = null;
    chartTooltip.style.display = "none";
    drawChart();
    return;
  }
  const index = Math.max(0, Math.min(chartGeometry.dates.length - 1, Math.round((mouseX - plotLeft) / plotWidth * (chartGeometry.dates.length - 1))));
  hoverPoint = { index, y: mouseY };
  drawChart();
  renderChartTooltip(event.clientX, event.clientY);
});
canvas.addEventListener("mouseup", () => {
  if (dragStartX === null || dragCurrentX === null || !chartGeometry) return;
  const distance = Math.abs(dragCurrentX - dragStartX);
  if (distance >= 8) {
    const left = Math.min(dragStartX, dragCurrentX);
    const right = Math.max(dragStartX, dragCurrentX);
    const startIndex = Math.round((left - chartGeometry.plotLeft) / chartGeometry.plotWidth * (chartGeometry.dates.length - 1));
    const endIndex = Math.round((right - chartGeometry.plotLeft) / chartGeometry.plotWidth * (chartGeometry.dates.length - 1));
    viewStartDate = chartGeometry.dates[Math.max(0, startIndex)];
    viewEndDate = chartGeometry.dates[Math.min(chartGeometry.dates.length - 1, endIndex)];
  }
  dragStartX = null;
  dragCurrentX = null;
  update();
});
canvas.addEventListener("dblclick", () => {
  resetViewRange();
});
canvas.addEventListener("mouseleave", () => {
  hoverPoint = null;
  chartTooltip.style.display = "none";
  if (dragStartX === null) drawChart();
});

renderPicker();
update();
</script>
<div data-myinvest-footer></div>
<script src="https://invest.okbbc.com/footer.js" charset="utf-8" defer></script>
</body>
</html>
"""
    output_path.write_text(html_template.replace("__PAYLOAD__", safe_json(payload)), encoding="utf-8")


def write_html(
    series: IndexSeries,
    records: pd.DataFrame,
    output_path: Path,
    y_scale: str,
    reversal_threshold: float,
) -> None:
    payload = chart_payload(series, records, y_scale, reversal_threshold)
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{series.name}波段拐点标记</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #17202a;
      --muted: #66717f;
      --line: #d8dee8;
      --panel: #ffffff;
      --bg: #f5f7f9;
      --main: #1f7a68;
      --turning-line: #3d4752;
      --turning-high: #b45f06;
      --turning-low: #275f9f;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
      background: var(--bg);
      color: var(--ink);
    }}
    .site-header {{
      background: rgba(255, 255, 255, 0.94);
      border-bottom: 1px solid var(--line);
    }}
    .site-nav {{
      width: calc(100vw - 24px);
      min-height: 50px;
      margin: 0 auto;
      display: flex;
      align-items: center;
      gap: 16px;
      overflow-x: auto;
      white-space: nowrap;
    }}
    .brand {{
      color: var(--ink);
      font-weight: 800;
      text-decoration: none;
    }}
    .site-nav a:not(.brand) {{
      color: var(--muted);
      font-size: 13px;
      text-decoration: none;
    }}
    .site-nav a.active {{
      color: var(--main);
      font-weight: 700;
    }}
    main {{
      width: calc(100vw - 24px);
      margin: 18px auto 28px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: clamp(24px, 3vw, 36px);
      line-height: 1.15;
      letter-spacing: 0;
    }}
    .subtitle {{
      margin: 0;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.7;
    }}
    .research-finding {{
      margin: 14px 0 16px;
      padding: 16px 18px;
      background: #fff7e6;
      border: 1px solid #e2b95f;
      border-left: 6px solid #b45f06;
      border-radius: 8px;
      box-shadow: 0 8px 20px rgba(180, 95, 6, 0.08);
    }}
    .research-finding h2 {{
      margin: 0 0 8px;
      color: #7a3f06;
      font-size: 18px;
      line-height: 1.35;
      letter-spacing: 0;
    }}
    .research-finding p {{
      margin: 0;
      color: #2c2f35;
      font-size: 14px;
      line-height: 1.8;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin: 16px 0;
    }}
    .stat {{
      min-height: 86px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px 14px;
    }}
    .label {{
      display: block;
      margin-bottom: 8px;
      color: var(--muted);
      font-size: 12px;
    }}
    .value {{
      display: block;
      font-size: 18px;
      font-weight: 700;
      white-space: nowrap;
    }}
    .controls {{
      display: grid;
      gap: 8px;
      margin: 0 0 14px;
      padding: 12px 14px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    .slider-row {{
      display: grid;
      grid-template-columns: auto minmax(140px, 1fr) 72px;
      gap: 12px;
      align-items: center;
    }}
    .slider-label {{
      color: var(--ink);
      font-size: 14px;
      font-weight: 700;
      white-space: nowrap;
    }}
    input[type="range"] {{
      width: 100%;
      accent-color: var(--main);
    }}
    .reversal-output {{
      color: var(--ink);
      font-size: 18px;
      font-weight: 700;
      text-align: right;
    }}
    .slider-hints {{
      display: flex;
      justify-content: space-between;
      padding-left: calc(56px + 12px);
      color: var(--muted);
      font-size: 12px;
    }}
    .indicator-controls {{
      display: grid;
      gap: 8px;
      padding-top: 8px;
      border-top: 1px solid var(--line);
    }}
    .indicator-title {{
      color: var(--ink);
      font-size: 14px;
      font-weight: 700;
    }}
    .indicator-grid {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px 14px;
      color: var(--muted);
      font-size: 13px;
    }}
    .indicator-toggle {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      min-height: 28px;
      white-space: nowrap;
      cursor: pointer;
    }}
    .indicator-toggle input {{
      margin: 0;
      accent-color: var(--main);
    }}
    .indicator-swatch {{
      width: 18px;
      height: 3px;
      border-radius: 999px;
      display: inline-block;
    }}
    .legend {{
      display: flex;
      flex-wrap: wrap;
      gap: 16px;
      margin: 0;
      color: var(--muted);
      font-size: 13px;
    }}
    .legend span {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }}
    .swatch {{
      width: 22px;
      height: 3px;
      border-radius: 999px;
      display: inline-block;
    }}
    .toolbar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin: 0 0 12px;
    }}
    .scale-control {{
      display: inline-flex;
      align-items: center;
      gap: 3px;
      padding: 3px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
    }}
    .scale-control span {{
      padding: 0 6px;
    }}
    .scale-control button {{
      min-width: 54px;
      height: 28px;
      border: 0;
      border-radius: 6px;
      background: transparent;
      color: var(--muted);
      font: inherit;
      cursor: pointer;
    }}
    .scale-control button.active {{
      background: #17202a;
      color: #ffffff;
      font-weight: 700;
    }}
    .chart-shell {{
      position: relative;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }}
    canvas {{
      display: block;
      width: 100%;
      height: min(68vh, 640px);
      min-height: 430px;
    }}
    .tooltip {{
      position: absolute;
      display: none;
      min-width: 230px;
      max-width: 360px;
      padding: 8px 10px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: rgba(255, 255, 255, 0.96);
      box-shadow: 0 8px 22px rgba(23, 32, 42, 0.12);
      pointer-events: none;
      font-size: 12px;
      line-height: 1.55;
    }}
    .notes {{
      margin-top: 14px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.7;
    }}
    .notes p {{ margin: 4px 0; }}
    .drawdown-strategy {{
      margin-top: 16px;
      padding: 16px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    .drawdown-strategy h2 {{
      margin: 0 0 8px;
      font-size: 18px;
      line-height: 1.35;
      letter-spacing: 0;
    }}
    .drawdown-strategy p {{
      margin: 6px 0;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.7;
    }}
    .strategy-control {{
      display: grid;
      grid-template-columns: minmax(140px, 220px) minmax(220px, 1fr) 70px;
      gap: 12px;
      align-items: center;
      margin: 12px 0;
      padding: 12px 0;
      border-top: 1px solid var(--line);
      border-bottom: 1px solid var(--line);
    }}
    .strategy-control label {{
      color: var(--ink);
      font-size: 14px;
      font-weight: 700;
    }}
    .strategy-summary {{
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 10px;
      margin: 12px 0;
    }}
    .strategy-metric {{
      min-height: 76px;
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcfd;
    }}
    .strategy-chart-wrap {{
      margin-top: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #ffffff;
    }}
    #drawdownStrategyChart,
    #coreStrategyChart {{
      display: block;
      width: 100%;
      height: 320px;
      min-height: 260px;
    }}
    @media (max-width: 980px) {{
      .stats {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
      .toolbar {{
        align-items: flex-start;
        flex-direction: column;
      }}
      .slider-row {{
        grid-template-columns: 1fr 72px;
      }}
      .slider-label {{
        grid-column: 1 / -1;
      }}
      .slider-hints {{
        padding-left: 0;
      }}
      canvas {{
        min-height: 360px;
      }}
      .value {{
        font-size: 16px;
      }}
      .strategy-control {{
        grid-template-columns: 1fr 70px;
      }}
      .strategy-control label {{
        grid-column: 1 / -1;
      }}
      .strategy-summary {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
    }}
  </style>
</head>
<body>
<div data-myinvest-header></div>
<script src="https://invest.okbbc.com/header.js" charset="utf-8" defer></script>
<header class="site-header">
  <nav class="site-nav" aria-label="研究入口">
    <a class="brand" href="/index.html">研究入口</a>
    <a href="/{series.code.replace('.', '_')}_new_high_low.html">Log回归通道</a>
    <a class="active" href="/{series.code.replace('.', '_')}_zigzag_strategy.html">ZigZag拐点策略</a>
    <a href="/{series.code.replace('.', '_')}_mainline_background.html">资产配置研究</a>
    <a href="/{series.code.replace('.', '_')}_alpha.html">资产 Alpha 研究</a>
    <a href="/{series.code.replace('.', '_')}_strategy_portfolio.html">策略组合研究</a>
    <a href="/{series.code.replace('.', '_')}_daily.csv">日线数据</a>
    <a href="/{series.code.replace('.', '_')}_record_points.csv">拐点记录</a>
  </nav>
</header>
<main>
  <header>
    <h1>{series.name}（{series.code}）</h1>
    <p class="subtitle">收盘价曲线 + 高低交替的波段拐点折线 · {payload["first"]["trade_date"]} 至 {payload["last"]["trade_date"]}</p>
  </header>
  <section class="research-finding" aria-label="核心研究发现">
    <h2>研究发现：自由现金流更适合买入纪律，不适合频繁卖出</h2>
    <p>对这条长期正漂移指数，复杂减仓策略虽然能降低一部分回撤，但年化和 Calmar 没有明显优于满仓持有。更清晰的做法是：尚未建仓时，发现从历史高点回撤超过 20% 后买入；买入后长期满仓持有，不再为了高抛低吸而卖出。ZigZag 和通道只作为观察，不作为卖出依据。</p>
  </section>
  <section class="stats" id="stats" aria-label="指数统计"></section>
  <section class="controls" aria-label="回撤阈值">
    <div class="slider-row">
      <label class="slider-label" for="reversalSlider">回撤阈值</label>
      <input id="reversalSlider" type="range" min="5" max="40" step="0.5">
      <output class="reversal-output" id="reversalValue" for="reversalSlider"></output>
    </div>
    <div class="slider-hints"><span>5%</span><span>40%</span></div>
    <div class="strategy-control">
      <label for="drawdownStopSlider">高点回落 n%</label>
      <input id="drawdownStopSlider" type="range" min="1" max="15" step="1" value="8">
      <output id="drawdownStopValue" for="drawdownStopSlider">8%</output>
    </div>
    <div class="indicator-controls" aria-label="趋势线选择">
      <span class="indicator-title">趋势线</span>
      <div class="indicator-grid">
        <label class="indicator-toggle"><input type="checkbox" data-indicator="logRegression"><i class="indicator-swatch" style="background:#6c4ab6"></i>Log回归通道</label>
        <label class="indicator-toggle"><input type="checkbox" data-indicator="bollinger"><i class="indicator-swatch" style="background:#c44e52"></i>布林带</label>
        <label class="indicator-toggle"><input type="checkbox" data-indicator="keltner"><i class="indicator-swatch" style="background:#dd8452"></i>肯特纳</label>
        <label class="indicator-toggle"><input type="checkbox" data-indicator="donchian"><i class="indicator-swatch" style="background:#4c72b0"></i>唐奇安</label>
        <label class="indicator-toggle"><input type="checkbox" data-indicator="maEnvelope"><i class="indicator-swatch" style="background:#8172b2"></i>均线包络</label>
        <label class="indicator-toggle"><input type="checkbox" data-indicator="zigzagChannel"><i class="indicator-swatch" style="background:#64a12d"></i>ZigZag高低点</label>
      </div>
    </div>
  </section>
  <div class="toolbar">
    <div class="legend">
      <span><i class="swatch" style="background: var(--main)"></i>收盘价</span>
      <span><i class="swatch" style="background: var(--turning-line)"></i>拐点折线</span>
      <span><i class="swatch" style="background: #c44e52"></i>20%策略净值</span>
      <span><i class="swatch" style="background: #0f67b1"></i>核心仓净值</span>
      <span><i class="swatch" style="background: #d9892b"></i>折线中点线</span>
      <span><i class="swatch" style="background: #8a6fd1"></i>中点交点差</span>
      <span><i class="swatch" style="background: #c73d3d"></i>牛市背景</span>
      <span><i class="swatch" style="background: #17885b"></i>熊市背景</span>
      <span><i class="swatch" style="background: #8b95a5"></i>上证背景</span>
      <span><i class="swatch" style="background: var(--turning-high)"></i>波段高点</span>
      <span><i class="swatch" style="background: var(--turning-low)"></i>波段低点</span>
    </div>
    <div class="scale-control" aria-label="Y轴模式">
      <span>Y轴</span>
      <button type="button" data-scale="linear">点位</button>
      <button type="button" data-scale="percent">百分比</button>
      <button type="button" data-scale="log">对数</button>
    </div>
  </div>
  <section class="chart-shell">
    <canvas id="chart" aria-label="{series.name}波段拐点折线图"></canvas>
    <div class="tooltip" id="tooltip"></div>
  </section>
  <section class="notes" id="notes" aria-label="数据说明"></section>
  <section class="drawdown-strategy" aria-label="20%回撤买入策略">
    <h2>20%回撤买入 + 高点回落 n% 空仓</h2>
    <p>无未来函数口径：从空仓开始，收盘价相对历史最高收盘价首次回撤达到 20% 时满仓；买入后只使用持仓期间已经出现的最高收盘价做移动高点，从该高点回落 n% 时空仓。空仓后需要回撤重新收窄到 20% 以内，再次跌破 20% 才重新触发买入。</p>
    <div class="strategy-summary" id="drawdownStrategySummary" aria-label="当前参数回测结果"></div>
    <p>下图为 n=1 到 15 的年化收益对比，柱状图高亮当前滑块值。</p>
    <div class="strategy-chart-wrap">
      <canvas id="drawdownStrategyChart" aria-label="n从1到15的年化收益柱状图"></canvas>
    </div>
  </section>
  <section class="drawdown-strategy" aria-label="核心仓机动仓策略回测">
    <h2>核心仓 + 机动仓策略回测</h2>
    <p>无未来函数口径：第 t 日收盘后计算目标仓位，从第 t+1 日收益开始生效。基础仓位 70%；历史高点回撤 10%-20% 提高到 80%；回撤达到 20% 提高到 100%；跌破 1年滚动 Log 回归中轨时仓位上限为 70%；跌破 2年滚动 Log 回归下轨时仓位上限为 50%。</p>
    <div class="strategy-summary" id="coreStrategySummary" aria-label="核心仓机动仓回测结果"></div>
    <p>下图比较核心仓策略净值与满仓持有净值。该策略目标不是每次跑赢满仓，而是尽量保留长期趋势收益，同时降低回撤和持仓压力。</p>
    <div class="strategy-chart-wrap">
      <canvas id="coreStrategyChart" aria-label="核心仓策略和满仓持有净值曲线"></canvas>
    </div>
  </section>
</main>

<script>
const payload = {safe_json(payload)};
const canvas = document.getElementById("chart");
const tip = document.getElementById("tooltip");
const ctx = canvas.getContext("2d");
const fmt = new Intl.NumberFormat("zh-CN", {{ maximumFractionDigits: 2 }});
const pct = new Intl.NumberFormat("zh-CN", {{ maximumFractionDigits: 2, minimumFractionDigits: 2 }});
const statsEl = document.getElementById("stats");
const notesEl = document.getElementById("notes");
const reversalSlider = document.getElementById("reversalSlider");
const reversalValue = document.getElementById("reversalValue");
const drawdownStopSlider = document.getElementById("drawdownStopSlider");
const drawdownStopValue = document.getElementById("drawdownStopValue");
const drawdownStrategySummary = document.getElementById("drawdownStrategySummary");
const drawdownStrategyChart = document.getElementById("drawdownStrategyChart");
const drawdownCtx = drawdownStrategyChart.getContext("2d");
const coreStrategySummary = document.getElementById("coreStrategySummary");
const coreStrategyChart = document.getElementById("coreStrategyChart");
const coreCtx = coreStrategyChart.getContext("2d");
const scaleButtons = Array.from(document.querySelectorAll("[data-scale]"));
const indicatorInputs = Array.from(document.querySelectorAll("[data-indicator]"));
let currentScale = payload.yScale || "log";
let currentReversal = Math.max(0.05, Math.min(0.4, Number(payload.reversalThreshold) || 0.125));
let currentAnalysis = null;
let currentDrawdownGrid = [];

payload.points = payload.points.map((p) => ({{
  ...p,
  close: Number(p.close),
  high: Number.isFinite(Number(p.high)) ? Number(p.high) : Number(p.close),
  low: Number.isFinite(Number(p.low)) ? Number(p.low) : Number(p.close),
  time: Date.parse(p.trade_date + "T00:00:00Z"),
}}));
payload.first = {{ ...payload.first, time: Date.parse(payload.first.trade_date + "T00:00:00Z") }};
payload.last = {{ ...payload.last, time: Date.parse(payload.last.trade_date + "T00:00:00Z") }};
const marketContext = payload.marketContext || {{ series: [], cycleBlocks: [] }};
marketContext.series = (marketContext.series || []).map((point) => ({{
  ...point,
  close: Number(point.close),
  time: Date.parse(point.trade_date + "T00:00:00Z"),
}})).filter((point) => Number.isFinite(point.time) && Number.isFinite(point.close) && point.close > 0);
marketContext.cycleBlocks = (marketContext.cycleBlocks || []).map((block) => ({{
  ...block,
  startTime: Date.parse(block.start_date + "T00:00:00Z"),
  endTime: Date.parse(block.end_date + "T00:00:00Z"),
}})).filter((block) => Number.isFinite(block.startTime) && Number.isFinite(block.endTime));
reversalSlider.value = String(currentReversal * 100);

function formatSignedPercent(value) {{
  const sign = value > 0 ? "+" : "";
  return `${{sign}}${{pct.format(value)}}%`;
}}

function computeTurningPoints(points, reversalThreshold) {{
  const closes = points.map((point) => Number(point.close));
  const pivots = [];
  if (!points.length) return pivots;

  const addPivot = (rowIndex, turningType, pointType) => {{
    if (pivots.length && pivots[pivots.length - 1].row_index === rowIndex) return;
    pivots.push({{
      row_index: rowIndex,
      turning_type: turningType,
      point_type: pointType,
      trade_date: points[rowIndex].trade_date,
      close: closes[rowIndex],
      time: points[rowIndex].time,
    }});
  }};

  let trend = 0;
  let highIdx = 0;
  let lowIdx = 0;

  for (let idx = 1; idx < closes.length; idx++) {{
    const close = closes[idx];

    if (trend === 0) {{
      if (close >= closes[highIdx]) highIdx = idx;
      if (close <= closes[lowIdx]) lowIdx = idx;

      const hasEnoughRange = closes[highIdx] / closes[lowIdx] - 1 >= reversalThreshold;
      if (!hasEnoughRange) continue;

      if (lowIdx < highIdx) {{
        addPivot(lowIdx, "low", "起点低点");
        trend = 1;
      }} else {{
        addPivot(highIdx, "high", "起点高点");
        trend = -1;
      }}
      continue;
    }}

    if (trend > 0) {{
      if (close >= closes[highIdx]) {{
        highIdx = idx;
        continue;
      }}
      const drawdown = (closes[highIdx] - close) / closes[highIdx];
      if (drawdown >= reversalThreshold) {{
        addPivot(highIdx, "high", "确认高点");
        trend = -1;
        lowIdx = idx;
      }}
      continue;
    }}

    if (close <= closes[lowIdx]) {{
      lowIdx = idx;
      continue;
    }}
    const rebound = (close - closes[lowIdx]) / closes[lowIdx];
    if (rebound >= reversalThreshold) {{
      addPivot(lowIdx, "low", "确认低点");
      trend = 1;
      highIdx = idx;
    }}
  }}

  if (trend === 0) {{
    addPivot(0, "flat", "起点/横盘");
  }} else {{
    const lastIdx = trend > 0 ? highIdx : lowIdx;
    addPivot(lastIdx, trend > 0 ? "high" : "low", trend > 0 ? "末段高点" : "末段低点");
  }}

  return pivots.map((pivot, index) => ({{ ...pivot, sequence: index + 1 }}));
}}

function annualizedReturn(finalValue) {{
  const days = Math.max(1, (payload.last.time - payload.first.time) / 86400000);
  return (Math.pow(finalValue, 365.25 / days) - 1) * 100;
}}

function maxDrawdownFromCurve(curve) {{
  let peak = curve[0]?.equity || 1;
  let maxDrawdown = 0;
  for (const point of curve) {{
    if (point.equity > peak) peak = point.equity;
    const drawdown = point.equity / peak - 1;
    if (drawdown < maxDrawdown) maxDrawdown = drawdown;
  }}
  return maxDrawdown * 100;
}}

function computeDrawdownEntryStrategy(stopPercent) {{
  const entryDrawdown = 0.20;
  let runningPeak = payload.points[0].close;
  let previousDrawdown = 0;
  let entryArmed = true;
  let holding = false;
  let cash = 1;
  let units = 0;
  let positionPeak = 0;
  const trades = [];
  const curve = [];

  for (const point of payload.points) {{
    if (point.close > runningPeak) runningPeak = point.close;
    const marketDrawdown = (runningPeak - point.close) / runningPeak;

    if (holding) {{
      if (point.close > positionPeak) positionPeak = point.close;
      const stopDrawdown = (positionPeak - point.close) / positionPeak;
      if (stopDrawdown >= stopPercent) {{
        cash = units * point.close;
        units = 0;
        holding = false;
        entryArmed = marketDrawdown < entryDrawdown;
        trades.push({{ action: "sell", trade_date: point.trade_date, close: point.close }});
      }}
    }} else {{
      const crossedEntry = entryArmed && marketDrawdown >= entryDrawdown && previousDrawdown < entryDrawdown;
      if (crossedEntry) {{
        units = cash / point.close;
        cash = 0;
        holding = true;
        positionPeak = point.close;
        entryArmed = false;
        trades.push({{ action: "buy", trade_date: point.trade_date, close: point.close }});
      }} else if (marketDrawdown < entryDrawdown) {{
        entryArmed = true;
      }}
    }}

    curve.push({{
      trade_date: point.trade_date,
      time: point.time,
      equity: holding ? units * point.close : cash,
    }});
    previousDrawdown = marketDrawdown;
  }}

  const finalValue = curve[curve.length - 1].equity;
  const holdFinalValue = payload.last.close / payload.first.close;
  const strategyAnnualized = annualizedReturn(finalValue);
  const holdAnnualized = annualizedReturn(holdFinalValue);
  const buyCount = trades.filter((trade) => trade.action === "buy").length;
  const sellCount = trades.filter((trade) => trade.action === "sell").length;
  return {{
    stopPercent,
    n: Math.round(stopPercent * 100),
    finalValue,
    totalReturn: (finalValue - 1) * 100,
    annualized: strategyAnnualized,
    holdAnnualized,
    excessAnnualized: strategyAnnualized - holdAnnualized,
    maxDrawdown: maxDrawdownFromCurve(curve),
    buyCount,
    sellCount,
    holding,
    trades,
    curve,
  }};
}}

function computeDrawdownStrategyGrid() {{
  const results = [];
  for (let n = 1; n <= 15; n++) {{
    results.push(computeDrawdownEntryStrategy(n / 100));
  }}
  return results;
}}

function drawdownCurveAsPricePoints(strategy) {{
  return strategy.curve.map((point) => ({{
    trade_date: point.trade_date,
    time: point.time,
    close: point.equity * payload.first.close,
    equity: point.equity,
  }}));
}}

function rollingLogRegressionAt(index, years, sigmaMultiple = 2) {{
  const endPoint = payload.points[index];
  const cutoff = endPoint.time - years * 365.25 * 86400000;
  const startIndex = payload.points.findIndex((point) => point.time >= cutoff);
  const from = startIndex < 0 ? 0 : startIndex;
  const train = payload.points.slice(from, index + 1);
  if (train.length < 60) return null;
  const n = train.length;
  const logs = train.map((point) => Math.log(point.close));
  const meanX = (n - 1) / 2;
  const meanY = logs.reduce((sum, value) => sum + value, 0) / n;
  let numerator = 0;
  let denominator = 0;
  for (let row = 0; row < n; row++) {{
    numerator += (row - meanX) * (logs[row] - meanY);
    denominator += Math.pow(row - meanX, 2);
  }}
  const slope = denominator === 0 ? 0 : numerator / denominator;
  const intercept = meanY - slope * meanX;
  const fittedValues = logs.map((_, row) => intercept + slope * row);
  const residuals = logs.map((value, row) => value - fittedValues[row]);
  const sigma = Math.sqrt(residuals.reduce((sum, value) => sum + value * value, 0) / Math.max(1, n - 2));
  const fitted = fittedValues[fittedValues.length - 1];
  return {{
    mid: Math.exp(fitted),
    lower: Math.exp(fitted - sigma * sigmaMultiple),
    upper: Math.exp(fitted + sigma * sigmaMultiple),
  }};
}}

function coreTargetAllocation(index, runningPeak) {{
  const point = payload.points[index];
  const drawdown = (runningPeak - point.close) / runningPeak;
  let target = 0.70;
  if (drawdown >= 0.20) target = 1.00;
  else if (drawdown >= 0.10) target = 0.80;

  const oneYearChannel = rollingLogRegressionAt(index, 1, 2);
  const twoYearChannel = rollingLogRegressionAt(index, 2, 2);
  if (oneYearChannel && point.close < oneYearChannel.mid) target = Math.min(target, 0.70);
  if (twoYearChannel && point.close < twoYearChannel.lower) target = Math.min(target, 0.50);
  return target;
}}

function computeCoreSatelliteStrategy() {{
  let equity = 1;
  let allocation = 0.70;
  let runningPeak = payload.points[0].close;
  let rebalanceCount = 0;
  let turnover = 0;
  const curve = [{{
    trade_date: payload.points[0].trade_date,
    time: payload.points[0].time,
    equity,
    allocation,
  }}];

  allocation = coreTargetAllocation(0, runningPeak);
  curve[0].allocation = allocation;

  for (let index = 1; index < payload.points.length; index++) {{
    const previous = payload.points[index - 1];
    const point = payload.points[index];
    const dailyReturn = point.close / previous.close - 1;
    equity *= 1 + allocation * dailyReturn;
    if (point.close > runningPeak) runningPeak = point.close;
    const nextAllocation = coreTargetAllocation(index, runningPeak);
    if (Math.abs(nextAllocation - allocation) > 1e-9) {{
      rebalanceCount += 1;
      turnover += Math.abs(nextAllocation - allocation);
      allocation = nextAllocation;
    }}
    curve.push({{
      trade_date: point.trade_date,
      time: point.time,
      equity,
      allocation,
    }});
  }}

  const holdFinalValue = payload.last.close / payload.first.close;
  const holdCurve = payload.points.map((point) => ({{
    trade_date: point.trade_date,
    time: point.time,
    equity: point.close / payload.first.close,
  }}));
  const strategyAnnualized = annualizedReturn(equity);
  const holdAnnualized = annualizedReturn(holdFinalValue);
  const strategyMaxDrawdown = maxDrawdownFromCurve(curve);
  const holdMaxDrawdown = maxDrawdownFromCurve(holdCurve);
  return {{
    finalValue: equity,
    totalReturn: (equity - 1) * 100,
    annualized: strategyAnnualized,
    holdAnnualized,
    excessAnnualized: strategyAnnualized - holdAnnualized,
    maxDrawdown: strategyMaxDrawdown,
    holdMaxDrawdown,
    calmar: strategyMaxDrawdown === 0 ? null : strategyAnnualized / Math.abs(strategyMaxDrawdown),
    holdCalmar: holdMaxDrawdown === 0 ? null : holdAnnualized / Math.abs(holdMaxDrawdown),
    rebalanceCount,
    turnover,
    currentAllocation: allocation,
    curve,
    holdCurve,
  }};
}}

function coreCurveAsPricePoints(strategy) {{
  return strategy.curve.map((point) => ({{
    trade_date: point.trade_date,
    time: point.time,
    close: point.equity * payload.first.close,
    equity: point.equity,
    allocation: point.allocation,
  }}));
}}

function computeAnalysis(reversalThreshold) {{
  const turningPoints = computeTurningPoints(payload.points, reversalThreshold);
  const turningHighs = turningPoints.filter((point) => point.turning_type === "high");
  const turningLows = turningPoints.filter((point) => point.turning_type === "low");
  return {{
    reversalThreshold,
    turningPoints,
    turningHighs,
    turningLows,
  }};
}}

function renderStats() {{
  const active = computeDrawdownEntryStrategy(Number(drawdownStopSlider.value) / 100);
  statsEl.innerHTML = `
    <div class="stat"><span class="label">最新点位</span><span class="value">${{fmt.format(payload.last.close)}}</span></div>
    <div class="stat"><span class="label">区间涨幅</span><span class="value">${{formatSignedPercent(payload.totalReturn)}}</span></div>
    <div class="stat"><span class="label">持有年化</span><span class="value">${{formatSignedPercent(active.holdAnnualized)}}</span></div>
    <div class="stat"><span class="label">20%策略年化</span><span class="value">${{formatSignedPercent(active.annualized)}}</span></div>
    <div class="stat"><span class="label">20%策略总收益</span><span class="value">${{formatSignedPercent(active.totalReturn)}}</span></div>
    <div class="stat"><span class="label">超额年化</span><span class="value">${{formatSignedPercent(active.excessAnnualized)}}</span></div>
    <div class="stat"><span class="label">最大回撤</span><span class="value">${{formatSignedPercent(active.maxDrawdown)}}</span></div>
    <div class="stat"><span class="label">交易 / 状态</span><span class="value">${{active.buyCount}}买${{active.sellCount}}卖<br>${{active.holding ? "持有" : "空仓"}}</span></div>
    <div class="stat"><span class="label">拐点总数</span><span class="value">${{currentAnalysis.turningPoints.length}}</span></div>
    <div class="stat"><span class="label">高点 / 低点</span><span class="value">${{currentAnalysis.turningHighs.length}} / ${{currentAnalysis.turningLows.length}}</span></div>
  `;
}}

function renderNotes() {{
  reversalValue.textContent = `${{pct.format(currentAnalysis.reversalThreshold * 100)}}%`;
  notesEl.innerHTML = `
    <p>${{payload.source}}，共 ${{payload.rows}} 条日线；基日 ${{payload.baseDate}}。</p>
    <p>背景层来自长期牛熊周期观察：浅红为牛市、浅绿为熊市；灰色虚线为上证指数背景曲线，使用独立归一化坐标，只辅助观察大盘环境，不改变自由现金流指数价格轴。</p>
    <p>当前回撤阈值：${{pct.format(currentAnalysis.reversalThreshold * 100)}}%。${{payload.note}}</p>
    <p>主图红线为 20% 回撤策略净值曲线，按“策略净值倍数 × 首日收盘点位”折算到同一坐标系，便于和指数收盘价、ZigZag 折线比较。</p>
    <p>折线中点线：按当前 Y 轴坐标取每段 ZigZag 折线的中点并连接；从第三段开始，用前两段中点连成的直线与当前段 ZigZag 折线求交，图上标签显示交点价格相对当前段中点价格的百分比差。</p>
    <p>ZigZag 拐点画在事后确认的高低点日期上，只作为形态观察，不再用于收益回测；页面收益统计只使用下方 20% 回撤买入策略和核心仓策略的无未来函数回测。</p>
  `;
}}

function drawDrawdownStrategyChart(grid, selectedN) {{
  if (!grid.length) return;
  const ratio = window.devicePixelRatio || 1;
  const rect = drawdownStrategyChart.getBoundingClientRect();
  const width = Math.max(320, Math.floor(rect.width));
  const height = Math.max(260, Math.floor(rect.height));
  drawdownStrategyChart.width = Math.floor(width * ratio);
  drawdownStrategyChart.height = Math.floor(height * ratio);
  drawdownCtx.setTransform(ratio, 0, 0, ratio, 0, 0);
  drawdownCtx.clearRect(0, 0, width, height);
  drawdownCtx.fillStyle = "#ffffff";
  drawdownCtx.fillRect(0, 0, width, height);

  const margin = {{ left: 58, right: 18, top: 34, bottom: 42 }};
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;
  const values = grid.map((item) => item.annualized);
  const holdAnnualized = grid[0].holdAnnualized;
  const minValue = Math.min(0, holdAnnualized, ...values);
  const maxValue = Math.max(0, holdAnnualized, ...values);
  const pad = Math.max(1, (maxValue - minValue) * 0.12);
  const lo = minValue - pad;
  const hi = maxValue + pad;
  const y = (value) => margin.top + ((hi - value) / Math.max(1e-9, hi - lo)) * plotH;
  const barGap = 8;
  const barW = Math.max(10, (plotW - barGap * (grid.length - 1)) / grid.length);
  const zeroY = y(0);

  drawdownCtx.strokeStyle = "#d8dee8";
  drawdownCtx.lineWidth = 1;
  drawdownCtx.fillStyle = "#66717f";
  drawdownCtx.font = "12px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
  drawdownCtx.textAlign = "right";
  drawdownCtx.textBaseline = "middle";
  for (let i = 0; i <= 4; i++) {{
    const value = lo + ((hi - lo) * i) / 4;
    const yy = y(value);
    drawdownCtx.beginPath();
    drawdownCtx.moveTo(margin.left, yy);
    drawdownCtx.lineTo(width - margin.right, yy);
    drawdownCtx.stroke();
    drawdownCtx.fillText(`${{pct.format(value)}}%`, margin.left - 8, yy);
  }}

  drawdownCtx.strokeStyle = "#9aa5b2";
  drawdownCtx.setLineDash([5, 4]);
  drawdownCtx.beginPath();
  drawdownCtx.moveTo(margin.left, y(holdAnnualized));
  drawdownCtx.lineTo(width - margin.right, y(holdAnnualized));
  drawdownCtx.stroke();
  drawdownCtx.setLineDash([]);
  drawdownCtx.fillStyle = "#17202a";
  drawdownCtx.textAlign = "left";
  drawdownCtx.textBaseline = "bottom";
  drawdownCtx.fillText(`持有年化 ${{formatSignedPercent(holdAnnualized)}}`, margin.left + 4, y(holdAnnualized) - 4);

  grid.forEach((item, index) => {{
    const x = margin.left + index * (barW + barGap);
    const yy = y(item.annualized);
    const top = Math.min(yy, zeroY);
    const bottom = Math.max(yy, zeroY);
    drawdownCtx.fillStyle = item.n === selectedN ? "#1f7a68" : item.annualized >= 0 ? "#8fb8ad" : "#b45f06";
    drawdownCtx.fillRect(x, top, barW, Math.max(1, bottom - top));
    drawdownCtx.fillStyle = "#66717f";
    drawdownCtx.textAlign = "center";
    drawdownCtx.textBaseline = "top";
    drawdownCtx.fillText(String(item.n), x + barW / 2, height - margin.bottom + 15);
  }});

  drawdownCtx.fillStyle = "#17202a";
  drawdownCtx.font = "13px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
  drawdownCtx.textAlign = "left";
  drawdownCtx.textBaseline = "top";
  drawdownCtx.fillText("n=1~15 年化收益", margin.left, 8);
  drawdownCtx.fillStyle = "#66717f";
  drawdownCtx.textAlign = "center";
  drawdownCtx.fillText("高点回落 n%", margin.left + plotW / 2, height - 18);
}}

function renderDrawdownStrategy() {{
  const selectedN = Number(drawdownStopSlider.value);
  drawdownStopValue.textContent = `${{selectedN}}%`;
  currentDrawdownGrid = computeDrawdownStrategyGrid();
  const active = currentDrawdownGrid.find((item) => item.n === selectedN) || currentDrawdownGrid[0];
  drawdownStrategySummary.innerHTML = `
    <div class="strategy-metric"><span class="label">当前 n</span><span class="value">${{selectedN}}%</span></div>
    <div class="strategy-metric"><span class="label">20%策略年化</span><span class="value">${{formatSignedPercent(active.annualized)}}</span></div>
    <div class="strategy-metric"><span class="label">超额年化</span><span class="value">${{formatSignedPercent(active.excessAnnualized)}}</span></div>
    <div class="strategy-metric"><span class="label">最大回撤</span><span class="value">${{formatSignedPercent(active.maxDrawdown)}}</span></div>
    <div class="strategy-metric"><span class="label">交易 / 状态</span><span class="value">${{active.buyCount}}买${{active.sellCount}}卖<br>${{active.holding ? "持有" : "空仓"}}</span></div>
  `;
  drawDrawdownStrategyChart(currentDrawdownGrid, selectedN);
}}

function drawCoreStrategyChart(strategy) {{
  const ratio = window.devicePixelRatio || 1;
  const rect = coreStrategyChart.getBoundingClientRect();
  const width = Math.max(320, Math.floor(rect.width));
  const height = Math.max(260, Math.floor(rect.height));
  coreStrategyChart.width = Math.floor(width * ratio);
  coreStrategyChart.height = Math.floor(height * ratio);
  coreCtx.setTransform(ratio, 0, 0, ratio, 0, 0);
  coreCtx.clearRect(0, 0, width, height);
  coreCtx.fillStyle = "#ffffff";
  coreCtx.fillRect(0, 0, width, height);

  const margin = {{ left: 58, right: 18, top: 34, bottom: 42 }};
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;
  const values = strategy.curve.map((point) => point.equity).concat(strategy.holdCurve.map((point) => point.equity));
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const pad = Math.max(0.05, (maxValue - minValue) * 0.10);
  const lo = Math.max(0.01, minValue - pad);
  const hi = maxValue + pad;
  const minTime = payload.first.time;
  const maxTime = payload.last.time;
  const x = (time) => margin.left + ((time - minTime) / Math.max(1, maxTime - minTime)) * plotW;
  const y = (value) => margin.top + ((hi - value) / Math.max(1e-9, hi - lo)) * plotH;

  coreCtx.strokeStyle = "#d8dee8";
  coreCtx.lineWidth = 1;
  coreCtx.fillStyle = "#66717f";
  coreCtx.font = "12px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
  coreCtx.textAlign = "right";
  coreCtx.textBaseline = "middle";
  for (let i = 0; i <= 4; i++) {{
    const value = lo + ((hi - lo) * i) / 4;
    const yy = y(value);
    coreCtx.beginPath();
    coreCtx.moveTo(margin.left, yy);
    coreCtx.lineTo(width - margin.right, yy);
    coreCtx.stroke();
    coreCtx.fillText(`${{fmt.format(value)}}x`, margin.left - 8, yy);
  }}

  const drawCurve = (points, color, widthPx, dash = []) => {{
    coreCtx.save();
    coreCtx.strokeStyle = color;
    coreCtx.lineWidth = widthPx;
    coreCtx.setLineDash(dash);
    coreCtx.beginPath();
    points.forEach((point, index) => {{
      const xx = x(point.time);
      const yy = y(point.equity);
      if (index === 0) coreCtx.moveTo(xx, yy);
      else coreCtx.lineTo(xx, yy);
    }});
    coreCtx.stroke();
    coreCtx.restore();
  }};
  drawCurve(strategy.holdCurve, "#9aa5b2", 1.5, [6, 4]);
  drawCurve(strategy.curve, "#0f67b1", 2.1);

  coreCtx.fillStyle = "#17202a";
  coreCtx.textAlign = "left";
  coreCtx.textBaseline = "top";
  coreCtx.font = "13px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
  coreCtx.fillText("核心仓策略净值 vs 满仓持有", margin.left, 8);
  coreCtx.fillStyle = "#0f67b1";
  coreCtx.fillText("核心仓", margin.left + 190, 8);
  coreCtx.fillStyle = "#66717f";
  coreCtx.fillText("满仓持有", margin.left + 252, 8);

  coreCtx.textAlign = "center";
  coreCtx.textBaseline = "top";
  const tickCount = 6;
  for (let i = 0; i < tickCount; i++) {{
    const time = minTime + ((maxTime - minTime) * i) / Math.max(1, tickCount - 1);
    coreCtx.fillStyle = "#66717f";
    coreCtx.fillText(new Date(time).toISOString().slice(0, 7), x(time), height - margin.bottom + 15);
  }}
}}

function renderCoreStrategy() {{
  const strategy = computeCoreSatelliteStrategy();
  coreStrategySummary.innerHTML = `
    <div class="strategy-metric"><span class="label">策略年化</span><span class="value">${{formatSignedPercent(strategy.annualized)}}</span></div>
    <div class="strategy-metric"><span class="label">持有年化</span><span class="value">${{formatSignedPercent(strategy.holdAnnualized)}}</span></div>
    <div class="strategy-metric"><span class="label">超额年化</span><span class="value">${{formatSignedPercent(strategy.excessAnnualized)}}</span></div>
    <div class="strategy-metric"><span class="label">策略最大回撤</span><span class="value">${{formatSignedPercent(strategy.maxDrawdown)}}</span></div>
    <div class="strategy-metric"><span class="label">持有最大回撤</span><span class="value">${{formatSignedPercent(strategy.holdMaxDrawdown)}}</span></div>
    <div class="strategy-metric"><span class="label">策略 Calmar</span><span class="value">${{strategy.calmar === null ? "NA" : fmt.format(strategy.calmar)}}</span></div>
    <div class="strategy-metric"><span class="label">持有 Calmar</span><span class="value">${{strategy.holdCalmar === null ? "NA" : fmt.format(strategy.holdCalmar)}}</span></div>
    <div class="strategy-metric"><span class="label">当前仓位</span><span class="value">${{pct.format(strategy.currentAllocation * 100)}}%</span></div>
    <div class="strategy-metric"><span class="label">调仓次数</span><span class="value">${{strategy.rebalanceCount}}</span></div>
    <div class="strategy-metric"><span class="label">累计换手</span><span class="value">${{pct.format(strategy.turnover * 100)}}%</span></div>
  `;
  drawCoreStrategyChart(strategy);
}}

function updateAnalysis() {{
  currentAnalysis = computeAnalysis(currentReversal);
  renderStats();
  renderNotes();
  tip.style.display = "none";
  draw();
}}

function extent(values) {{
  return [Math.min(...values), Math.max(...values)];
}}

function activeIndicatorIds() {{
  return indicatorInputs.filter((input) => input.checked).map((input) => input.dataset.indicator);
}}

function makeSeriesPoint(source, close) {{
  return {{
    trade_date: source.trade_date,
    time: source.time,
    close,
  }};
}}

function computeSmaChannel(period, multiplier) {{
  const mid = [];
  const upper = [];
  const lower = [];
  const closes = payload.points.map((point) => point.close);
  for (let index = period - 1; index < payload.points.length; index++) {{
    const window = closes.slice(index - period + 1, index + 1);
    const mean = window.reduce((sum, value) => sum + value, 0) / period;
    const variance = window.reduce((sum, value) => sum + Math.pow(value - mean, 2), 0) / period;
    const deviation = Math.sqrt(variance);
    const source = payload.points[index];
    mid.push(makeSeriesPoint(source, mean));
    upper.push(makeSeriesPoint(source, mean + deviation * multiplier));
    lower.push(makeSeriesPoint(source, mean - deviation * multiplier));
  }}
  return {{ mid, upper, lower }};
}}

function computeMaEnvelope(period, envelopePct) {{
  const mid = [];
  const upper = [];
  const lower = [];
  const closes = payload.points.map((point) => point.close);
  for (let index = period - 1; index < payload.points.length; index++) {{
    const window = closes.slice(index - period + 1, index + 1);
    const mean = window.reduce((sum, value) => sum + value, 0) / period;
    const source = payload.points[index];
    mid.push(makeSeriesPoint(source, mean));
    upper.push(makeSeriesPoint(source, mean * (1 + envelopePct)));
    lower.push(makeSeriesPoint(source, mean * (1 - envelopePct)));
  }}
  return {{ mid, upper, lower }};
}}

function computeKeltnerChannel(period, multiplier) {{
  const mid = [];
  const upper = [];
  const lower = [];
  const alpha = 2 / (period + 1);
  let emaClose = payload.points[0].close;
  let emaAtr = Math.max(payload.points[0].high - payload.points[0].low, 0);
  for (let index = 0; index < payload.points.length; index++) {{
    const point = payload.points[index];
    const previousClose = index > 0 ? payload.points[index - 1].close : point.close;
    const trueRange = Math.max(
      point.high - point.low,
      Math.abs(point.high - previousClose),
      Math.abs(point.low - previousClose)
    );
    emaClose = index === 0 ? point.close : alpha * point.close + (1 - alpha) * emaClose;
    emaAtr = index === 0 ? trueRange : alpha * trueRange + (1 - alpha) * emaAtr;
    if (index < period - 1) continue;
    mid.push(makeSeriesPoint(point, emaClose));
    upper.push(makeSeriesPoint(point, emaClose + emaAtr * multiplier));
    lower.push(makeSeriesPoint(point, Math.max(0.01, emaClose - emaAtr * multiplier)));
  }}
  return {{ mid, upper, lower }};
}}

function computeDonchianChannel(period) {{
  const mid = [];
  const upper = [];
  const lower = [];
  for (let index = period - 1; index < payload.points.length; index++) {{
    const window = payload.points.slice(index - period + 1, index + 1);
    const channelHigh = Math.max(...window.map((point) => point.high));
    const channelLow = Math.min(...window.map((point) => point.low));
    const source = payload.points[index];
    mid.push(makeSeriesPoint(source, (channelHigh + channelLow) / 2));
    upper.push(makeSeriesPoint(source, channelHigh));
    lower.push(makeSeriesPoint(source, channelLow));
  }}
  return {{ mid, upper, lower }};
}}

function computeLogRegressionChannel(deviationMultiplier) {{
  const n = payload.points.length;
  if (n < 3) return {{ mid: [], upper: [], lower: [] }};
  const logCloses = payload.points.map((point) => Math.log(point.close));
  const meanX = (n - 1) / 2;
  const meanY = logCloses.reduce((sum, value) => sum + value, 0) / n;
  let numerator = 0;
  let denominator = 0;
  for (let index = 0; index < n; index++) {{
    numerator += (index - meanX) * (logCloses[index] - meanY);
    denominator += Math.pow(index - meanX, 2);
  }}
  const slope = denominator === 0 ? 0 : numerator / denominator;
  const intercept = meanY - slope * meanX;
  const residuals = logCloses.map((value, index) => value - (intercept + slope * index));
  const residualStd = Math.sqrt(residuals.reduce((sum, value) => sum + value * value, 0) / Math.max(1, n - 2));
  const mid = [];
  const upper = [];
  const lower = [];
  for (let index = 0; index < n; index++) {{
    const source = payload.points[index];
    const fitted = intercept + slope * index;
    mid.push(makeSeriesPoint(source, Math.exp(fitted)));
    upper.push(makeSeriesPoint(source, Math.exp(fitted + residualStd * deviationMultiplier)));
    lower.push(makeSeriesPoint(source, Math.exp(fitted - residualStd * deviationMultiplier)));
  }}
  return {{ mid, upper, lower }};
}}

function computeZigzagChannel() {{
  return {{
    upper: currentAnalysis.turningHighs,
    lower: currentAnalysis.turningLows,
  }};
}}

function computeVisibleIndicatorSets() {{
  const ids = new Set(activeIndicatorIds());
  const sets = [];
  if (ids.has("logRegression")) {{
    const channel = computeLogRegressionChannel(2);
    sets.push({{
      id: "logRegression",
      lines: [
        {{ points: channel.upper, color: "#6c4ab6", width: 1.2, dash: [5, 5] }},
        {{ points: channel.mid, color: "#6c4ab6", width: 1.8, dash: [] }},
        {{ points: channel.lower, color: "#6c4ab6", width: 1.2, dash: [5, 5] }},
      ],
    }});
  }}
  if (ids.has("bollinger")) {{
    const channel = computeSmaChannel(20, 2);
    sets.push({{
      id: "bollinger",
      lines: [
        {{ points: channel.upper, color: "#c44e52", width: 1.1, dash: [4, 4] }},
        {{ points: channel.mid, color: "#c44e52", width: 1.4, dash: [] }},
        {{ points: channel.lower, color: "#c44e52", width: 1.1, dash: [4, 4] }},
      ],
    }});
  }}
  if (ids.has("keltner")) {{
    const channel = computeKeltnerChannel(20, 2);
    sets.push({{
      id: "keltner",
      lines: [
        {{ points: channel.upper, color: "#dd8452", width: 1.1, dash: [6, 4] }},
        {{ points: channel.mid, color: "#dd8452", width: 1.4, dash: [] }},
        {{ points: channel.lower, color: "#dd8452", width: 1.1, dash: [6, 4] }},
      ],
    }});
  }}
  if (ids.has("donchian")) {{
    const channel = computeDonchianChannel(20);
    sets.push({{
      id: "donchian",
      lines: [
        {{ points: channel.upper, color: "#4c72b0", width: 1.2, dash: [3, 5] }},
        {{ points: channel.mid, color: "#4c72b0", width: 1.2, dash: [8, 4] }},
        {{ points: channel.lower, color: "#4c72b0", width: 1.2, dash: [3, 5] }},
      ],
    }});
  }}
  if (ids.has("maEnvelope")) {{
    const channel = computeMaEnvelope(20, 0.05);
    sets.push({{
      id: "maEnvelope",
      lines: [
        {{ points: channel.upper, color: "#8172b2", width: 1.1, dash: [5, 3] }},
        {{ points: channel.mid, color: "#8172b2", width: 1.4, dash: [] }},
        {{ points: channel.lower, color: "#8172b2", width: 1.1, dash: [5, 3] }},
      ],
    }});
  }}
  if (ids.has("zigzagChannel")) {{
    const channel = computeZigzagChannel();
    sets.push({{
      id: "zigzagChannel",
      lines: [
        {{ points: channel.upper, color: "#64a12d", width: 1.5, dash: [8, 5] }},
        {{ points: channel.lower, color: "#64a12d", width: 1.5, dash: [8, 5] }},
      ],
    }});
  }}
  return sets;
}}

function axisValue(close) {{
  if (currentScale === "percent") return (close / payload.first.close - 1) * 100;
  if (currentScale === "log") return Math.log(close);
  return close;
}}

function axisLabel(value) {{
  if (currentScale === "percent") return `${{pct.format(value)}}%`;
  if (currentScale === "log") return fmt.format(Math.exp(value));
  return fmt.format(value);
}}

function closeFromAxisValue(value) {{
  if (currentScale === "percent") return payload.first.close * (1 + value / 100);
  if (currentScale === "log") return Math.exp(value);
  return value;
}}

function formatSegmentChange(fromPoint, toPoint) {{
  const change = (toPoint.close / fromPoint.close - 1) * 100;
  const sign = change > 0 ? "+" : "";
  return `${{sign}}${{pct.format(change)}}%`;
}}

function computeZigzagSegmentMidpoints(points) {{
  const midpoints = [];
  for (let index = 1; index < points.length; index++) {{
    const fromPoint = points[index - 1];
    const toPoint = points[index];
    const midpointAxisValue = (axisValue(fromPoint.close) + axisValue(toPoint.close)) / 2;
    midpoints.push({{
      sequence: index,
      segmentIndex: index - 1,
      trade_date: `${{fromPoint.trade_date}}~${{toPoint.trade_date}}`,
      time: (fromPoint.time + toPoint.time) / 2,
      close: closeFromAxisValue(midpointAxisValue),
      fromPoint,
      toPoint,
    }});
  }}
  return midpoints;
}}

function toGeometryPoint(point) {{
  return {{
    x: point.time,
    y: axisValue(point.close),
  }};
}}

function lineSegmentIntersection(lineA, lineB, segmentA, segmentB) {{
  const a = toGeometryPoint(lineA);
  const b = toGeometryPoint(lineB);
  const c = toGeometryPoint(segmentA);
  const d = toGeometryPoint(segmentB);
  const lineX = b.x - a.x;
  const lineY = b.y - a.y;
  const segX = d.x - c.x;
  const segY = d.y - c.y;
  const denom = lineX * segY - lineY * segX;
  if (Math.abs(denom) < 1e-9) return null;
  const cx = c.x - a.x;
  const cy = c.y - a.y;
  const t = (cx * segY - cy * segX) / denom;
  const u = (cx * lineY - cy * lineX) / denom;
  if (u < -1e-6 || u > 1 + 1e-6) return null;
  const axis = c.y + u * segY;
  return {{
    time: a.x + t * lineX,
    close: closeFromAxisValue(axis),
    axis,
    lineRatio: t,
    segmentRatio: u,
  }};
}}

function computeMidpointIntersections(turningPoints, midpoints) {{
  const intersections = [];
  for (let index = 2; index < midpoints.length; index++) {{
    const lineStart = midpoints[index - 2];
    const lineEnd = midpoints[index - 1];
    const segmentStart = turningPoints[index];
    const segmentEnd = turningPoints[index + 1];
    if (!segmentStart || !segmentEnd) continue;
    const intersection = lineSegmentIntersection(lineStart, lineEnd, segmentStart, segmentEnd);
    if (!intersection) continue;
    const targetMidpoint = midpoints[index];
    const diffPct = (intersection.close / targetMidpoint.close - 1) * 100;
    intersections.push({{
      sequence: index - 1,
      lineStart,
      lineEnd,
      segmentStart,
      segmentEnd,
      targetMidpoint,
      intersection,
      diffPct,
    }});
  }}
  return intersections;
}}

function resizeCanvas() {{
  const ratio = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = Math.floor(rect.width * ratio);
  canvas.height = Math.floor(rect.height * ratio);
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  draw();
}}

function drawLine(points, x, y, color, width, dash = []) {{
  if (!points.length) return;
  ctx.save();
  ctx.setLineDash(dash);
  ctx.beginPath();
  points.forEach((point, index) => {{
    const xx = x(point.time);
    const yy = y(point.close);
    if (index === 0) ctx.moveTo(xx, yy);
    else ctx.lineTo(xx, yy);
  }});
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.stroke();
  ctx.restore();
}}

function drawMarketBackground(x, minTime, maxTime, plotLeft, plotRight, plotTop, plotBottom) {{
  ctx.save();
  for (const block of marketContext.cycleBlocks) {{
    const start = Math.max(block.startTime, minTime);
    const end = Math.min(block.endTime, maxTime);
    if (end <= start) continue;
    const x0 = clamp(x(start), plotLeft, plotRight);
    const x1 = clamp(x(end), plotLeft, plotRight);
    if (x1 <= x0) continue;
    ctx.fillStyle = block.state === "bull" ? "rgba(199, 61, 61, 0.105)" : "rgba(23, 136, 91, 0.105)";
    ctx.fillRect(x0, plotTop, x1 - x0, plotBottom - plotTop);
  }}

  const indexPoints = marketContext.series.filter((point) => point.time >= minTime && point.time <= maxTime);
  if (indexPoints.length >= 2) {{
    const values = indexPoints.map((point) => Math.log(point.close));
    const minValue = Math.min(...values);
    const maxValue = Math.max(...values);
    const spread = maxValue - minValue || 1;
    const yIndex = (close) => plotBottom - ((Math.log(close) - minValue) / spread) * (plotBottom - plotTop);
    ctx.beginPath();
    indexPoints.forEach((point, index) => {{
      const xx = x(point.time);
      const yy = yIndex(point.close);
      if (index === 0) ctx.moveTo(xx, yy);
      else ctx.lineTo(xx, yy);
    }});
    ctx.strokeStyle = "rgba(75, 85, 99, 0.34)";
    ctx.lineWidth = 1.8;
    ctx.setLineDash([7, 5]);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = "rgba(75, 85, 99, 0.74)";
    ctx.font = "12px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
    ctx.textAlign = "right";
    ctx.textBaseline = "top";
    ctx.fillText("上证背景（独立归一化）", plotRight - 8, plotTop + 8);
  }}
  ctx.restore();
}}

function indicatorValues(indicatorSets) {{
  return indicatorSets.flatMap((set) =>
    set.lines.flatMap((line) => line.points.map((point) => Number(point.close)).filter((value) => Number.isFinite(value)))
  );
}}

function drawIndicatorSets(indicatorSets, x, y) {{
  for (const set of indicatorSets) {{
    for (const line of set.lines) {{
      drawLine(line.points, x, y, line.color, line.width, line.dash);
    }}
  }}
}}

function clamp(value, min, max) {{
  return Math.max(min, Math.min(max, value));
}}

function drawMidpointMarkers(points, x, y) {{
  for (const point of points) {{
    const xx = x(point.time);
    const yy = y(point.close);
    ctx.fillStyle = "#d9892b";
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 1.1;
    ctx.beginPath();
    ctx.arc(xx, yy, 3.4, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
  }}
}}

function drawMidpointIntersections(intersections, x, y) {{
  if (!intersections.length) return;
  ctx.save();
  ctx.strokeStyle = "rgba(138, 111, 209, 0.58)";
  ctx.lineWidth = 1.1;
  ctx.setLineDash([4, 5]);
  for (const item of intersections) {{
    ctx.beginPath();
    ctx.moveTo(x(item.lineStart.time), y(item.lineStart.close));
    ctx.lineTo(x(item.intersection.time), y(item.intersection.close));
    ctx.stroke();
  }}
  ctx.setLineDash([]);
  for (const item of intersections) {{
    const xx = x(item.intersection.time);
    const yy = y(item.intersection.close);
    ctx.strokeStyle = "#8a6fd1";
    ctx.lineWidth = 1.8;
    ctx.beginPath();
    ctx.moveTo(xx - 4.4, yy - 4.4);
    ctx.lineTo(xx + 4.4, yy + 4.4);
    ctx.moveTo(xx + 4.4, yy - 4.4);
    ctx.lineTo(xx - 4.4, yy + 4.4);
    ctx.stroke();
  }}
  ctx.restore();
}}

function drawMidpointIntersectionLabels(intersections, x, y, plotLeft, plotRight, plotTop, plotBottom) {{
  if (!intersections.length) return;
  ctx.font = "12px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  const placedBoxes = [];
  const overlaps = (box) => placedBoxes.some((item) => !(
    box.right < item.left || box.left > item.right || box.bottom < item.top || box.top > item.bottom
  ));
  for (const item of intersections) {{
    const label = `交点-中点 ${{formatSignedPercent(item.diffPct)}}`;
    const textWidth = ctx.measureText(label).width;
    const boxW = textWidth + 12;
    const boxH = 20;
    const anchorX = x(item.intersection.time);
    const anchorY = y(item.intersection.close);
    const direction = item.diffPct >= 0 ? -1 : 1;
    const yOffsets = [22, 44, 66, 88, 110].map((value) => value * direction);
    const xOffsets = [0, 46, -46, 92, -92, 138, -138];
    let xx = clamp(anchorX, plotLeft + boxW / 2, plotRight - boxW / 2);
    let yy = clamp(anchorY + yOffsets[0], plotTop + boxH / 2, plotBottom - boxH / 2);
    let chosenBox = null;
    for (const yOffset of yOffsets) {{
      for (const xOffset of xOffsets) {{
        const candidateX = clamp(anchorX + xOffset, plotLeft + boxW / 2, plotRight - boxW / 2);
        const candidateY = clamp(anchorY + yOffset, plotTop + boxH / 2, plotBottom - boxH / 2);
        const box = {{
          left: candidateX - boxW / 2 - 4,
          right: candidateX + boxW / 2 + 4,
          top: candidateY - boxH / 2 - 3,
          bottom: candidateY + boxH / 2 + 3,
        }};
        if (!overlaps(box)) {{
          xx = candidateX;
          yy = candidateY;
          chosenBox = box;
          break;
        }}
      }}
      if (chosenBox) break;
    }}
    if (!chosenBox) {{
      chosenBox = {{
        left: xx - boxW / 2 - 4,
        right: xx + boxW / 2 + 4,
        top: yy - boxH / 2 - 3,
        bottom: yy + boxH / 2 + 3,
      }};
    }}
    placedBoxes.push(chosenBox);
    ctx.fillStyle = "rgba(255, 255, 255, 0.9)";
    ctx.strokeStyle = "rgba(138, 111, 209, 0.45)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.roundRect(xx - boxW / 2, yy - boxH / 2, boxW, boxH, 5);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = "#6f55bd";
    ctx.fillText(label, xx, yy + 0.5);
  }}
}}

function drawSegmentLabels(points, x, y, plotLeft, plotRight, plotTop, plotBottom) {{
  if (points.length < 2) return;
  ctx.font = "12px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  const placedBoxes = [];
  const overlaps = (box) => placedBoxes.some((item) => !(
    box.right < item.left || box.left > item.right || box.bottom < item.top || box.top > item.bottom
  ));
  for (let index = 1; index < points.length; index++) {{
    const fromPoint = points[index - 1];
    const toPoint = points[index];
    const change = (toPoint.close / fromPoint.close - 1) * 100;
    const label = formatSegmentChange(fromPoint, toPoint);
    const anchorX = x(toPoint.time);
    const anchorY = y(toPoint.close);
    const textWidth = ctx.measureText(label).width;
    const padX = 6;
    const boxW = textWidth + padX * 2;
    const boxH = 20;
    const direction = change >= 0 ? -1 : 1;
    const yOffsets = [26, 48, 70, 92, 114, 136, 158].map((value) => value * direction);
    const xOffsets = [0, -44, 44, -88, 88, -132, 132];
    let xx = clamp(anchorX, plotLeft + boxW / 2, plotRight - boxW / 2);
    let yy = clamp(anchorY + yOffsets[0], plotTop + boxH / 2, plotBottom - boxH / 2);
    let chosenBox = null;
    for (const yOffset of yOffsets) {{
      for (const xOffset of xOffsets) {{
        const candidateX = clamp(anchorX + xOffset, plotLeft + boxW / 2, plotRight - boxW / 2);
        const candidateY = clamp(anchorY + yOffset, plotTop + boxH / 2, plotBottom - boxH / 2);
        const box = {{
          left: candidateX - boxW / 2 - 3,
          right: candidateX + boxW / 2 + 3,
          top: candidateY - boxH / 2 - 2,
          bottom: candidateY + boxH / 2 + 2,
        }};
        if (!overlaps(box)) {{
          xx = candidateX;
          yy = candidateY;
          chosenBox = box;
          break;
        }}
      }}
      if (chosenBox) break;
    }}
    if (!chosenBox) {{
      chosenBox = {{
        left: xx - boxW / 2 - 2,
        right: xx + boxW / 2 + 2,
        top: yy - boxH / 2 - 2,
        bottom: yy + boxH / 2 + 2,
      }};
    }}
    placedBoxes.push(chosenBox);
    ctx.fillStyle = "rgba(255, 255, 255, 0.88)";
    ctx.strokeStyle = change >= 0 ? "rgba(180, 95, 6, 0.35)" : "rgba(39, 95, 159, 0.35)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.roundRect(xx - boxW / 2, yy - boxH / 2, boxW, boxH, 5);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = change >= 0 ? "#8f4a05" : "#275f9f";
    ctx.fillText(label, xx, yy + 0.5);
  }}
}}

function drawTurningMarkers(points, x, y) {{
  for (const point of points) {{
    const xx = x(point.time);
    const yy = y(point.close);
    const isHigh = point.turning_type === "high";
    const isLow = point.turning_type === "low";
    const color = isHigh ? "#b45f06" : isLow ? "#275f9f" : "#3d4752";
    ctx.fillStyle = color;
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 1.3;
    ctx.beginPath();
    if (isLow) {{
      ctx.moveTo(xx, yy - 4.6);
      ctx.lineTo(xx + 4.6, yy);
      ctx.lineTo(xx, yy + 4.6);
      ctx.lineTo(xx - 4.6, yy);
      ctx.closePath();
    }} else if (isHigh) {{
      ctx.arc(xx, yy, 4, 0, Math.PI * 2);
    }} else {{
      ctx.rect(xx - 3.5, yy - 3.5, 7, 7);
    }}
    ctx.fill();
    ctx.stroke();
  }}
}}

function draw(activeTime = null) {{
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  const margin = {{ left: 64, right: 24, top: 28, bottom: 46 }};
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;
  const indicatorSets = computeVisibleIndicatorSets();
  const drawdownStrategy = computeDrawdownEntryStrategy(Number(drawdownStopSlider.value) / 100);
  const drawdownCurve = drawdownCurveAsPricePoints(drawdownStrategy);
  const coreStrategy = computeCoreSatelliteStrategy();
  const coreCurve = coreCurveAsPricePoints(coreStrategy);
  const zigzagMidpoints = computeZigzagSegmentMidpoints(currentAnalysis.turningPoints);
  const midpointIntersections = computeMidpointIntersections(currentAnalysis.turningPoints, zigzagMidpoints);
  const [minTime, maxTime] = extent(payload.points.map((p) => p.time));
  const visibleValues = payload.points.map((p) => p.close)
    .concat(indicatorValues(indicatorSets))
    .concat(drawdownCurve.map((point) => point.close))
    .concat(coreCurve.map((point) => point.close))
    .concat(zigzagMidpoints.map((point) => point.close))
    .concat(midpointIntersections.map((item) => item.intersection.close));
  const [minValue, maxValue] = extent(visibleValues.map((value) => axisValue(value)));
  const pad = (maxValue - minValue) * 0.08 || 1;
  const lo = minValue - pad;
  const hi = maxValue + pad;
  const x = (time) => margin.left + ((time - minTime) / Math.max(1, maxTime - minTime)) * plotW;
  const y = (close) => margin.top + ((hi - axisValue(close)) / (hi - lo)) * plotH;

  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, width, height);
  drawMarketBackground(x, minTime, maxTime, margin.left, width - margin.right, margin.top, height - margin.bottom);

  ctx.strokeStyle = "#d8dee8";
  ctx.lineWidth = 1;
  ctx.fillStyle = "#66717f";
  ctx.font = "12px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  for (let i = 0; i <= 5; i++) {{
    const value = lo + ((hi - lo) * i) / 5;
    const yy = margin.top + ((hi - value) / (hi - lo)) * plotH;
    ctx.beginPath();
    ctx.moveTo(margin.left, yy);
    ctx.lineTo(width - margin.right, yy);
    ctx.stroke();
    ctx.fillText(axisLabel(value), margin.left - 10, yy);
  }}

  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  const tickCount = 6;
  for (let i = 0; i < tickCount; i++) {{
    const time = minTime + ((maxTime - minTime) * i) / Math.max(1, tickCount - 1);
    const label = new Date(time).toISOString().slice(0, 7);
    ctx.fillText(label, x(time), height - margin.bottom + 18);
  }}

  drawIndicatorSets(indicatorSets, x, y);
  drawLine(payload.points, x, y, "#1f7a68", 2.2);
  drawLine(drawdownCurve, x, y, "#c44e52", 1.8);
  drawLine(coreCurve, x, y, "#0f67b1", 1.9);
  drawLine(currentAnalysis.turningPoints, x, y, "#3d4752", 1.6);
  drawLine(zigzagMidpoints, x, y, "#d9892b", 1.8, [5, 4]);
  drawMidpointIntersections(midpointIntersections, x, y);
  drawSegmentLabels(currentAnalysis.turningPoints, x, y, margin.left, width - margin.right, margin.top, height - margin.bottom);
  drawTurningMarkers(currentAnalysis.turningPoints, x, y);
  drawMidpointMarkers(zigzagMidpoints, x, y);
  drawMidpointIntersectionLabels(midpointIntersections, x, y, margin.left, width - margin.right, margin.top, height - margin.bottom);

  if (activeTime !== null) {{
    const nearest = nearestPoint(payload.points, activeTime);
    ctx.strokeStyle = "#9aa5b2";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x(nearest.time), margin.top);
    ctx.lineTo(x(nearest.time), height - margin.bottom);
    ctx.stroke();
    ctx.fillStyle = "#17202a";
    ctx.beginPath();
    ctx.arc(x(nearest.time), y(nearest.close), 4, 0, Math.PI * 2);
    ctx.fill();
  }}

  return {{ margin, plotW, minTime, maxTime, x, y }};
}}

function nearestPoint(points, time) {{
  let best = points[0];
  let bestDistance = Math.abs(best.time - time);
  for (const point of points) {{
    const distance = Math.abs(point.time - time);
    if (distance < bestDistance) {{
      best = point;
      bestDistance = distance;
    }}
  }}
  return best;
}}

function lastPointAtOrBefore(points, time) {{
  let result = null;
  for (const point of points) {{
    if (point.time <= time) result = point;
    else break;
  }}
  return result;
}}

canvas.addEventListener("mousemove", (event) => {{
  const rect = canvas.getBoundingClientRect();
  const state = draw();
  const mx = event.clientX - rect.left;
  const ratio = Math.max(0, Math.min(1, (mx - state.margin.left) / Math.max(1, state.plotW)));
  const activeTime = state.minTime + ratio * (state.maxTime - state.minTime);
  const point = nearestPoint(payload.points, activeTime);
  draw(point.time);
  const latestTurn = lastPointAtOrBefore(currentAnalysis.turningPoints, point.time);
  const latestHigh = lastPointAtOrBefore(currentAnalysis.turningHighs, point.time);
  const latestLow = lastPointAtOrBefore(currentAnalysis.turningLows, point.time);
  const latestEquity = lastPointAtOrBefore(drawdownCurveAsPricePoints(computeDrawdownEntryStrategy(Number(drawdownStopSlider.value) / 100)), point.time);
  const latestCoreEquity = lastPointAtOrBefore(coreCurveAsPricePoints(computeCoreSatelliteStrategy()), point.time);
  const turnText = latestTurn ? `${{latestTurn.point_type}}：${{latestTurn.trade_date}} / ${{fmt.format(latestTurn.close)}}` : "暂无";
  const highText = latestHigh ? `${{latestHigh.trade_date}} / ${{fmt.format(latestHigh.close)}}` : "暂无";
  const lowText = latestLow ? `${{latestLow.trade_date}} / ${{fmt.format(latestLow.close)}}` : "暂无";
  const equityText = latestEquity ? `${{fmt.format(latestEquity.equity)}} 倍 / 折算点位 ${{fmt.format(latestEquity.close)}}` : "暂无";
  const coreEquityText = latestCoreEquity ? `${{fmt.format(latestCoreEquity.equity)}} 倍 / 仓位 ${{pct.format(latestCoreEquity.allocation * 100)}}%` : "暂无";
  tip.innerHTML = `
    <strong>${{point.trade_date}}</strong><br>
    收盘：${{fmt.format(point.close)}}<br>
    <span style="color:#c44e52">20%策略净值：</span>${{equityText}}<br>
    <span style="color:#0f67b1">核心仓净值：</span>${{coreEquityText}}<br>
    <span style="color:#3d4752">上一拐点：</span>${{turnText}}<br>
    <span style="color:#b45f06">上一高点：</span>${{highText}}<br>
    <span style="color:#275f9f">上一低点：</span>${{lowText}}
  `;
  tip.style.display = "block";
  tip.style.left = `${{Math.min(canvas.clientWidth - 380, Math.max(12, mx + 16))}}px`;
  tip.style.top = `${{Math.max(12, event.clientY - rect.top - 20)}}px`;
}});

canvas.addEventListener("mouseleave", () => {{
  tip.style.display = "none";
  draw();
}});

function updateScaleButtons() {{
  for (const button of scaleButtons) {{
    button.classList.toggle("active", button.dataset.scale === currentScale);
  }}
}}

for (const button of scaleButtons) {{
  button.addEventListener("click", () => {{
    currentScale = button.dataset.scale;
    tip.style.display = "none";
    updateScaleButtons();
    draw();
  }});
}}

for (const input of indicatorInputs) {{
  input.addEventListener("change", () => {{
    tip.style.display = "none";
    draw();
  }});
}}

reversalSlider.addEventListener("input", () => {{
  currentReversal = Number(reversalSlider.value) / 100;
  updateAnalysis();
}});

drawdownStopSlider.addEventListener("input", () => {{
  renderDrawdownStrategy();
  renderStats();
  draw();
}});

window.addEventListener("resize", () => {{
  resizeCanvas();
  drawDrawdownStrategyChart(currentDrawdownGrid, Number(drawdownStopSlider.value));
  renderCoreStrategy();
}});
updateScaleButtons();
updateAnalysis();
renderDrawdownStrategy();
renderCoreStrategy();
resizeCanvas();
</script>
<div data-myinvest-footer></div>
<script src="https://invest.okbbc.com/footer.js" charset="utf-8" defer></script>
</body>
</html>
"""
    output_path.write_text(html, encoding="utf-8")


def write_log_regression_html(
    series: IndexSeries,
    records: pd.DataFrame,
    output_path: Path,
    y_scale: str,
    reversal_threshold: float,
) -> None:
    payload = chart_payload(series, records, y_scale, reversal_threshold)
    page_title = f"{series.name} Log回归通道研究"
    html_template = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>__PAGE_TITLE__</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #17202a;
      --muted: #66717f;
      --line: #d8dee8;
      --panel: #ffffff;
      --bg: #f5f7f9;
      --main: #1f7a68;
      --accent: #6c4ab6;
      --upper: #a2466c;
      --lower: #326fa8;
      --buy: #1f7a68;
      --sell: #b45f06;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
      background: var(--bg);
      color: var(--ink);
    }
    .site-header {
      background: rgba(255, 255, 255, 0.94);
      border-bottom: 1px solid var(--line);
    }
    .site-nav {
      width: min(1240px, calc(100vw - 32px));
      min-height: 50px;
      margin: 0 auto;
      display: flex;
      align-items: center;
      gap: 16px;
      overflow-x: auto;
      white-space: nowrap;
    }
    .brand {
      color: var(--ink);
      font-weight: 800;
      text-decoration: none;
    }
    .site-nav a:not(.brand) {
      color: var(--muted);
      font-size: 13px;
      text-decoration: none;
    }
    .site-nav a.active {
      color: var(--main);
      font-weight: 700;
    }
    main {
      width: min(1240px, calc(100vw - 32px));
      margin: 22px auto 28px;
    }
    h1 {
      margin: 0 0 8px;
      font-size: clamp(24px, 3vw, 34px);
      line-height: 1.15;
      letter-spacing: 0;
    }
    .subtitle {
      margin: 0;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.7;
    }
    .research-finding {
      margin: 14px 0 16px;
      padding: 16px 18px;
      background: #eef7f4;
      border: 1px solid #9cc8bb;
      border-left: 6px solid var(--main);
      border-radius: 8px;
      box-shadow: 0 8px 20px rgba(31, 122, 104, 0.08);
    }
    .research-finding h2 {
      margin: 0 0 8px;
      color: #145445;
      font-size: 18px;
      line-height: 1.35;
      letter-spacing: 0;
    }
    .research-finding p {
      margin: 0;
      color: #27313a;
      font-size: 14px;
      line-height: 1.8;
    }
    .stats {
      display: grid;
      gap: 10px;
      margin: 16px 0;
    }
    .stats-row {
      display: grid;
      gap: 10px;
    }
    .stats-row.annual-row {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }
    .stats-row.detail-row {
      grid-template-columns: repeat(4, minmax(0, 1fr));
    }
    .stat {
      min-height: 86px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px 14px;
    }
    .label {
      display: block;
      margin-bottom: 8px;
      color: var(--muted);
      font-size: 12px;
    }
    .value {
      display: block;
      font-size: 18px;
      font-weight: 700;
      white-space: nowrap;
    }
    .controls {
      display: grid;
      grid-template-columns: minmax(180px, 240px) minmax(260px, 1fr) minmax(260px, 1fr);
      gap: 22px;
      margin: 0 0 14px;
      padding: 14px 18px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    .control {
      display: grid;
      gap: 9px;
      min-width: 0;
    }
    .control + .control {
      border-left: 1px solid var(--line);
      padding-left: 22px;
    }
    .control label {
      color: var(--ink);
      font-size: 14px;
      font-weight: 700;
    }
    select {
      height: 34px;
      padding: 0 10px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--ink);
      font: inherit;
    }
    .slider-row {
      display: grid;
      grid-template-columns: minmax(140px, 1fr) 72px;
      gap: 12px;
      align-items: center;
    }
    input[type="range"] {
      width: 100%;
      accent-color: var(--main);
    }
    output {
      color: var(--ink);
      font-size: 18px;
      font-weight: 700;
      text-align: right;
    }
    .slider-hints {
      display: flex;
      justify-content: space-between;
      color: var(--muted);
      font-size: 12px;
    }
    .legend {
      display: flex;
      flex-wrap: wrap;
      gap: 16px;
      margin: 0 0 12px;
      color: var(--muted);
      font-size: 13px;
    }
    .legend span {
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .swatch {
      width: 22px;
      height: 3px;
      border-radius: 999px;
      display: inline-block;
    }
    .chart-shell {
      position: relative;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }
    canvas {
      display: block;
      width: 100%;
      height: min(68vh, 640px);
      min-height: 430px;
    }
    .tooltip {
      position: absolute;
      display: none;
      min-width: 240px;
      max-width: 360px;
      padding: 8px 10px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: rgba(255, 255, 255, 0.96);
      box-shadow: 0 8px 22px rgba(23, 32, 42, 0.12);
      pointer-events: none;
      font-size: 12px;
      line-height: 1.55;
    }
    .notes {
      margin-top: 14px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.7;
    }
    .notes p { margin: 4px 0; }
    .research-note {
      margin-top: 14px;
      padding: 14px 16px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      color: var(--ink);
      font-size: 13px;
      line-height: 1.75;
    }
    .research-note h2 {
      margin: 0 0 8px;
      font-size: 16px;
      line-height: 1.35;
      letter-spacing: 0;
    }
    .research-note p {
      margin: 6px 0;
      color: var(--muted);
    }
    .research-note strong {
      color: var(--ink);
    }
    @media (max-width: 980px) {
      .stats-row.annual-row,
      .stats-row.detail-row {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
      .controls {
        grid-template-columns: 1fr;
        gap: 14px;
      }
      .control + .control {
        border-left: 0;
        border-top: 1px solid var(--line);
        padding-left: 0;
        padding-top: 14px;
      }
      canvas {
        min-height: 360px;
      }
      .value {
        font-size: 16px;
      }
    }
  </style>
</head>
<body>
<div data-myinvest-header></div>
<script src="https://invest.okbbc.com/header.js" charset="utf-8" defer></script>
<header class="site-header">
  <nav class="site-nav" aria-label="研究入口">
    <a class="brand" href="/index.html">研究入口</a>
    <a class="active" href="/480092_CNI_new_high_low.html">Log回归通道</a>
    <a href="/480092_CNI_zigzag_strategy.html">ZigZag拐点策略</a>
    <a href="/480092_CNI_mainline_background.html">资产配置研究</a>
    <a href="/480092_CNI_alpha.html">资产 Alpha 研究</a>
    <a href="/480092_CNI_strategy_portfolio.html">策略组合研究</a>
    <a href="/480092_CNI_daily.csv">日线数据</a>
    <a href="/480092_CNI_record_points.csv">拐点记录</a>
  </nav>
</header>
<main>
  <header>
    <h1>__PAGE_TITLE__</h1>
    <p class="subtitle">__DATE_RANGE__ · 仅保留滚动 Log 回归通道，全部轨道和收益回放都不使用未来数据。</p>
  </header>

  <section class="research-finding" aria-label="核心研究发现">
    <h2>研究发现：通道位置有价值，但不能把复盘通道当成实盘结论</h2>
    <p>固定低点锚定的 Log 趋势通道能解释历史，也能在样本内跑赢，但一旦锚点包含后来的大低点，就带有未来函数。真正可用的是“通道位置”这个观察变量：只用当时已经存在的数据滚动计算，判断价格在长期趋势轨道中的高低位置；参数结果必须按无未来函数、t+1 生效口径重新验证。</p>
  </section>

  <section class="stats" id="stats" aria-label="收益对比"></section>

  <section class="controls" aria-label="Log回归参数">
    <div class="control">
      <label for="lookbackSlider">回看年数</label>
      <div class="slider-row">
        <input id="lookbackSlider" type="range" min="1" max="10" step="0.5" value="2">
        <output id="lookbackValue" for="lookbackSlider">2.0年</output>
      </div>
      <div class="slider-hints"><span>1年</span><span>10年</span></div>
    </div>
    <div class="control">
      <label for="sigmaSlider">通道宽度</label>
      <div class="slider-row">
        <input id="sigmaSlider" type="range" min="1" max="3" step="0.25" value="2.75">
        <output id="sigmaValue" for="sigmaSlider">2.75σ</output>
      </div>
      <div class="slider-hints"><span>1.00σ</span><span>3.00σ</span></div>
    </div>
    <div class="control">
      <label for="zigzagSlider">ZigZag阈值</label>
      <div class="slider-row">
        <input id="zigzagSlider" type="range" min="5" max="40" step="0.5" value="15">
        <output id="zigzagValue" for="zigzagSlider">15.00%</output>
      </div>
      <div class="slider-hints"><span>5%</span><span>40%</span></div>
    </div>
  </section>

  <div class="legend">
    <span><i class="swatch" style="background: var(--main)"></i>收盘价</span>
    <span><i class="swatch" style="background: var(--accent)"></i>Log回归中轨</span>
    <span><i class="swatch" style="background: var(--upper)"></i>上轨</span>
    <span><i class="swatch" style="background: var(--lower)"></i>下轨</span>
    <span><i class="swatch" style="background: #3d4752"></i>ZigZag折线</span>
    <span><i class="swatch" style="background: #d9892b"></i>ZigZag段中点线</span>
    <span><i class="swatch" style="background: #c73d3d"></i>牛市背景</span>
    <span><i class="swatch" style="background: #17885b"></i>熊市背景</span>
    <span><i class="swatch" style="background: #8b95a5"></i>上证背景</span>
    <span><i class="swatch" style="background: var(--buy)"></i>买入信号</span>
    <span><i class="swatch" style="background: var(--sell)"></i>卖出信号</span>
  </div>

  <section class="chart-shell">
    <canvas id="chart" aria-label="Log回归通道图"></canvas>
    <div class="tooltip" id="tooltip"></div>
  </section>

  <section class="notes" id="notes" aria-label="说明"></section>
  <section class="research-note" aria-label="回测观察与建议">
    <h2>回测观察与建议</h2>
    <p><strong>当前默认参数改为样本内表现较好的 2年 / 2.75σ。</strong>在 2016-04-01 至 2026-06-30 的同口径回放里，买入持有年化约 16.48%，通道回放年化约 20.77%，超额年化约 +4.29%；持有总收益约 +377.34%，通道回放总收益约 +591.39%，交易 6 次。</p>
    <p>原默认 4年 / 2.00σ 的问题是偏向“上轨全卖、下轨买回”的均值回归逻辑。这个指数长期趋势较强，2020-11-23 触发卖出后直到 2024-09-09 才买回，中间大段上涨被错过，所以默认回放年化约 9.74%，明显低于持有。</p>
    <p>这个结果仍然只是样本内回测，不应直接当作固定最优参数。后续更合理的方向是把“上轨全卖、下轨全买”改成分档仓位：上升趋势里上轨只减仓不清仓，下轨加仓；下降趋势里限制仓位上限。参数优化应同时看年化、最大回撤、Calmar、换手次数和邻近参数稳定性。</p>
  </section>
</main>

<script>
const payload = __PAYLOAD__;
const canvas = document.getElementById("chart");
const ctx = canvas.getContext("2d");
const tip = document.getElementById("tooltip");
const statsEl = document.getElementById("stats");
const notesEl = document.getElementById("notes");
const lookbackSlider = document.getElementById("lookbackSlider");
const lookbackValue = document.getElementById("lookbackValue");
const sigmaSlider = document.getElementById("sigmaSlider");
const sigmaValue = document.getElementById("sigmaValue");
const zigzagSlider = document.getElementById("zigzagSlider");
const zigzagValue = document.getElementById("zigzagValue");
const fmt = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 });
const pct = new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const DAY = 86400000;
const MIN_REGRESSION_POINTS = 60;

payload.points = payload.points.map((point) => ({
  ...point,
  close: Number(point.close),
  high: Number.isFinite(Number(point.high)) ? Number(point.high) : Number(point.close),
  low: Number.isFinite(Number(point.low)) ? Number(point.low) : Number(point.close),
  time: Date.parse(point.trade_date + "T00:00:00Z"),
}));
payload.first = { ...payload.first, time: Date.parse(payload.first.trade_date + "T00:00:00Z") };
payload.last = { ...payload.last, time: Date.parse(payload.last.trade_date + "T00:00:00Z") };
const marketContext = payload.marketContext || { series: [], cycleBlocks: [] };
marketContext.series = (marketContext.series || []).map((point) => ({
  ...point,
  close: Number(point.close),
  time: Date.parse(point.trade_date + "T00:00:00Z"),
})).filter((point) => Number.isFinite(point.time) && Number.isFinite(point.close) && point.close > 0);
marketContext.cycleBlocks = (marketContext.cycleBlocks || []).map((block) => ({
  ...block,
  startTime: Date.parse(block.start_date + "T00:00:00Z"),
  endTime: Date.parse(block.end_date + "T00:00:00Z"),
})).filter((block) => Number.isFinite(block.startTime) && Number.isFinite(block.endTime));

let current = null;

function formatSignedPercent(value) {
  const sign = value > 0 ? "+" : "";
  return `${sign}${pct.format(value)}%`;
}

function linearRegressionChannel(points, sigmaMultiple) {
  const n = points.length;
  const logs = points.map((point) => Math.log(point.close));
  const meanX = (n - 1) / 2;
  const meanY = logs.reduce((sum, value) => sum + value, 0) / n;
  let numerator = 0;
  let denominator = 0;
  for (let index = 0; index < n; index++) {
    numerator += (index - meanX) * (logs[index] - meanY);
    denominator += Math.pow(index - meanX, 2);
  }
  const slope = denominator === 0 ? 0 : numerator / denominator;
  const intercept = meanY - slope * meanX;
  const residuals = logs.map((value, index) => value - (intercept + slope * index));
  const sigma = Math.sqrt(residuals.reduce((sum, value) => sum + value * value, 0) / Math.max(1, n - 2));
  const channel = points.map((source, index) => {
    const fitted = intercept + slope * index;
    return {
      trade_date: source.trade_date,
      time: source.time,
      close: source.close,
      mid: Math.exp(fitted),
      upper: Math.exp(fitted + sigma * sigmaMultiple),
      lower: Math.exp(fitted - sigma * sigmaMultiple),
    };
  });
  return { channel, sigma, slope };
}

function rollingRegressionChannel(displayPoints, sigmaMultiple) {
  const years = Number(lookbackSlider.value);
  const channel = [];
  for (const point of displayPoints) {
    const cutoff = point.time - years * 365.25 * DAY;
    const train = payload.points.filter((item) => item.time <= point.time && item.time >= cutoff);
    if (train.length < MIN_REGRESSION_POINTS) continue;
    const regression = linearRegressionChannel(train, sigmaMultiple);
    channel.push(regression.channel[regression.channel.length - 1]);
  }
  return { channel, sigma: null, slope: null };
}

function computeZigzagPoints(points, reversalThreshold) {
  const closes = points.map((point) => Number(point.close));
  const pivots = [];
  if (!points.length) return pivots;

  const addPivot = (rowIndex, turningType, pointType) => {
    if (pivots.length && pivots[pivots.length - 1].row_index === rowIndex) return;
    pivots.push({
      row_index: rowIndex,
      turning_type: turningType,
      point_type: pointType,
      trade_date: points[rowIndex].trade_date,
      close: closes[rowIndex],
      time: points[rowIndex].time,
    });
  };

  let trend = 0;
  let highIdx = 0;
  let lowIdx = 0;

  for (let idx = 1; idx < closes.length; idx++) {
    const close = closes[idx];

    if (trend === 0) {
      if (close >= closes[highIdx]) highIdx = idx;
      if (close <= closes[lowIdx]) lowIdx = idx;

      const hasEnoughRange = closes[highIdx] / closes[lowIdx] - 1 >= reversalThreshold;
      if (!hasEnoughRange) continue;

      if (lowIdx < highIdx) {
        addPivot(lowIdx, "low", "起点低点");
        trend = 1;
      } else {
        addPivot(highIdx, "high", "起点高点");
        trend = -1;
      }
      continue;
    }

    if (trend > 0) {
      if (close >= closes[highIdx]) {
        highIdx = idx;
        continue;
      }
      if ((closes[highIdx] - close) / closes[highIdx] >= reversalThreshold) {
        addPivot(highIdx, "high", "确认高点");
        trend = -1;
        lowIdx = idx;
      }
      continue;
    }

    if (close <= closes[lowIdx]) {
      lowIdx = idx;
      continue;
    }
    if ((close - closes[lowIdx]) / closes[lowIdx] >= reversalThreshold) {
      addPivot(lowIdx, "low", "确认低点");
      trend = 1;
      highIdx = idx;
    }
  }

  if (trend === 0) {
    addPivot(0, "flat", "起点/横盘");
  } else {
    const lastIdx = trend > 0 ? highIdx : lowIdx;
    addPivot(lastIdx, trend > 0 ? "high" : "low", trend > 0 ? "末段高点" : "末段低点");
  }

  return pivots.map((pivot, index) => ({ ...pivot, sequence: index + 1 }));
}

function computeZigzagMidpoints(zigzagPoints) {
  const midpoints = [];
  for (let index = 1; index < zigzagPoints.length; index++) {
    const fromPoint = zigzagPoints[index - 1];
    const toPoint = zigzagPoints[index];
    midpoints.push({
      sequence: index,
      trade_date: `${fromPoint.trade_date}~${toPoint.trade_date}`,
      time: (fromPoint.time + toPoint.time) / 2,
      close: Math.exp((Math.log(fromPoint.close) + Math.log(toPoint.close)) / 2),
    });
  }
  return midpoints;
}

function annualizedReturn(finalValue, firstTime, lastTime) {
  const days = Math.max(1, (lastTime - firstTime) / DAY);
  return (Math.pow(finalValue, 365.25 / days) - 1) * 100;
}

function channelReplay(points, channel) {
  if (points.length < 2 || channel.length < 2) {
    return {
      first: points[0] || null,
      last: points[points.length - 1] || null,
      trades: [],
      holding: true,
      strategyTotal: 0,
      holdTotal: 0,
      strategyAnnualized: 0,
      holdAnnualized: 0,
      excessAnnualized: 0,
    };
  }
  let cash = 0;
  let units = 1 / points[0].close;
  let holding = true;
  const trades = [];

  for (let index = 1; index < points.length; index++) {
    const point = points[index];
    const rail = channel[index];
    if (holding && point.close >= rail.upper) {
      cash = units * point.close;
      units = 0;
      holding = false;
      trades.push({ ...point, action: "sell" });
    } else if (!holding && point.close <= rail.lower) {
      units = cash / point.close;
      cash = 0;
      holding = true;
      trades.push({ ...point, action: "buy" });
    }
  }

  const first = points[0];
  const last = points[points.length - 1];
  const strategyFinal = holding ? units * last.close : cash;
  const holdFinal = last.close / first.close;
  const strategyAnnualized = annualizedReturn(strategyFinal, first.time, last.time);
  const holdAnnualized = annualizedReturn(holdFinal, first.time, last.time);
  return {
    first,
    last,
    trades,
    holding,
    strategyTotal: (strategyFinal - 1) * 100,
    holdTotal: (holdFinal - 1) * 100,
    strategyAnnualized,
    holdAnnualized,
    excessAnnualized: strategyAnnualized - holdAnnualized,
  };
}

function computeState() {
  const points = payload.points;
  const sigmaMultiple = Number(sigmaSlider.value);
  const zigzagThreshold = Number(zigzagSlider.value) / 100;
  const regression = rollingRegressionChannel(points, sigmaMultiple);
  const replayPoints = regression.channel;
  const replay = channelReplay(replayPoints, regression.channel);
  const zigzagPoints = computeZigzagPoints(points, zigzagThreshold);
  const zigzagMidpoints = computeZigzagMidpoints(zigzagPoints);
  return { points, replayPoints, sigmaMultiple, zigzagThreshold, zigzagPoints, zigzagMidpoints, ...regression, replay };
}

function renderStats() {
  const replay = current.replay;
  const first = replay.first || current.points[0];
  const last = replay.last || current.points[current.points.length - 1];
  const latestRail = current.channel[current.channel.length - 1] || { lower: NaN, upper: NaN };
  statsEl.innerHTML = `
    <div class="stats-row annual-row">
      <div class="stat"><span class="label">持有年化</span><span class="value">${formatSignedPercent(replay.holdAnnualized)}</span></div>
      <div class="stat"><span class="label">通道回放年化</span><span class="value">${formatSignedPercent(replay.strategyAnnualized)}</span></div>
      <div class="stat"><span class="label">超额年化</span><span class="value">${formatSignedPercent(replay.excessAnnualized)}</span></div>
    </div>
    <div class="stats-row detail-row">
      <div class="stat"><span class="label">研究区间</span><span class="value">${first.trade_date}<br>${last.trade_date}</span></div>
      <div class="stat"><span class="label">ZigZag拐点</span><span class="value">${current.zigzagPoints.length}</span></div>
      <div class="stat"><span class="label">持有总收益</span><span class="value">${formatSignedPercent(replay.holdTotal)}</span></div>
      <div class="stat"><span class="label">通道回放总收益</span><span class="value">${formatSignedPercent(replay.strategyTotal)}</span></div>
      <div class="stat"><span class="label">交易次数</span><span class="value">${replay.trades.length}</span></div>
      <div class="stat"><span class="label">当前状态</span><span class="value">${replay.holding ? "持有" : "空仓"}</span></div>
      <div class="stat"><span class="label">最新收盘</span><span class="value">${fmt.format(last.close)}</span></div>
      <div class="stat"><span class="label">最新轨道</span><span class="value">${fmt.format(latestRail.lower)} / ${fmt.format(latestRail.upper)}</span></div>
    </div>
  `;
}

function renderNotes() {
  lookbackValue.textContent = `${Number(lookbackSlider.value).toFixed(1)}年`;
  sigmaValue.textContent = `${Number(sigmaSlider.value).toFixed(2)}σ`;
  zigzagValue.textContent = `${Number(zigzagSlider.value).toFixed(2)}%`;
  notesEl.innerHTML = `
    <p>${payload.source}，当前显示窗口共 ${current.points.length} 条日线，当前回放窗口共 ${current.replayPoints.length} 条日线。</p>
    <p>背景层来自长期牛熊周期观察：浅红为牛市、浅绿为熊市；灰色虚线为上证指数背景曲线，使用独立归一化坐标，只辅助观察大盘环境，不改变自由现金流指数价格轴。</p>
    <p>滚动 Log 回归通道：图上始终显示全部数据；每个交易日只使用当日及以前最多 ${Number(lookbackSlider.value).toFixed(1)} 年历史数据拟合当天轨道，中轨为 log(close) 拟合趋势线，上下轨为中轨 ± ${Number(sigmaSlider.value).toFixed(2)}σ 残差带；收益回放不使用未来数据。</p>
    <p>ZigZag 折线阈值为 ${Number(zigzagSlider.value).toFixed(2)}%，用于形态观察；拐点画在事后确认的高低点日期上，不参与通道回放收益计算。</p>
    <p>通道回放口径：起始日持有指数，收盘价触及或高于上轨时卖出，触及或低于下轨时买入；不计交易成本、滑点、税费，也不代表真实可交易回测。</p>
  `;
}

function axisLabel(value) {
  return fmt.format(Math.exp(value));
}

function yValue(close) {
  return Math.log(close);
}

function resizeCanvas() {
  const ratio = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = Math.floor(rect.width * ratio);
  canvas.height = Math.floor(rect.height * ratio);
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  draw();
}

function drawLine(points, x, y, key, color, width, dash = []) {
  if (!points.length) return;
  ctx.save();
  ctx.setLineDash(dash);
  ctx.beginPath();
  points.forEach((point, index) => {
    const xx = x(point.time);
    const yy = y(point[key]);
    if (index === 0) ctx.moveTo(xx, yy);
    else ctx.lineTo(xx, yy);
  });
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.stroke();
  ctx.restore();
}

function drawMarketBackground(x, minTime, maxTime, plotLeft, plotRight, plotTop, plotBottom) {
  ctx.save();
  for (const block of marketContext.cycleBlocks) {
    const start = Math.max(block.startTime, minTime);
    const end = Math.min(block.endTime, maxTime);
    if (end <= start) continue;
    const x0 = Math.max(plotLeft, Math.min(plotRight, x(start)));
    const x1 = Math.max(plotLeft, Math.min(plotRight, x(end)));
    if (x1 <= x0) continue;
    ctx.fillStyle = block.state === "bull" ? "rgba(199, 61, 61, 0.105)" : "rgba(23, 136, 91, 0.105)";
    ctx.fillRect(x0, plotTop, x1 - x0, plotBottom - plotTop);
  }

  const indexPoints = marketContext.series.filter((point) => point.time >= minTime && point.time <= maxTime);
  if (indexPoints.length >= 2) {
    const values = indexPoints.map((point) => Math.log(point.close));
    const minValue = Math.min(...values);
    const maxValue = Math.max(...values);
    const spread = maxValue - minValue || 1;
    const yIndex = (close) => plotBottom - ((Math.log(close) - minValue) / spread) * (plotBottom - plotTop);
    ctx.beginPath();
    indexPoints.forEach((point, index) => {
      const xx = x(point.time);
      const yy = yIndex(point.close);
      if (index === 0) ctx.moveTo(xx, yy);
      else ctx.lineTo(xx, yy);
    });
    ctx.strokeStyle = "rgba(75, 85, 99, 0.34)";
    ctx.lineWidth = 1.8;
    ctx.setLineDash([7, 5]);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = "rgba(75, 85, 99, 0.74)";
    ctx.font = "12px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
    ctx.textAlign = "right";
    ctx.textBaseline = "top";
    ctx.fillText("上证背景（独立归一化）", plotRight - 8, plotTop + 8);
  }
  ctx.restore();
}

function drawTrades(x, y) {
  for (const trade of current.replay.trades) {
    const xx = x(trade.time);
    const yy = y(trade.close);
    ctx.fillStyle = trade.action === "buy" ? "#1f7a68" : "#b45f06";
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    if (trade.action === "buy") {
      ctx.moveTo(xx, yy - 6);
      ctx.lineTo(xx + 5, yy + 4);
      ctx.lineTo(xx - 5, yy + 4);
    } else {
      ctx.moveTo(xx, yy + 6);
      ctx.lineTo(xx + 5, yy - 4);
      ctx.lineTo(xx - 5, yy - 4);
    }
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
  }
}

function drawZigzagMarkers(x, y) {
  for (const point of current.zigzagPoints) {
    const xx = x(point.time);
    const yy = y(point.close);
    ctx.fillStyle = point.turning_type === "high" ? "#b45f06" : point.turning_type === "low" ? "#275f9f" : "#3d4752";
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 1.1;
    ctx.beginPath();
    ctx.arc(xx, yy, 3.8, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
  }
}

function drawZigzagMidpointMarkers(x, y) {
  for (const point of current.zigzagMidpoints) {
    const xx = x(point.time);
    const yy = y(point.close);
    ctx.fillStyle = "#d9892b";
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(xx, yy, 3.2, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
  }
}

function drawZigzagLabels(x, y, plotLeft, plotRight, plotTop, plotBottom) {
  if (current.zigzagPoints.length < 2) return;
  ctx.font = "12px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  for (let index = 1; index < current.zigzagPoints.length; index++) {
    const fromPoint = current.zigzagPoints[index - 1];
    const toPoint = current.zigzagPoints[index];
    const change = (toPoint.close / fromPoint.close - 1) * 100;
    const label = formatSignedPercent(change);
    const textWidth = ctx.measureText(label).width;
    const boxW = textWidth + 12;
    const boxH = 20;
    const anchorX = x(toPoint.time);
    const anchorY = y(toPoint.close);
    const isUp = change >= 0;
    const xx = Math.max(plotLeft + boxW / 2, Math.min(plotRight - boxW / 2, anchorX));
    const yy = Math.max(plotTop + boxH / 2, Math.min(plotBottom - boxH / 2, anchorY + (isUp ? -26 : 26)));
    ctx.fillStyle = "rgba(255, 255, 255, 0.9)";
    ctx.strokeStyle = isUp ? "rgba(180, 95, 6, 0.35)" : "rgba(39, 95, 159, 0.35)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.roundRect(xx - boxW / 2, yy - boxH / 2, boxW, boxH, 5);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = isUp ? "#8f4a05" : "#275f9f";
    ctx.fillText(label, xx, yy + 0.5);
  }
}

function draw(activeTime = null) {
  if (!current) return;
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  const margin = { left: 64, right: 24, top: 26, bottom: 46 };
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;
  const minTime = current.points[0].time;
  const maxTime = current.points[current.points.length - 1].time;
  const visibleValues = current.points.map((point) => point.close)
    .concat(current.channel.flatMap((point) => [point.upper, point.mid, point.lower]));
  const minValue = Math.min(...visibleValues.map(yValue));
  const maxValue = Math.max(...visibleValues.map(yValue));
  const pad = (maxValue - minValue) * 0.08 || 1;
  const lo = minValue - pad;
  const hi = maxValue + pad;
  const x = (time) => margin.left + ((time - minTime) / Math.max(1, maxTime - minTime)) * plotW;
  const y = (close) => margin.top + ((hi - yValue(close)) / (hi - lo)) * plotH;

  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, width, height);
  drawMarketBackground(x, minTime, maxTime, margin.left, width - margin.right, margin.top, height - margin.bottom);

  ctx.strokeStyle = "#d8dee8";
  ctx.lineWidth = 1;
  ctx.fillStyle = "#66717f";
  ctx.font = "12px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  for (let i = 0; i <= 5; i++) {
    const value = lo + ((hi - lo) * i) / 5;
    const yy = margin.top + ((hi - value) / (hi - lo)) * plotH;
    ctx.beginPath();
    ctx.moveTo(margin.left, yy);
    ctx.lineTo(width - margin.right, yy);
    ctx.stroke();
    ctx.fillText(axisLabel(value), margin.left - 10, yy);
  }

  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  for (let i = 0; i < 6; i++) {
    const time = minTime + ((maxTime - minTime) * i) / 5;
    const label = new Date(time).toISOString().slice(0, 7);
    ctx.fillText(label, x(time), height - margin.bottom + 18);
  }

  drawLine(current.channel, x, y, "upper", "#a2466c", 1.4, [6, 4]);
  drawLine(current.channel, x, y, "mid", "#6c4ab6", 1.8);
  drawLine(current.channel, x, y, "lower", "#326fa8", 1.4, [6, 4]);
  drawLine(current.points, x, y, "close", "#1f7a68", 2.2);
  drawLine(current.zigzagPoints, x, y, "close", "#3d4752", 1.6);
  drawLine(current.zigzagMidpoints, x, y, "close", "#d9892b", 1.8, [5, 4]);
  drawZigzagMidpointMarkers(x, y);
  drawZigzagMarkers(x, y);
  drawZigzagLabels(x, y, margin.left, width - margin.right, margin.top, height - margin.bottom);
  drawTrades(x, y);

  if (activeTime !== null) {
    const nearest = nearestPoint(current.points, activeTime);
    ctx.strokeStyle = "#9aa5b2";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x(nearest.time), margin.top);
    ctx.lineTo(x(nearest.time), height - margin.bottom);
    ctx.stroke();
    ctx.fillStyle = "#17202a";
    ctx.beginPath();
    ctx.arc(x(nearest.time), y(nearest.close), 4, 0, Math.PI * 2);
    ctx.fill();
  }

  return { margin, plotW, minTime, maxTime };
}

function nearestPoint(points, time) {
  let best = points[0];
  let bestDistance = Math.abs(best.time - time);
  for (const point of points) {
    const distance = Math.abs(point.time - time);
    if (distance < bestDistance) {
      best = point;
      bestDistance = distance;
    }
  }
  return best;
}

function nearestChannel(time) {
  if (!current.channel.length) return null;
  return current.channel.reduce((best, point) => (
    Math.abs(point.time - time) < Math.abs(best.time - time) ? point : best
  ), current.channel[0]);
}

function update() {
  current = computeState();
  renderStats();
  renderNotes();
  tip.style.display = "none";
  draw();
}

canvas.addEventListener("mousemove", (event) => {
  if (!current) return;
  const rect = canvas.getBoundingClientRect();
  const state = draw();
  const mx = event.clientX - rect.left;
  const ratio = Math.max(0, Math.min(1, (mx - state.margin.left) / Math.max(1, state.plotW)));
  const activeTime = state.minTime + ratio * (state.maxTime - state.minTime);
  const point = nearestPoint(current.points, activeTime);
  const rail = nearestChannel(point.time);
  draw(point.time);
  tip.innerHTML = `
    <strong>${point.trade_date}</strong><br>
    收盘：${fmt.format(point.close)}<br>
    上轨：${rail ? fmt.format(rail.upper) : "暂无"}<br>
    中轨：${rail ? fmt.format(rail.mid) : "暂无"}<br>
    下轨：${rail ? fmt.format(rail.lower) : "暂无"}
  `;
  tip.style.display = "block";
  tip.style.left = `${Math.min(canvas.clientWidth - 380, Math.max(12, mx + 16))}px`;
  tip.style.top = `${Math.max(12, event.clientY - rect.top - 20)}px`;
});

canvas.addEventListener("mouseleave", () => {
  tip.style.display = "none";
  draw();
});

lookbackSlider.addEventListener("input", update);
sigmaSlider.addEventListener("input", update);
zigzagSlider.addEventListener("input", update);
window.addEventListener("resize", resizeCanvas);
update();
resizeCanvas();
</script>
<div data-myinvest-footer></div>
<script src="https://invest.okbbc.com/footer.js" charset="utf-8" defer></script>
</body>
</html>
"""
    html = (
        html_template.replace("__PAGE_TITLE__", page_title)
        .replace("__DATE_RANGE__", f"{payload['first']['trade_date']} 至 {payload['last']['trade_date']}")
        .replace("__PAYLOAD__", safe_json(payload))
    )
    output_path.write_text(html, encoding="utf-8")


def write_alpha_html(series: IndexSeries, output_path: Path, payload: dict[str, Any]) -> None:
    html_template = r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>资产 Alpha 研究</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #17202a;
      --muted: #66717f;
      --line: #d8dee8;
      --bg: #f5f7f9;
      --panel: #ffffff;
      --main: #147a61;
      --accent: #2f63b7;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
      background: var(--bg);
      color: var(--ink);
    }
    body.chart-fullscreen { overflow: hidden; }
    .site-header { background: rgba(255, 255, 255, 0.94); border-bottom: 1px solid var(--line); }
    .site-nav {
      width: min(1560px, calc(100vw - 28px));
      min-height: 50px;
      margin: 0 auto;
      display: flex;
      align-items: center;
      gap: 16px;
      overflow-x: auto;
      white-space: nowrap;
    }
    .brand { color: var(--ink); font-weight: 800; text-decoration: none; }
    .site-nav a:not(.brand) { color: var(--muted); font-size: 13px; text-decoration: none; }
    .site-nav a.active { color: var(--main); font-weight: 700; }
    main {
      width: min(1560px, calc(100vw - 28px));
      margin: 8px auto 28px;
    }
    main.fullscreen-view {
      position: fixed;
      inset: 0;
      z-index: 1000;
      width: 100vw;
      height: 100vh;
      margin: 0;
      padding: 18px;
      overflow: auto;
      background: var(--bg);
    }
    .page-head {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: center;
      margin-bottom: 8px;
    }
    h1 { margin: 0; font-size: 18px; line-height: 1.2; letter-spacing: 0; white-space: nowrap; }
    .subtitle { margin: 0; color: var(--muted); font-size: 13px; line-height: 1.5; }
    .source-note { color: var(--muted); font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .workspace {
      display: grid;
      grid-template-columns: 300px minmax(0, 1fr);
      gap: 14px;
      align-items: start;
    }
    .controls, .chart-panel, .table-panel, .method-panel {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: 0 10px 28px rgba(23, 32, 42, 0.05);
    }
    .controls { padding: 12px; position: sticky; top: 58px; max-height: calc(100vh - 68px); overflow: auto; }
    .controls h2, .table-panel h2, .method-panel h2 { margin: 0 0 10px; font-size: 15px; }
    .control-section { border-top: 1px solid var(--line); padding-top: 12px; margin-top: 12px; }
    .control-section h3 { margin: 0 0 8px; color: var(--muted); font-size: 12px; }
    .index-option {
      display: grid;
      grid-template-columns: 18px minmax(0, 1fr);
      gap: 8px;
      align-items: center;
      min-height: 30px;
      font-size: 13px;
    }
    .index-option span { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .index-option small { display: block; color: var(--muted); font-size: 11px; }
    input[type="checkbox"] { width: 16px; height: 16px; accent-color: var(--main); }
    input[type="date"] {
      width: 100%;
      min-height: 34px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #fff;
      color: var(--ink);
      padding: 0 8px;
      font: inherit;
    }
    .date-range { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    .date-range label { display: grid; gap: 4px; color: var(--muted); font-size: 11px; }
    .button-row { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-top: 12px; }
    button {
      min-height: 34px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #fff;
      color: var(--ink);
      font: inherit;
      font-size: 12px;
      font-weight: 700;
      cursor: pointer;
    }
    button.primary { border-color: var(--main); background: var(--main); color: #fff; }
    button:disabled { opacity: .45; cursor: default; }
    .chart-panel { padding: 10px; }
    .chart-head { display: flex; justify-content: space-between; gap: 12px; align-items: center; margin-bottom: 10px; color: var(--muted); font-size: 12px; }
    .chart-actions { display: inline-flex; gap: 8px; align-items: center; white-space: nowrap; }
    .chart-actions button { min-height: 30px; padding: 0 10px; }
    .chart-wrap { position: relative; }
    canvas {
      display: block;
      width: 100%;
      height: 720px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      cursor: crosshair;
    }
    main.fullscreen-view canvas { height: max(680px, calc(100vh - 190px)); }
    .chart-tooltip {
      position: absolute;
      z-index: 4;
      display: none;
      min-width: 230px;
      max-width: min(440px, calc(100% - 24px));
      max-height: 60%;
      overflow: auto;
      padding: 9px 11px;
      border: 1px solid rgba(23, 32, 42, .22);
      border-radius: 6px;
      background: rgba(255, 255, 255, .96);
      box-shadow: 0 5px 18px rgba(23, 32, 42, .16);
      color: var(--ink);
      font-size: 12px;
      line-height: 1.45;
      pointer-events: none;
    }
    .chart-tooltip strong { display: block; margin-bottom: 5px; font-size: 13px; }
    .chart-tooltip-row { display: grid; grid-template-columns: 9px minmax(100px, 1fr) auto; gap: 7px; align-items: center; white-space: nowrap; }
    .chart-tooltip-dot { width: 7px; height: 7px; border-radius: 50%; }
    .legend { display: flex; flex-wrap: wrap; gap: 8px 14px; margin-top: 10px; color: var(--muted); font-size: 12px; }
    .legend span { display: inline-flex; align-items: center; gap: 6px; }
    .swatch { width: 18px; height: 3px; border-radius: 999px; background: currentColor; }
    .benchmark-note { margin: 8px 0 0; color: var(--muted); font-size: 12px; line-height: 1.5; }
    .table-panel, .method-panel { margin-top: 14px; padding: 14px; overflow-x: auto; }
    table { width: 100%; min-width: 1120px; border-collapse: collapse; font-size: 13px; }
    th, td { padding: 9px 8px; border-bottom: 1px solid var(--line); text-align: right; white-space: nowrap; }
    th:first-child, td:first-child, th:nth-child(2), td:nth-child(2), th:nth-child(3), td:nth-child(3) { text-align: left; }
    th { color: var(--muted); font-size: 12px; font-weight: 800; }
    .positive { color: #b03a2e; }
    .negative { color: #237447; }
    .empty { padding: 12px; color: var(--muted); font-size: 13px; line-height: 1.7; }
    .method-panel p { margin: 0; color: var(--muted); font-size: 12px; line-height: 1.7; }
    .summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin-bottom: 14px; }
    .summary-item { padding: 10px 12px; border: 1px solid var(--line); background: #fbfcfd; }
    .summary-item span { display: block; color: var(--muted); font-size: 11px; margin-bottom: 4px; }
    .summary-item strong { display: block; font-size: 16px; }
    @media (max-width: 760px) { .summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
    @media (max-width: 980px) {
      .page-head { display: grid; }
      .source-note { white-space: normal; }
      .workspace { grid-template-columns: 1fr; }
      .controls { position: static; max-height: none; }
      canvas { height: 560px; }
    }
  </style>
</head>
<body>
<div data-myinvest-header></div>
<script src="https://invest.okbbc.com/header.js" charset="utf-8" defer></script>
<header class="site-header">
  <nav class="site-nav" aria-label="研究入口">
    <a class="brand" href="/index.html">研究入口</a>
    <a href="/{CODE}_mainline_background.html">资产配置研究</a>
    <a class="active" href="/{CODE}_alpha.html">资产 Alpha 研究</a>
    <a href="/{CODE}_strategy_portfolio.html">策略组合研究</a>
    <a href="/{CODE}_new_high_low.html">Log回归通道</a>
    <a href="/{CODE}_zigzag_strategy.html">ZigZag拐点策略</a>
  </nav>
</header>
<main id="pageRoot">
  <header class="page-head">
    <div>
      <h1>资产 Alpha 研究</h1>
      <p class="subtitle">观察策略资产相对宽基的累计超额表现；周期背景仅作市场环境标记，不参与交易信号。</p>
    </div>
    <span class="source-note" id="sourceNote"></span>
  </header>
  <div class="workspace">
    <aside class="controls" aria-label="Alpha选择设置">
      <h2>比较设置</h2>
      <div class="control-section">
        <h3>策略基金 / 策略指数</h3>
        <div id="strategyPicker"></div>
      </div>
      <div class="control-section">
        <h3>宽基基准</h3>
        <div id="benchmarkPicker"></div>
      </div>
      <div class="control-section">
        <div class="date-range">
          <label>开始日期<input id="startDate" type="date"></label>
          <label>结束日期<input id="endDate" type="date"></label>
        </div>
      </div>
      <div class="button-row">
        <button class="primary" id="selectDefault" type="button">默认组合</button>
        <button id="clearSelection" type="button">清空选择</button>
        <button id="resetRange" type="button">恢复全区间</button>
        <button id="fullscreenButton" type="button">全屏图表</button>
      </div>
    </aside>
    <section class="chart-panel">
      <div class="chart-head">
        <strong id="chartTitle">策略相对宽基的 Alpha 曲线</strong>
        <span>拖拽放大，双击恢复</span>
      </div>
      <div class="chart-wrap">
        <canvas id="alphaChart" aria-label="资产 Alpha 相对收益图"></canvas>
        <div class="chart-tooltip" id="chartTooltip"></div>
      </div>
      <div class="legend" id="legend"></div>
      <p class="benchmark-note" id="benchmarkNote"></p>
    </section>
  </div>
  <section class="table-panel">
    <h2>主图组合结果</h2>
    <div id="portfolioSummary"></div>
    <h2 id="tableTitle">单项策略 / 宽基比较</h2>
    <div id="alphaTable"></div>
  </section>
  <section class="method-panel">
    <h2>口径说明</h2>
    <p>主图 Alpha = 策略组合累计净值 ÷ 宽基组合累计净值 - 1；策略和宽基均在选择多项时按季度再平衡等权合成，单选时退化为单个资产。年化超额收益按相对净值复合年化；下表同时列出每个策略与每个宽基的独立比较。回归 Alpha 为日收益回归截距乘以 252，仅作辅助参考。</p>
  </section>
</main>
<div data-myinvest-footer></div>
<script src="https://invest.okbbc.com/footer.js" charset="utf-8" defer></script>
<script>
const payload = __PAYLOAD__;
const pageRoot = document.getElementById("pageRoot");
const strategyPicker = document.getElementById("strategyPicker");
const benchmarkPicker = document.getElementById("benchmarkPicker");
const startDateInput = document.getElementById("startDate");
const endDateInput = document.getElementById("endDate");
const chartTitle = document.getElementById("chartTitle");
const benchmarkNote = document.getElementById("benchmarkNote");
const sourceNote = document.getElementById("sourceNote");
const alphaTable = document.getElementById("alphaTable");
const tableTitle = document.getElementById("tableTitle");
const legend = document.getElementById("legend");
const canvas = document.getElementById("alphaChart");
const chartTooltip = document.getElementById("chartTooltip");
const fullscreenButton = document.getElementById("fullscreenButton");
const portfolioSummary = document.getElementById("portfolioSummary");
const colors = ["#1565c0", "#d84315", "#2e7d32", "#7b1fa2", "#c69200", "#00838f", "#c62828", "#5d4037", "#3949ab", "#558b2f", "#ad1457", "#00695c"];
const candidates = payload.candidates || [];
const candidateMap = new Map(candidates.map((item) => [item.code, item]));
let viewStartDate = payload.analysis.firstDate;
let viewEndDate = payload.analysis.lastDate;
let dragStartX = null;
let dragCurrentX = null;
let chartGeometry = null;
let hoverPoint = null;

function raw(item) {
  return (item?.series || [])
    .map((point) => ({ date: point.trade_date, close: Number(point.close) }))
    .filter((point) => point.date && Number.isFinite(point.close) && point.close > 0)
    .sort((left, right) => left.date.localeCompare(right.date));
}

function mapRaw(item) { return new Map(raw(item).map((point) => [point.date, point.close])); }
function fmtPct(value, digits = 1) {
  if (!Number.isFinite(value)) return "-";
  const sign = value > 0 ? "+" : "";
  return `${sign}${(value * 100).toFixed(digits)}%`;
}
function fmtNumber(value, digits = 2) { return Number.isFinite(value) ? value.toFixed(digits) : "-"; }
function selectedBy(kind) {
  const root = kind === "strategy" ? strategyPicker : benchmarkPicker;
  return Array.from(root.querySelectorAll("input:checked"))
    .map((input) => candidateMap.get(input.value))
    .filter(Boolean);
}
function inputRow(item, kind) {
  return `<label class="index-option"><input type="checkbox" data-kind="${kind}" value="${item.code}"><span title="${item.name} ${item.code}">${item.name}<small>${item.code} · ${item.returnType || "行情"}</small></span></label>`;
}
function renderPickers() {
  const strategyItems = candidates.filter((item) => item.group === "A股策略");
  const benchmarkItems = candidates.filter((item) => item.group === "A股宽基");
  strategyPicker.innerHTML = strategyItems.length ? strategyItems.map((item) => inputRow(item, "strategy")).join("") : `<div class="empty">没有可用策略资产。</div>`;
  benchmarkPicker.innerHTML = benchmarkItems.length ? benchmarkItems.map((item) => inputRow(item, "benchmark")).join("") : `<div class="empty">没有可用宽基资产。</div>`;
  setDefaults();
  document.querySelectorAll(".controls input[type=checkbox]").forEach((input) => input.addEventListener("change", update));
}
function setDefaults() {
  strategyPicker.querySelectorAll("input").forEach((input) => { input.checked = input.value === "480092.CNI"; });
  benchmarkPicker.querySelectorAll("input").forEach((input) => { input.checked = input.value === "H00300.CSI"; });
}
function commonDates(left, right) {
  const rightMap = mapRaw(right);
  return raw(left).map((point) => point.date).filter((date) => rightMap.has(date));
}
function directAlpha(strategy, benchmark) {
  const strategyMap = mapRaw(strategy);
  const benchmarkMap = mapRaw(benchmark);
  const dates = Array.from(strategyMap.keys()).filter((date) => benchmarkMap.has(date)).sort();
  if (dates.length < 2) return null;
  const firstStrategy = strategyMap.get(dates[0]);
  const firstBenchmark = benchmarkMap.get(dates[0]);
  const points = [{ date: dates[0], value: 1 }];
  const activeReturns = [];
  const strategyReturns = [];
  const benchmarkReturns = [];
  let relative = 1;
  for (let index = 1; index < dates.length; index += 1) {
    const previousDate = dates[index - 1];
    const date = dates[index];
    const strategyReturn = strategyMap.get(date) / strategyMap.get(previousDate) - 1;
    const benchmarkReturn = benchmarkMap.get(date) / benchmarkMap.get(previousDate) - 1;
    const activeReturn = (1 + strategyReturn) / (1 + benchmarkReturn) - 1;
    strategyReturns.push(strategyReturn);
    benchmarkReturns.push(benchmarkReturn);
    activeReturns.push(activeReturn);
    relative *= 1 + activeReturn;
    points.push({ date, value: relative });
  }
  return { dates, points, activeReturns, strategyReturns, benchmarkReturns, firstStrategy, firstBenchmark };
}
function quarterOf(date) { return date.slice(0, 4) + "-Q" + (Math.floor((Number(date.slice(5, 7)) - 1) / 3) + 1); }
function compositeBenchmark(items) {
  if (!items.length) return [];
  if (items.length === 1) return raw(items[0]).map((point) => ({ date: point.date, value: point.close / raw(items[0])[0].close }));
  const maps = items.map(mapRaw);
  const dates = Array.from(maps[0].keys()).filter((date) => maps.every((map) => map.has(date))).sort();
  if (dates.length < 2) return [];
  const equalWeight = 1 / items.length;
  let value = 1;
  let weights = items.map(() => equalWeight);
  let previousQuarter = "";
  const points = [{ date: dates[0], value }];
  for (let index = 1; index < dates.length; index += 1) {
    const date = dates[index];
    const quarter = quarterOf(date);
    if (quarter !== previousQuarter && index > 1) weights = items.map(() => equalWeight);
    previousQuarter = quarter;
    const returns = maps.map((map) => map.get(date) / map.get(dates[index - 1]) - 1);
    const portfolioReturn = returns.reduce((sum, itemReturn, itemIndex) => sum + weights[itemIndex] * itemReturn, 0);
    value *= 1 + portfolioReturn;
    points.push({ date, value });
    weights = weights.map((weight, itemIndex) => weight * (1 + returns[itemIndex]) / (1 + portfolioReturn));
  }
  return points;
}
function alphaAgainstComposite(strategy, benchmarkSeries) {
  const strategyMap = new Map(strategy.map((point) => [point.date, point.value]));
  const benchmarkMap = new Map(benchmarkSeries.map((point) => [point.date, point.value]));
  const dates = Array.from(strategyMap.keys()).filter((date) => benchmarkMap.has(date)).sort();
  if (dates.length < 2) return null;
  let relative = 1;
  const points = [{ date: dates[0], value: relative }];
  const activeReturns = [];
  const strategyReturns = [];
  const benchmarkReturns = [];
  for (let index = 1; index < dates.length; index += 1) {
    const date = dates[index];
    const previousDate = dates[index - 1];
    const strategyReturn = strategyMap.get(date) / strategyMap.get(previousDate) - 1;
    const benchmarkReturn = benchmarkMap.get(date) / benchmarkMap.get(previousDate) - 1;
    const activeReturn = (1 + strategyReturn) / (1 + benchmarkReturn) - 1;
    strategyReturns.push(strategyReturn);
    benchmarkReturns.push(benchmarkReturn);
    activeReturns.push(activeReturn);
    relative *= 1 + activeReturn;
    points.push({ date, value: relative });
  }
  return { dates, points, activeReturns, strategyReturns, benchmarkReturns };
}
function regressionAlpha(result) {
  if (!result || result.strategyReturns?.length < 20) return { beta: NaN, alpha: NaN, trackingError: NaN, informationRatio: NaN };
  const pairs = result.strategyReturns.map((value, index) => [value, result.benchmarkReturns[index]]).filter((pair) => pair.every(Number.isFinite));
  const meanS = pairs.reduce((sum, pair) => sum + pair[0], 0) / pairs.length;
  const meanB = pairs.reduce((sum, pair) => sum + pair[1], 0) / pairs.length;
  let covariance = 0;
  let variance = 0;
  pairs.forEach(([s, b]) => { covariance += (s - meanS) * (b - meanB); variance += (b - meanB) ** 2; });
  const beta = variance > 0 ? covariance / variance : NaN;
  const residual = pairs.map(([s, b]) => s - (Number.isFinite(beta) ? beta * b : 0));
  const meanResidual = residual.reduce((sum, value) => sum + value, 0) / residual.length;
  const active = pairs.map(([s, b]) => s - b);
  const activeMean = active.reduce((sum, value) => sum + value, 0) / active.length;
  const activeStd = Math.sqrt(active.reduce((sum, value) => sum + (value - activeMean) ** 2, 0) / Math.max(1, active.length - 1));
  const trackingError = activeStd * Math.sqrt(252);
  return { beta, alpha: meanResidual * 252, trackingError, informationRatio: trackingError > 0 ? activeMean * 252 / trackingError : NaN };
}
function relativeStats(result) {
  if (!result || result.points.length < 2) return null;
  const values = result.points.map((point) => point.value);
  const finalValue = values[values.length - 1];
  const days = Math.max(1, Math.round((new Date(result.dates[result.dates.length - 1]) - new Date(result.dates[0])) / 86400000));
  let peak = values[0];
  let maxDrawdown = 0;
  let maxDate = result.dates[0];
  values.forEach((value, index) => {
    if (value > peak) peak = value;
    const drawdown = value / peak - 1;
    if (drawdown < maxDrawdown) { maxDrawdown = drawdown; maxDate = result.dates[index]; }
  });
  const positiveDays = result.activeReturns.filter((value) => value > 0).length;
  return {
    cumulative: finalValue - 1,
    annual: Math.pow(finalValue, 365 / days) - 1,
    maxDrawdown,
    maxDate,
    positiveRate: result.activeReturns.length ? positiveDays / result.activeReturns.length : NaN,
    regression: regressionAlpha(result),
  };
}
function tableDirectResult(strategy, benchmark) {
  const result = directAlpha(strategy, benchmark);
  const stats = relativeStats(result);
  if (!result || !stats) return null;
  return { strategy, benchmark, result, stats };
}
function visibleDateRange(points) {
  return points.filter((point) => point.date >= viewStartDate && point.date <= viewEndDate);
}
function allChartSeries() {
  const strategies = selectedBy("strategy");
  const benchmarks = selectedBy("benchmark");
  const strategyPortfolio = compositeBenchmark(strategies);
  const benchmarkPortfolio = compositeBenchmark(benchmarks);
  const result = alphaAgainstComposite(strategyPortfolio, benchmarkPortfolio);
  if (!result) return [];
  return [{
    label: strategies.length === 1 ? strategies[0].name : `策略等权组合（${strategies.length}项）`,
    result,
    color: colors[0],
  }];
}
function drawCycleBlocks(ctx, geometry) {
  (payload.cycleBlocks || []).forEach((block) => {
    if (block.end_date < geometry.dates[0] || block.start_date > geometry.dates[geometry.dates.length - 1]) return;
    const start = Math.max(0, geometry.dates.findIndex((date) => date >= block.start_date));
    let end = geometry.dates.findIndex((date) => date > block.end_date);
    if (end < 0) end = geometry.dates.length - 1;
    if (start < 0 || end < start) return;
    const x1 = geometry.xAt(start);
    const x2 = geometry.xAt(end);
    ctx.fillStyle = block.state === "bull" ? "rgba(176,58,46,.08)" : "rgba(35,116,71,.08)";
    ctx.fillRect(x1, geometry.plotTop, Math.max(1, x2 - x1), geometry.plotBottom - geometry.plotTop);
    if (x2 - x1 > 90) {
      ctx.fillStyle = block.state === "bull" ? "rgba(176,58,46,.7)" : "rgba(35,116,71,.7)";
      ctx.font = "11px Microsoft YaHei, sans-serif";
      ctx.fillText(block.label || "", x1 + 6, geometry.plotTop + 16);
    }
  });
}
function drawChart() {
  const dpr = window.devicePixelRatio || 1;
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  canvas.width = Math.round(width * dpr);
  canvas.height = Math.round(height * dpr);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);
  const series = allChartSeries();
  const dates = Array.from(new Set(series.flatMap((item) => visibleDateRange(item.result.points).map((point) => point.date)))).sort();
  const plotLeft = 72;
  const plotRight = width - 24;
  const plotTop = 22;
  const plotBottom = height - 44;
  const plotWidth = Math.max(1, plotRight - plotLeft);
  const plotHeight = Math.max(1, plotBottom - plotTop);
  const xAt = (index) => plotLeft + (dates.length <= 1 ? 0 : index / (dates.length - 1)) * plotWidth;
  if (!dates.length) {
    ctx.fillStyle = "#66717f";
    ctx.font = "14px Microsoft YaHei, sans-serif";
    ctx.fillText("请至少选择一个策略和一个宽基。", plotLeft, height / 2);
    chartGeometry = null;
    return;
  }
  const pointsByDate = new Map(series.flatMap((item) => item.result.points.map((point) => [point.date, point.value])));
  const values = series.flatMap((item) => visibleDateRange(item.result.points).map((point) => (point.value - 1) * 100));
  values.push(0);
  let minValue = Math.min(...values);
  let maxValue = Math.max(...values);
  const span = Math.max(5, maxValue - minValue);
  minValue -= span * .08;
  maxValue += span * .08;
  const yAt = (value) => plotBottom - ((value - minValue) / (maxValue - minValue)) * plotHeight;
  const geometry = { dates, plotLeft, plotRight, plotTop, plotBottom, plotWidth, plotHeight, xAt, yAt };
  chartGeometry = geometry;
  drawCycleBlocks(ctx, geometry);
  ctx.strokeStyle = "#e5e9ef";
  ctx.lineWidth = 1;
  ctx.font = "11px Microsoft YaHei, sans-serif";
  ctx.fillStyle = "#66717f";
  for (let tick = 0; tick <= 5; tick += 1) {
    const value = minValue + (maxValue - minValue) * tick / 5;
    const y = yAt(value);
    ctx.beginPath(); ctx.moveTo(plotLeft, y); ctx.lineTo(plotRight, y); ctx.stroke();
    ctx.fillText(`${value.toFixed(1)}%`, 8, y + 4);
  }
  const zeroY = yAt(0);
  ctx.strokeStyle = "#46505c";
  ctx.lineWidth = 1.2;
  ctx.beginPath(); ctx.moveTo(plotLeft, zeroY); ctx.lineTo(plotRight, zeroY); ctx.stroke();
  ctx.fillStyle = "#46505c";
  ctx.fillText("0%", 38, zeroY + 4);
  const yearLabels = dates.filter((date, index) => index === 0 || date.slice(0, 4) !== dates[index - 1].slice(0, 4));
  yearLabels.forEach((date) => {
    const index = dates.indexOf(date);
    const x = xAt(index);
    ctx.strokeStyle = "#d8dee8";
    ctx.beginPath(); ctx.moveTo(x, plotBottom); ctx.lineTo(x, plotBottom + 5); ctx.stroke();
    ctx.fillStyle = "#66717f";
    ctx.fillText(date.slice(0, 4), x - 14, height - 18);
  });
  series.forEach((item) => {
    const map = new Map(item.result.points.map((point) => [point.date, point.value]));
    ctx.strokeStyle = item.color;
    ctx.lineWidth = 2.1;
    ctx.beginPath();
    let started = false;
    dates.forEach((date, index) => {
      if (!map.has(date)) { started = false; return; }
      const x = xAt(index);
      const y = yAt((map.get(date) - 1) * 100);
      if (!started) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y);
    });
    ctx.stroke();
  });
  if (hoverPoint && hoverPoint.index >= 0 && hoverPoint.index < dates.length) {
    const x = xAt(hoverPoint.index);
    ctx.strokeStyle = "rgba(23,32,42,.45)";
    ctx.setLineDash([4, 4]);
    ctx.beginPath(); ctx.moveTo(x, plotTop); ctx.lineTo(x, plotBottom); ctx.stroke();
    ctx.setLineDash([]);
  }
}
function renderLegend() {
  const series = allChartSeries();
  legend.innerHTML = series.map((item) => `<span style="color:${item.color}"><i class="swatch"></i>${item.label}</span>`).join("");
  const benchmarks = selectedBy("benchmark");
  if (!benchmarks.length) {
    benchmarkNote.textContent = "请选择至少一个宽基基准。";
    return;
  }
  benchmarkNote.textContent = benchmarks.length === 1
    ? `主图基准：${benchmarks[0].name}（${benchmarks[0].code}）。`
    : `主图基准：${benchmarks.map((item) => item.name).join("、")} 的季度再平衡等权组合；表格保留单独比较。`;
}
function renderSummaryText() {
  const strategies = selectedBy("strategy");
  const benchmarks = selectedBy("benchmark");
  const strategyLabel = strategies.length === 1 ? strategies[0].name : `策略等权组合（${strategies.length || 0}项）`;
  const benchmarkLabel = benchmarks.length === 1 ? benchmarks[0].name : `宽基等权组合（${benchmarks.length || 0}项）`;
  chartTitle.textContent = `${strategyLabel} ÷ ${benchmarkLabel}：Alpha 曲线`;
  sourceNote.textContent = `数据区间 ${viewStartDate} 至 ${viewEndDate}；仅使用已实现日行情`;
  tableTitle.textContent = `单项策略 / 宽基比较：${viewStartDate} 至 ${viewEndDate}`;
}
function renderPortfolioSummary() {
  const series = allChartSeries();
  if (!series.length) {
    portfolioSummary.innerHTML = `<div class="empty">请至少选择一个策略和一个宽基，且两者需要有重叠行情。</div>`;
    return;
  }
  const stats = relativeStats(series[0].result);
  const regression = stats.regression;
  portfolioSummary.innerHTML = `<div class="summary-grid"><div class="summary-item"><span>组合累计超额</span><strong class="${stats.cumulative >= 0 ? "positive" : "negative"}">${fmtPct(stats.cumulative)}</strong></div><div class="summary-item"><span>组合年化超额</span><strong class="${stats.annual >= 0 ? "positive" : "negative"}">${fmtPct(stats.annual)}</strong></div><div class="summary-item"><span>组合回归 Alpha</span><strong>${fmtPct(regression.alpha)}</strong></div><div class="summary-item"><span>组合相对最大回撤</span><strong class="negative">${fmtPct(stats.maxDrawdown)}</strong></div></div>`;
}
function renderTable() {
  const strategies = selectedBy("strategy");
  const benchmarks = selectedBy("benchmark");
  const rows = strategies.flatMap((strategy) => benchmarks.map((benchmark) => tableDirectResult(strategy, benchmark))).filter(Boolean).sort((left, right) => right.stats.annual - left.stats.annual);
  if (!rows.length) { alphaTable.innerHTML = `<div class="empty">请至少选择一个策略和一个宽基，且两者需要有重叠行情。</div>`; return; }
  alphaTable.innerHTML = `<table><thead><tr><th>排名</th><th>策略</th><th>宽基</th><th>累计超额</th><th>年化超额</th><th>回归 Alpha</th><th>Beta</th><th>跟踪误差</th><th>信息比率</th><th>相对最大回撤</th><th>最大回撤日期</th><th>正超额日占比</th></tr></thead><tbody>${rows.map((row, index) => {
    const r = row.stats.regression;
    return `<tr><td>${index + 1}</td><td>${row.strategy.name}</td><td>${row.benchmark.name}</td><td class="${row.stats.cumulative >= 0 ? "positive" : "negative"}">${fmtPct(row.stats.cumulative)}</td><td class="${row.stats.annual >= 0 ? "positive" : "negative"}">${fmtPct(row.stats.annual)}</td><td>${fmtPct(r.alpha)}</td><td>${fmtNumber(r.beta)}</td><td>${fmtPct(r.trackingError)}</td><td>${fmtNumber(r.informationRatio)}</td><td class="negative">${fmtPct(row.stats.maxDrawdown)}</td><td>${row.stats.maxDate}</td><td>${fmtPct(row.stats.positiveRate)}</td></tr>`;
  }).join("")}</tbody></table>`;
}
function renderTooltip(event) {
  if (!chartGeometry || !hoverPoint) return;
  const date = chartGeometry.dates[hoverPoint.index];
  const rows = allChartSeries().map((item) => {
    const point = item.result.points.find((candidate) => candidate.date === date);
    return point ? { item, value: point.value - 1 } : null;
  }).filter(Boolean).sort((left, right) => right.value - left.value);
  chartTooltip.innerHTML = `<strong>${date}</strong>${rows.map((row) => `<div class="chart-tooltip-row"><i class="chart-tooltip-dot" style="background:${row.item.color}"></i><span>${row.item.label}</span><b>${fmtPct(row.value)}</b></div>`).join("")}`;
  const rect = canvas.getBoundingClientRect();
  chartTooltip.style.display = "block";
  chartTooltip.style.left = `${Math.min(canvas.clientWidth - 390, Math.max(12, event.clientX - rect.left + 16))}px`;
  chartTooltip.style.top = `${Math.max(12, event.clientY - rect.top - 20)}px`;
}
function update() {
  renderSummaryText();
  drawChart();
  renderLegend();
  renderPortfolioSummary();
  renderTable();
  startDateInput.value = viewStartDate;
  endDateInput.value = viewEndDate;
}
function resetRange() {
  viewStartDate = payload.analysis.firstDate;
  viewEndDate = payload.analysis.lastDate;
  dragStartX = null;
  dragCurrentX = null;
  hoverPoint = null;
  chartTooltip.style.display = "none";
  update();
}
document.getElementById("selectDefault").addEventListener("click", () => { setDefaults(); update(); });
document.getElementById("clearSelection").addEventListener("click", () => { document.querySelectorAll(".controls input[type=checkbox]").forEach((input) => { input.checked = false; }); update(); });
document.getElementById("resetRange").addEventListener("click", resetRange);
fullscreenButton.addEventListener("click", () => {
  const active = pageRoot.classList.toggle("fullscreen-view");
  document.body.classList.toggle("chart-fullscreen", active);
  fullscreenButton.textContent = active ? "退出全屏" : "全屏图表";
  update();
});
document.addEventListener("keydown", (event) => { if (event.key === "Escape" && pageRoot.classList.contains("fullscreen-view")) { pageRoot.classList.remove("fullscreen-view"); document.body.classList.remove("chart-fullscreen"); fullscreenButton.textContent = "全屏图表"; update(); } });
function applyDateInputs() {
  if (!startDateInput.value || !endDateInput.value || startDateInput.value >= endDateInput.value) return;
  viewStartDate = startDateInput.value < payload.analysis.firstDate ? payload.analysis.firstDate : startDateInput.value;
  viewEndDate = endDateInput.value > payload.analysis.lastDate ? payload.analysis.lastDate : endDateInput.value;
  update();
}
startDateInput.min = payload.analysis.firstDate; startDateInput.max = payload.analysis.lastDate;
endDateInput.min = payload.analysis.firstDate; endDateInput.max = payload.analysis.lastDate;
startDateInput.addEventListener("change", applyDateInputs); endDateInput.addEventListener("change", applyDateInputs);
canvas.addEventListener("mousedown", (event) => {
  if (!chartGeometry) return;
  const rect = canvas.getBoundingClientRect();
  const x = event.clientX - rect.left;
  if (x < chartGeometry.plotLeft || x > chartGeometry.plotRight) return;
  dragStartX = x; dragCurrentX = x; chartTooltip.style.display = "none";
});
canvas.addEventListener("mousemove", (event) => {
  if (!chartGeometry) return;
  const rect = canvas.getBoundingClientRect();
  const x = event.clientX - rect.left;
  if (dragStartX !== null) { dragCurrentX = Math.max(chartGeometry.plotLeft, Math.min(chartGeometry.plotRight, x)); hoverPoint = null; drawChart(); return; }
  if (x < chartGeometry.plotLeft || x > chartGeometry.plotRight) { hoverPoint = null; chartTooltip.style.display = "none"; drawChart(); return; }
  const index = Math.max(0, Math.min(chartGeometry.dates.length - 1, Math.round((x - chartGeometry.plotLeft) / chartGeometry.plotWidth * (chartGeometry.dates.length - 1))));
  hoverPoint = { index }; drawChart(); renderTooltip(event);
});
canvas.addEventListener("mouseup", () => {
  if (dragStartX === null || dragCurrentX === null || !chartGeometry) return;
  if (Math.abs(dragCurrentX - dragStartX) >= 8) {
    const left = Math.min(dragStartX, dragCurrentX); const right = Math.max(dragStartX, dragCurrentX);
    const startIndex = Math.round((left - chartGeometry.plotLeft) / chartGeometry.plotWidth * (chartGeometry.dates.length - 1));
    const endIndex = Math.round((right - chartGeometry.plotLeft) / chartGeometry.plotWidth * (chartGeometry.dates.length - 1));
    viewStartDate = chartGeometry.dates[Math.max(0, startIndex)]; viewEndDate = chartGeometry.dates[Math.min(chartGeometry.dates.length - 1, endIndex)];
  }
  dragStartX = null; dragCurrentX = null; update();
});
canvas.addEventListener("mouseleave", () => { dragStartX = null; dragCurrentX = null; hoverPoint = null; chartTooltip.style.display = "none"; drawChart(); });
canvas.addEventListener("dblclick", resetRange);
window.addEventListener("resize", update);
renderPickers();
update();
</script>
</body>
</html>
'''
    html = html_template.replace("{CODE}", series.code.replace(".", "_"))
    html = html.replace("__PAYLOAD__", safe_json(payload))
    output_path.write_text(html, encoding="utf-8")


def write_strategy_portfolio_html(series: IndexSeries, output_path: Path, payload: dict[str, Any]) -> None:
    html_template = r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>策略组合研究</title>
  <style>
    :root { color-scheme: light; --ink:#17202a; --muted:#66717f; --line:#d8dee8; --bg:#f5f7f9; --panel:#fff; --main:#147a61; }
    * { box-sizing:border-box; }
    body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif; background:var(--bg); color:var(--ink); }
    body.chart-fullscreen { overflow:hidden; }
    .site-header { background:rgba(255,255,255,.94); border-bottom:1px solid var(--line); }
    .site-nav { width:min(1560px,calc(100vw - 28px)); min-height:50px; margin:0 auto; display:flex; align-items:center; gap:16px; overflow-x:auto; white-space:nowrap; }
    .brand { color:var(--ink); font-weight:800; text-decoration:none; }
    .site-nav a:not(.brand) { color:var(--muted); font-size:13px; text-decoration:none; }
    .site-nav a.active { color:var(--main); font-weight:700; }
    main { width:min(1560px,calc(100vw - 28px)); margin:8px auto 28px; }
    main.fullscreen-view { position:fixed; inset:0; z-index:1000; width:100vw; height:100vh; margin:0; padding:18px; overflow:auto; background:var(--bg); }
    .page-head { display:flex; justify-content:space-between; align-items:center; gap:14px; margin-bottom:8px; }
    h1 { margin:0; font-size:18px; line-height:1.2; letter-spacing:0; }
    .subtitle,.source-note { margin:5px 0 0; color:var(--muted); font-size:12px; line-height:1.5; }
    .source-note { white-space:nowrap; }
    .workspace { display:grid; grid-template-columns:300px minmax(0,1fr); gap:14px; align-items:start; }
    .controls,.chart-panel,.table-panel,.weights-panel,.method-panel { border:1px solid var(--line); border-radius:8px; background:var(--panel); box-shadow:0 10px 28px rgba(23,32,42,.05); }
    .controls { padding:12px; position:sticky; top:58px; max-height:calc(100vh - 68px); overflow:auto; }
    .controls h2,.table-panel h2,.weights-panel h2,.method-panel h2 { margin:0 0 10px; font-size:15px; }
    .control-section { border-top:1px solid var(--line); padding-top:12px; margin-top:12px; }
    .control-section h3 { margin:0 0 7px; color:var(--muted); font-size:12px; }
    .option { display:grid; grid-template-columns:18px minmax(0,1fr); gap:8px; align-items:center; min-height:31px; font-size:13px; }
    .option small { display:block; color:var(--muted); font-size:11px; }
    input[type="checkbox"] { width:16px; height:16px; accent-color:var(--main); }
    input[type="range"] { width:100%; accent-color:var(--main); }
    input[type="date"] { width:100%; min-height:34px; border:1px solid var(--line); border-radius:7px; padding:0 8px; font:inherit; }
    .range-label { display:flex; justify-content:space-between; gap:8px; color:var(--ink); font-size:13px; }
    .range-label output { color:var(--main); font-weight:800; }
    .date-range { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
    .date-range label { display:grid; gap:4px; color:var(--muted); font-size:11px; }
    .button-row { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; margin-top:12px; }
    button { min-height:34px; border:1px solid var(--line); border-radius:7px; background:#fff; color:var(--ink); font:inherit; font-size:12px; font-weight:700; cursor:pointer; }
    button.primary { border-color:var(--main); background:var(--main); color:#fff; }
    .chart-panel { padding:10px; }
    .chart-head { display:flex; justify-content:space-between; gap:12px; align-items:center; margin-bottom:10px; color:var(--muted); font-size:12px; }
    .chart-wrap { position:relative; }
    canvas { display:block; width:100%; height:690px; border:1px solid var(--line); border-radius:8px; background:#fff; cursor:crosshair; }
    main.fullscreen-view canvas { height:max(680px,calc(100vh - 190px)); }
    .chart-tooltip { position:absolute; z-index:4; display:none; min-width:230px; max-width:min(430px,calc(100% - 24px)); max-height:60%; overflow:auto; padding:9px 11px; border:1px solid rgba(23,32,42,.22); border-radius:6px; background:rgba(255,255,255,.96); box-shadow:0 5px 18px rgba(23,32,42,.16); font-size:12px; line-height:1.45; pointer-events:none; }
    .chart-tooltip strong { display:block; margin-bottom:5px; font-size:13px; }
    .chart-tooltip-row { display:grid; grid-template-columns:9px minmax(120px,1fr) auto; gap:7px; align-items:center; white-space:nowrap; }
    .chart-tooltip-dot { width:7px; height:7px; border-radius:50%; }
    .legend { display:flex; flex-wrap:wrap; gap:8px 14px; margin-top:10px; color:var(--muted); font-size:12px; }
    .legend span { display:inline-flex; align-items:center; gap:6px; }
    .swatch { width:18px; height:3px; border-radius:999px; background:currentColor; }
    .table-panel,.weights-panel,.method-panel { margin-top:14px; padding:14px; overflow-x:auto; }
    table { width:100%; min-width:1110px; border-collapse:collapse; font-size:13px; }
    th,td { padding:9px 8px; border-bottom:1px solid var(--line); text-align:right; white-space:nowrap; }
    th:first-child,td:first-child { text-align:left; }
    th { color:var(--muted); font-size:12px; font-weight:800; }
    .positive { color:#b03a2e; } .negative { color:#237447; }
    .weights-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:10px; }
    .weight-card { padding:11px; border:1px solid var(--line); background:#fbfcfd; }
    .weight-card h3 { margin:0 0 8px; font-size:13px; }
    .weight-stack { display:flex; height:16px; overflow:hidden; border:1px solid var(--line); }
    .weight-stack i { min-width:1px; height:100%; }
    .weight-list { display:grid; gap:4px; margin-top:8px; color:var(--muted); font-size:12px; }
    .weight-list div { display:grid; grid-template-columns:8px minmax(0,1fr) auto; gap:6px; align-items:center; }
    .weight-list i { width:7px; height:7px; }
    .weight-list span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .method-panel p { margin:0; color:var(--muted); font-size:12px; line-height:1.7; }
    .empty { padding:12px; color:var(--muted); font-size:13px; }
    @media (max-width:980px) { .workspace{grid-template-columns:1fr}.controls{position:static;max-height:none}.page-head{display:grid}.source-note{white-space:normal}canvas{height:540px} }
  </style>
</head>
<body>
<div data-myinvest-header></div>
<script src="https://invest.okbbc.com/header.js" charset="utf-8" defer></script>
<header class="site-header"><nav class="site-nav" aria-label="研究入口">
  <a class="brand" href="/index.html">研究入口</a>
  <a href="/{CODE}_mainline_background.html">资产配置研究</a>
  <a href="/{CODE}_alpha.html">资产 Alpha 研究</a>
  <a class="active" href="/{CODE}_strategy_portfolio.html">策略组合研究</a>
  <a href="/{CODE}_new_high_low.html">Log回归通道</a>
  <a href="/{CODE}_zigzag_strategy.html">ZigZag拐点策略</a>
</nav></header>
<main id="pageRoot">
  <header class="page-head"><div><h1>策略组合研究</h1><p class="subtitle">比较四个策略资产在不同权重模型和再平衡策略下的组合净值。</p></div><span class="source-note" id="sourceNote"></span></header>
  <div class="workspace">
    <aside class="controls" aria-label="组合设置">
      <h2>组合设置</h2>
      <div class="control-section"><h3>策略资产</h3><div id="assetPicker"></div></div>
      <div class="control-section"><h3>配置方式</h3>
        <label class="option"><input class="method-check" type="checkbox" value="equal" checked><span>等权<small>每项目标权重相同</small></span></label>
        <label class="option"><input class="method-check" type="checkbox" value="inverse"><span>逆波动<small>权重 ∝ 1 / 滚动波动率</small></span></label>
        <label class="option"><input class="method-check" type="checkbox" value="erc" checked><span>风险平价（ERC）<small>按完整协方差矩阵等风险贡献</small></span></label>
      </div>
      <div class="control-section"><h3>再平衡方式</h3>
        <label class="option"><input class="rebalance-check" type="checkbox" value="quarterly" checked><span>季度再平衡</span></label>
        <label class="option"><input class="rebalance-check" type="checkbox" value="annual"><span>年度再平衡</span></label>
        <label class="option"><input class="rebalance-check" type="checkbox" value="gain"><span>涨幅触发再平衡<small>任一策略涨幅达到阈值后调回目标权重</small></span></label>
        <label class="option"><input class="rebalance-check" type="checkbox" value="drift"><span>权重偏离触发<small>实际权重相对目标权重偏离达到阈值后调仓</small></span></label>
        <label class="option"><input class="rebalance-check" type="checkbox" value="none"><span>不再平衡<small>初始等权，之后权重自然漂移</small></span></label>
      </div>
      <div class="control-section"><label class="range-label" for="lookbackSlider">风险估计回看期 <output id="lookbackValue">120日</output></label><input id="lookbackSlider" type="range" min="40" max="250" step="10" value="120"></div>
      <div class="control-section"><label class="range-label" for="gainSlider">涨幅触发阈值 <output id="gainValue">20%</output></label><input id="gainSlider" type="range" min="5" max="60" step="5" value="20"></div>
      <div class="control-section"><label class="range-label" for="driftSlider">权重偏离阈值 <output id="driftValue">20%</output></label><input id="driftSlider" type="range" min="5" max="40" step="5" value="20"></div>
      <div class="control-section"><div class="date-range"><label>开始日期<input id="startDate" type="date"></label><label>结束日期<input id="endDate" type="date"></label></div></div>
      <div class="button-row"><button class="primary" id="selectDefault" type="button">默认组合</button><button id="clearSelection" type="button">清空曲线</button><button id="resetRange" type="button">恢复全区间</button><button id="fullscreenButton" type="button">全屏图表</button></div>
    </aside>
    <section class="chart-panel"><div class="chart-head"><strong id="chartTitle">组合净值对比</strong><span>拖拽放大，双击恢复</span></div><div class="chart-wrap"><canvas id="portfolioChart" aria-label="策略组合净值对比图"></canvas><div id="chartTooltip" class="chart-tooltip"></div></div><div id="legend" class="legend"></div></section>
  </div>
  <section class="table-panel"><h2 id="tableTitle">组合结果</h2><div id="portfolioTable"></div></section>
  <section class="weights-panel"><h2>当前组合权重</h2><div id="weightsPanel" class="weights-grid"></div></section>
  <section class="method-panel"><h2>计算口径</h2><p>所有组合从共同可用的首日开始计算。等权在调仓日令目标权重相同；逆波动按调仓日前已完成的滚动日收益波动率倒数分配；ERC 风险平价使用同一窗口的完整协方差矩阵，使各资产的组合风险贡献尽量相等。涨幅触发方式在任一策略相对上次调仓参考价涨幅达到阈值后，于下一交易日调回目标权重；权重偏离方式以最近一次调仓冻结的目标权重为基准，任一资产实际权重相对该目标的偏离达到阈值时调仓。调仓目标仅使用前一交易日及更早数据，并从当前交易日收益开始生效；季度和年度均在该周期首个交易日执行。初始资金等权配置，未发生调仓前权重随涨跌自然漂移。</p></section>
</main>
<div data-myinvest-footer></div>
<script src="https://invest.okbbc.com/footer.js" charset="utf-8" defer></script>
<script>
const payload = __PAYLOAD__;
const candidates = (payload.candidates || []).filter((item) => item.group === "A股策略");
const colors = ["#1565c0","#d84315","#2e7d32","#7b1fa2","#c69200","#00838f","#c62828","#5d4037","#3949ab"];
const assetColors = ["#1565c0","#d84315","#2e7d32","#7b1fa2"];
const assetPicker = document.getElementById("assetPicker");
const canvas = document.getElementById("portfolioChart");
const chartTooltip = document.getElementById("chartTooltip");
const legend = document.getElementById("legend");
const portfolioTable = document.getElementById("portfolioTable");
const weightsPanel = document.getElementById("weightsPanel");
const sourceNote = document.getElementById("sourceNote");
const lookbackSlider = document.getElementById("lookbackSlider");
const lookbackValue = document.getElementById("lookbackValue");
const gainSlider = document.getElementById("gainSlider");
const gainValue = document.getElementById("gainValue");
const driftSlider = document.getElementById("driftSlider");
const driftValue = document.getElementById("driftValue");
const startDateInput = document.getElementById("startDate");
const endDateInput = document.getElementById("endDate");
const pageRoot = document.getElementById("pageRoot");
const fullscreenButton = document.getElementById("fullscreenButton");
let viewStartDate = payload.analysis.firstDate;
let viewEndDate = payload.analysis.lastDate;
let dragStartX = null, dragCurrentX = null, hoverPoint = null, chartGeometry = null;
const methodNames = { equal:"等权", inverse:"逆波动", erc:"风险平价（ERC）" };
const rebalanceNames = { quarterly:"季度再平衡", annual:"年度再平衡", gain:"涨幅触发", drift:"权重偏离", none:"不再平衡" };

function raw(item) { return (item.series || []).map((point) => ({date:point.trade_date,close:Number(point.close)})).filter((point) => point.date && Number.isFinite(point.close) && point.close > 0).sort((a,b) => a.date.localeCompare(b.date)); }
function fmtPct(value,digits=1) { if (!Number.isFinite(value)) return "-"; return `${value > 0 ? "+" : ""}${(value * 100).toFixed(digits)}%`; }
function fmtNumber(value,digits=2) { return Number.isFinite(value) ? value.toFixed(digits) : "-"; }
function selectedAssets() { return Array.from(assetPicker.querySelectorAll("input:checked")).map((input) => candidates.find((item) => item.code === input.value)).filter(Boolean); }
function selectedMethods() { return Array.from(document.querySelectorAll(".method-check:checked")).map((input) => input.value); }
function selectedRebalances() { return Array.from(document.querySelectorAll(".rebalance-check:checked")).map((input) => input.value); }
function renderPicker() { assetPicker.innerHTML = candidates.map((item) => `<label class="option"><input type="checkbox" value="${item.code}" checked><span>${item.name}<small>${item.code} · ${item.returnType}</small></span></label>`).join(""); assetPicker.querySelectorAll("input").forEach((input) => input.addEventListener("change", update)); }
function alignedPrices(items) {
  if (!items.length) return null;
  const maps = items.map((item) => new Map(raw(item).map((point) => [point.date,point.close])));
  const dates = Array.from(maps[0].keys()).filter((date) => maps.every((map) => map.has(date))).sort();
  if (dates.length < 2) return null;
  return { dates, prices:dates.map((date) => maps.map((map) => map.get(date))) };
}
function mean(values) { return values.reduce((sum,value) => sum + value,0) / values.length; }
function sampleStd(values) { if (values.length < 2) return NaN; const avg=mean(values); return Math.sqrt(values.reduce((sum,value) => sum + (value-avg) ** 2,0) / (values.length-1)); }
function normalize(weights) { const total=weights.reduce((sum,value) => sum + (Number.isFinite(value) && value > 0 ? value : 0),0); return total > 0 ? weights.map((value) => Math.max(0,value) / total) : weights.map(() => 1 / weights.length); }
function covariance(returns, count) {
  if (returns.length < 2) return null;
  const averages = Array.from({length:count},(_,i) => mean(returns.map((row) => row[i])));
  return Array.from({length:count},(_,i) => Array.from({length:count},(_,j) => returns.reduce((sum,row) => sum + (row[i]-averages[i]) * (row[j]-averages[j]),0) / Math.max(1,returns.length-1)));
}
function matrixVector(matrix, vector) { return matrix.map((row) => row.reduce((sum,value,index) => sum + value * vector[index],0)); }
function inverseVolWeights(returns, count) { const volatilities=Array.from({length:count},(_,i) => sampleStd(returns.map((row) => row[i]))); return normalize(volatilities.map((value) => Number.isFinite(value) && value > 1e-9 ? 1 / value : 0)); }
function ercWeights(returns, count) {
  const matrix = covariance(returns,count);
  if (!matrix) return Array.from({length:count},() => 1 / count);
  for (let i=0;i<count;i+=1) matrix[i][i] = Math.max(matrix[i][i],1e-10);
  let weights = inverseVolWeights(returns,count);
  for (let iteration=0;iteration<500;iteration+=1) {
    const marginal = matrixVector(matrix,weights);
    const contributions = weights.map((weight,index) => weight * marginal[index]);
    if (contributions.some((value) => !Number.isFinite(value) || value <= 0)) return inverseVolWeights(returns,count);
    const target = contributions.reduce((sum,value) => sum + value,0) / count;
    const error = Math.max(...contributions.map((value) => Math.abs(value / target - 1)));
    if (error < 1e-5) return weights;
    weights = normalize(weights.map((weight,index) => weight * target / contributions[index]));
  }
  return weights;
}
function targetWeights(method, returns, count) { if (method === "equal" || returns.length < 20) return Array.from({length:count},() => 1 / count); if (method === "inverse") return inverseVolWeights(returns,count); return ercWeights(returns,count); }
function periodChanged(previousDate,date,rebalance) {
  if (rebalance === "none" || rebalance === "gain" || rebalance === "drift") return false;
  if (rebalance === "annual") return previousDate.slice(0,4) !== date.slice(0,4);
  const previousQuarter = `${previousDate.slice(0,4)}-${Math.floor((Number(previousDate.slice(5,7))-1)/3)}`;
  const currentQuarter = `${date.slice(0,4)}-${Math.floor((Number(date.slice(5,7))-1)/3)}`;
  return previousQuarter !== currentQuarter;
}
function buildPortfolio(items,method,rebalance,lookback,gainTrigger,driftTrigger) {
  const aligned=alignedPrices(items); if (!aligned) return null;
  const {dates,prices}=aligned, count=items.length;
  let weights=Array.from({length:count},() => 1 / count), value=1, turnover=0, rebalanceCount=0, referencePrices=[...prices[0]], referenceWeights=[...weights];
  const points=[{date:dates[0],value}], weightPoints=[{date:dates[0],weights:[...weights]}], turnoverEvents=[], returns=[], pointsReturns=[];
  for (let index=1;index<dates.length;index+=1) {
    const gainReached = rebalance === "gain" && prices[index-1].some((price,itemIndex) => price / referencePrices[itemIndex] - 1 >= gainTrigger);
    const driftReached = rebalance === "drift" && weights.some((weight,itemIndex) => referenceWeights[itemIndex] > 0 && Math.abs(weight - referenceWeights[itemIndex]) / referenceWeights[itemIndex] >= driftTrigger);
    if (periodChanged(dates[index-1],dates[index],rebalance) || gainReached || driftReached) {
      const history=returns.slice(Math.max(0,returns.length-lookback));
      const target=targetWeights(method,history,count);
      const turnoverAmount=target.reduce((sum,weight,itemIndex) => sum + Math.abs(weight - weights[itemIndex]),0) / 2;
      turnover += turnoverAmount;
      turnoverEvents.push({date:dates[index],turnover:turnoverAmount});
      weights=target; rebalanceCount += 1;
      referencePrices=[...prices[index-1]];
      referenceWeights=[...target];
    }
    const dayReturns=prices[index].map((price,itemIndex) => price / prices[index-1][itemIndex] - 1);
    const portfolioReturn=dayReturns.reduce((sum,itemReturn,itemIndex) => sum + weights[itemIndex] * itemReturn,0);
    value *= 1 + portfolioReturn;
    weights=normalize(weights.map((weight,itemIndex) => weight * (1 + dayReturns[itemIndex])));
    returns.push(dayReturns); pointsReturns.push(portfolioReturn); points.push({date:dates[index],value}); weightPoints.push({date:dates[index],weights:[...weights]});
  }
  return { id:`${method}-${rebalance}`, method, rebalance, gainTrigger, driftTrigger, items, points, weightPoints, turnoverEvents, returns:pointsReturns, weights, turnover, rebalanceCount };
}
function portfolioSegment(portfolio) {
  const startIndex=Math.max(0,portfolio.points.findIndex((point) => point.date >= viewStartDate));
  let endIndex=portfolio.points.findIndex((point) => point.date > viewEndDate); if(endIndex<0) endIndex=portfolio.points.length; endIndex=Math.max(startIndex+1,endIndex);
  return { points:portfolio.points.slice(startIndex,endIndex), returns:portfolio.returns.slice(startIndex,Math.max(startIndex,endIndex-1)), weights:portfolio.weightPoints[Math.max(0,endIndex-1)].weights, turnover:portfolio.turnoverEvents.filter((event) => event.date >= viewStartDate && event.date <= viewEndDate).reduce((sum,event) => sum + event.turnover,0), rebalanceCount:portfolio.turnoverEvents.filter((event) => event.date >= viewStartDate && event.date <= viewEndDate).length };
}
function portfolioStats(portfolio) {
  const segment=portfolioSegment(portfolio), values=segment.points.map((point) => point.value), finalValue=values[values.length-1];
  const days=Math.max(1,Math.round((new Date(segment.points.at(-1).date)-new Date(segment.points[0].date))/86400000));
  let peak=values[0], maxDrawdown=0;
  values.forEach((value) => { peak=Math.max(peak,value); maxDrawdown=Math.min(maxDrawdown,value/peak-1); });
  const std=sampleStd(segment.returns), avg=segment.returns.length ? mean(segment.returns) : NaN;
  const total=finalValue/values[0]-1, annual=Math.pow(finalValue/values[0],365/days)-1, volatility=std*Math.sqrt(252);
  return { total, annual, volatility, sharpe:std > 0 ? avg/std*Math.sqrt(252) : NaN, maxDrawdown, calmar:maxDrawdown < 0 ? annual/Math.abs(maxDrawdown) : NaN, weights:segment.weights, turnover:segment.turnover, rebalanceCount:segment.rebalanceCount };
}
function portfolios() { const items=selectedAssets(), methods=selectedMethods(), rebalances=selectedRebalances(), lookback=Number(lookbackSlider.value), gainTrigger=Number(gainSlider.value)/100, driftTrigger=Number(driftSlider.value)/100; return methods.flatMap((method) => rebalances.map((rebalance) => buildPortfolio(items,method,rebalance,lookback,gainTrigger,driftTrigger))).filter(Boolean); }
function visible(points) { return points.filter((point) => point.date >= viewStartDate && point.date <= viewEndDate); }
function label(portfolio) { const rebalanceLabel=portfolio.rebalance === "gain" ? `${rebalanceNames.gain} ≥${(portfolio.gainTrigger*100).toFixed(0)}%` : portfolio.rebalance === "drift" ? `${rebalanceNames.drift} ≥${(portfolio.driftTrigger*100).toFixed(0)}%` : rebalanceNames[portfolio.rebalance]; return `${methodNames[portfolio.method]} · ${rebalanceLabel}`; }
function drawCycleBlocks(ctx,geometry) { (payload.cycleBlocks || []).forEach((block) => { if (block.end_date < geometry.dates[0] || block.start_date > geometry.dates.at(-1)) return; const start=Math.max(0,geometry.dates.findIndex((date)=>date>=block.start_date)); let end=geometry.dates.findIndex((date)=>date>block.end_date); if(end<0) end=geometry.dates.length-1; const x1=geometry.xAt(start),x2=geometry.xAt(end); ctx.fillStyle=block.state==="bull" ? "rgba(176,58,46,.08)" : "rgba(35,116,71,.08)"; ctx.fillRect(x1,geometry.top,Math.max(1,x2-x1),geometry.bottom-geometry.top); if(x2-x1>90){ctx.fillStyle=block.state==="bull" ? "rgba(176,58,46,.7)" : "rgba(35,116,71,.7)";ctx.font="11px Microsoft YaHei";ctx.fillText(block.label||"",x1+6,geometry.top+16);} }); }
function drawChart() {
  const dpr=window.devicePixelRatio||1,width=canvas.clientWidth,height=canvas.clientHeight; canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);const ctx=canvas.getContext("2d");ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,width,height);
  const series=portfolios(),dates=Array.from(new Set(series.flatMap((portfolio)=>visible(portfolio.points).map((point)=>point.date)))).sort(),left=72,right=width-24,top=22,bottom=height-44,plotWidth=Math.max(1,right-left),plotHeight=Math.max(1,bottom-top);
  if(!dates.length){ctx.fillStyle="#66717f";ctx.font="14px Microsoft YaHei";ctx.fillText("请至少选择一个策略、一个配置方式和一种再平衡方式。",left,height/2);chartGeometry=null;return;}
  const xAt=(index)=>left+(dates.length<=1?0:index/(dates.length-1))*plotWidth, values=series.flatMap((portfolio)=>visible(portfolio.points).map((point)=>(point.value-1)*100));values.push(0);let min=Math.min(...values),max=Math.max(...values),span=Math.max(5,max-min);min-=span*.08;max+=span*.08;const yAt=(value)=>bottom-(value-min)/(max-min)*plotHeight;chartGeometry={dates,left,right,top,bottom,plotWidth,xAt};
  drawCycleBlocks(ctx,{dates,top,bottom,xAt});ctx.strokeStyle="#e5e9ef";ctx.lineWidth=1;ctx.font="11px Microsoft YaHei";ctx.fillStyle="#66717f";for(let tick=0;tick<=5;tick+=1){const value=min+(max-min)*tick/5,y=yAt(value);ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(right,y);ctx.stroke();ctx.fillText(`${value.toFixed(1)}%`,8,y+4);}const zero=yAt(0);ctx.strokeStyle="#46505c";ctx.lineWidth=1.2;ctx.beginPath();ctx.moveTo(left,zero);ctx.lineTo(right,zero);ctx.stroke();
  dates.filter((date,index)=>index===0||date.slice(0,4)!==dates[index-1].slice(0,4)).forEach((date)=>{const index=dates.indexOf(date),x=xAt(index);ctx.strokeStyle="#d8dee8";ctx.beginPath();ctx.moveTo(x,bottom);ctx.lineTo(x,bottom+5);ctx.stroke();ctx.fillStyle="#66717f";ctx.fillText(date.slice(0,4),x-14,height-18);});
  series.forEach((portfolio,index)=>{const map=new Map(portfolio.points.map((point)=>[point.date,point.value]));ctx.strokeStyle=colors[index%colors.length];ctx.lineWidth=2.1;ctx.beginPath();let started=false;dates.forEach((date,dateIndex)=>{if(!map.has(date)){started=false;return;}const x=xAt(dateIndex),y=yAt((map.get(date)-1)*100);if(!started){ctx.moveTo(x,y);started=true;}else ctx.lineTo(x,y);});ctx.stroke();});
  if(hoverPoint && hoverPoint.index>=0 && hoverPoint.index<dates.length){const x=xAt(hoverPoint.index);ctx.strokeStyle="rgba(23,32,42,.45)";ctx.setLineDash([4,4]);ctx.beginPath();ctx.moveTo(x,top);ctx.lineTo(x,bottom);ctx.stroke();ctx.setLineDash([]);}
}
function renderLegend() { legend.innerHTML=portfolios().map((portfolio,index)=>`<span style="color:${colors[index%colors.length]}"><i class="swatch"></i>${label(portfolio)}</span>`).join(""); }
function renderTable() { const rows=portfolios().map((portfolio)=>({portfolio,stats:portfolioStats(portfolio)})).sort((a,b)=>b.stats.annual-a.stats.annual); document.getElementById("tableTitle").textContent=`组合结果：${viewStartDate} 至 ${viewEndDate}`; if(!rows.length){portfolioTable.innerHTML=`<div class="empty">请选择组合方案。</div>`;return;} portfolioTable.innerHTML=`<table><thead><tr><th>组合</th><th>累计收益</th><th>年化</th><th>波动率</th><th>夏普</th><th>最大回撤</th><th>Calmar</th><th>累计换手</th><th>调仓次数</th><th>区间末权重</th></tr></thead><tbody>${rows.map(({portfolio,stats})=>`<tr><td>${label(portfolio)}</td><td class="${stats.total>=0?"positive":"negative"}">${fmtPct(stats.total)}</td><td class="${stats.annual>=0?"positive":"negative"}">${fmtPct(stats.annual)}</td><td>${fmtPct(stats.volatility)}</td><td>${fmtNumber(stats.sharpe)}</td><td class="negative">${fmtPct(stats.maxDrawdown)}</td><td>${fmtNumber(stats.calmar)}</td><td>${fmtPct(stats.turnover)}</td><td>${stats.rebalanceCount}</td><td>${portfolio.items.map((item,index)=>`${item.name} ${(stats.weights[index]*100).toFixed(1)}%`).join("；")}</td></tr>`).join("")}</tbody></table>`; }
function renderWeights() { const series=portfolios(); if(!series.length){weightsPanel.innerHTML=`<div class="empty">请选择组合方案。</div>`;return;} weightsPanel.innerHTML=series.map((portfolio)=>{const stats=portfolioStats(portfolio),stack=stats.weights.map((weight,index)=>`<i style="width:${weight*100}%;background:${assetColors[index%assetColors.length]}"></i>`).join(""),list=portfolio.items.map((item,index)=>`<div><i style="background:${assetColors[index%assetColors.length]}"></i><span>${item.name}</span><b>${(stats.weights[index]*100).toFixed(1)}%</b></div>`).join("");return `<article class="weight-card"><h3>${label(portfolio)}</h3><div class="weight-stack">${stack}</div><div class="weight-list">${list}</div></article>`;}).join(""); }
function renderTooltip(event) { if(!chartGeometry || !hoverPoint)return;const date=chartGeometry.dates[hoverPoint.index],rows=portfolios().map((portfolio,index)=>{const point=portfolio.points.find((item)=>item.date===date);return point?{portfolio,index,value:point.value-1}:null;}).filter(Boolean).sort((a,b)=>b.value-a.value);chartTooltip.innerHTML=`<strong>${date}</strong>${rows.map((row)=>`<div class="chart-tooltip-row"><i class="chart-tooltip-dot" style="background:${colors[row.index%colors.length]}"></i><span>${label(row.portfolio)}</span><b>${fmtPct(row.value)}</b></div>`).join("")}`;const rect=canvas.getBoundingClientRect();chartTooltip.style.display="block";chartTooltip.style.left=`${Math.min(canvas.clientWidth-390,Math.max(12,event.clientX-rect.left+16))}px`;chartTooltip.style.top=`${Math.max(12,event.clientY-rect.top-20)}px`; }
function update(){lookbackValue.textContent=`${lookbackSlider.value}日`;gainValue.textContent=`${gainSlider.value}%`;driftValue.textContent=`${driftSlider.value}%`;sourceNote.textContent=`${selectedAssets().length}项策略 · ${selectedMethods().length}种权重模型 · ${selectedRebalances().length}种再平衡；所有风险估计不使用当日及未来数据`;drawChart();renderLegend();renderTable();renderWeights();startDateInput.value=viewStartDate;endDateInput.value=viewEndDate;}
function setDefaults(){assetPicker.querySelectorAll("input").forEach((input)=>input.checked=true);document.querySelectorAll(".method-check").forEach((input)=>input.checked=["equal","erc"].includes(input.value));document.querySelectorAll(".rebalance-check").forEach((input)=>input.checked=input.value==="quarterly");}
function resetRange(){viewStartDate=payload.analysis.firstDate;viewEndDate=payload.analysis.lastDate;dragStartX=null;dragCurrentX=null;hoverPoint=null;chartTooltip.style.display="none";update();}
document.getElementById("selectDefault").addEventListener("click",()=>{setDefaults();update();});document.getElementById("clearSelection").addEventListener("click",()=>{document.querySelectorAll(".method-check,.rebalance-check").forEach((input)=>input.checked=false);update();});document.getElementById("resetRange").addEventListener("click",resetRange);lookbackSlider.addEventListener("input",update);gainSlider.addEventListener("input",update);driftSlider.addEventListener("input",update);document.querySelectorAll(".method-check,.rebalance-check").forEach((input)=>input.addEventListener("change",update));
fullscreenButton.addEventListener("click",()=>{const active=pageRoot.classList.toggle("fullscreen-view");document.body.classList.toggle("chart-fullscreen",active);fullscreenButton.textContent=active?"退出全屏":"全屏图表";update();});document.addEventListener("keydown",(event)=>{if(event.key==="Escape"&&pageRoot.classList.contains("fullscreen-view")){pageRoot.classList.remove("fullscreen-view");document.body.classList.remove("chart-fullscreen");fullscreenButton.textContent="全屏图表";update();}});
function applyDates(){if(!startDateInput.value||!endDateInput.value||startDateInput.value>=endDateInput.value)return;viewStartDate=startDateInput.value<payload.analysis.firstDate?payload.analysis.firstDate:startDateInput.value;viewEndDate=endDateInput.value>payload.analysis.lastDate?payload.analysis.lastDate:endDateInput.value;update();}startDateInput.min=payload.analysis.firstDate;startDateInput.max=payload.analysis.lastDate;endDateInput.min=payload.analysis.firstDate;endDateInput.max=payload.analysis.lastDate;startDateInput.addEventListener("change",applyDates);endDateInput.addEventListener("change",applyDates);
canvas.addEventListener("mousedown",(event)=>{if(!chartGeometry)return;const rect=canvas.getBoundingClientRect(),x=event.clientX-rect.left;if(x<chartGeometry.left||x>chartGeometry.right)return;dragStartX=x;dragCurrentX=x;chartTooltip.style.display="none";});canvas.addEventListener("mousemove",(event)=>{if(!chartGeometry)return;const rect=canvas.getBoundingClientRect(),x=event.clientX-rect.left;if(dragStartX!==null){dragCurrentX=Math.max(chartGeometry.left,Math.min(chartGeometry.right,x));hoverPoint=null;drawChart();return;}if(x<chartGeometry.left||x>chartGeometry.right){hoverPoint=null;chartTooltip.style.display="none";drawChart();return;}const index=Math.max(0,Math.min(chartGeometry.dates.length-1,Math.round((x-chartGeometry.left)/chartGeometry.plotWidth*(chartGeometry.dates.length-1))));hoverPoint={index};drawChart();renderTooltip(event);});canvas.addEventListener("mouseup",()=>{if(dragStartX===null||dragCurrentX===null||!chartGeometry)return;if(Math.abs(dragCurrentX-dragStartX)>=8){const left=Math.min(dragStartX,dragCurrentX),right=Math.max(dragStartX,dragCurrentX),startIndex=Math.round((left-chartGeometry.left)/chartGeometry.plotWidth*(chartGeometry.dates.length-1)),endIndex=Math.round((right-chartGeometry.left)/chartGeometry.plotWidth*(chartGeometry.dates.length-1));viewStartDate=chartGeometry.dates[Math.max(0,startIndex)];viewEndDate=chartGeometry.dates[Math.min(chartGeometry.dates.length-1,endIndex)];}dragStartX=null;dragCurrentX=null;update();});canvas.addEventListener("mouseleave",()=>{dragStartX=null;dragCurrentX=null;hoverPoint=null;chartTooltip.style.display="none";drawChart();});canvas.addEventListener("dblclick",resetRange);window.addEventListener("resize",update);
renderPicker();setDefaults();update();
</script>
</body>
</html>'''
    html = html_template.replace("{CODE}", series.code.replace(".", "_"))
    html = html.replace("__PAYLOAD__", safe_json(payload))
    output_path.write_text(html, encoding="utf-8")


def write_research_index_html(
    series: IndexSeries,
    records: pd.DataFrame,
    output_path: Path,
    log_html_path: Path,
    zigzag_html_path: Path,
    mainline_html_path: Path,
    alpha_html_path: Path,
    strategy_portfolio_html_path: Path,
    daily_csv_path: Path,
    records_csv_path: Path,
    legacy_html_path: Path,
) -> None:
    first = series.data.iloc[0]
    last = series.data.iloc[-1]
    high_count = int(series.data["turning_high"].sum())
    low_count = int(series.data["turning_low"].sum())
    data_range = f"{first['trade_date']} 至 {last['trade_date']}"
    latest_close = f"{float(last['close']):.2f}"
    html_template = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>研究入口</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #17202a;
      --muted: #66717f;
      --line: #d8dee8;
      --panel: #ffffff;
      --bg: #f5f7f9;
      --main: #1f7a68;
      --accent: #6c4ab6;
      --warn: #b45f06;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
      background: var(--bg);
      color: var(--ink);
    }
    .site-header {
      background: rgba(255, 255, 255, 0.94);
      border-bottom: 1px solid var(--line);
    }
    .site-nav {
      width: min(1180px, calc(100vw - 32px));
      min-height: 50px;
      margin: 0 auto;
      display: flex;
      align-items: center;
      gap: 16px;
      overflow-x: auto;
      white-space: nowrap;
    }
    .brand {
      color: var(--ink);
      font-weight: 800;
      text-decoration: none;
    }
    .site-nav a:not(.brand) {
      color: var(--muted);
      font-size: 13px;
      text-decoration: none;
    }
    .site-nav a.active {
      color: var(--main);
      font-weight: 700;
    }
    main {
      width: min(1180px, calc(100vw - 32px));
      margin: 24px auto 34px;
    }
    .page-head {
      margin-bottom: 16px;
    }
    h1 {
      margin: 0 0 8px;
      font-size: clamp(24px, 3vw, 34px);
      line-height: 1.15;
      letter-spacing: 0;
    }
    .subtitle {
      margin: 0;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.7;
    }
    .overview {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin: 16px 0;
    }
    .metric,
    .strategy-card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    .metric {
      min-height: 78px;
      padding: 12px 14px;
    }
    .label {
      display: block;
      margin-bottom: 8px;
      color: var(--muted);
      font-size: 12px;
    }
    .value {
      display: block;
      font-size: 18px;
      font-weight: 700;
      white-space: nowrap;
    }
    .section-title {
      margin: 24px 0 10px;
      font-size: 18px;
      line-height: 1.3;
      letter-spacing: 0;
    }
    .strategy-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(310px, 1fr));
      gap: 14px;
    }
    .strategy-card {
      min-height: 278px;
      padding: 18px;
      display: grid;
      gap: 14px;
      align-content: start;
    }
    .card-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: flex-start;
    }
    .card-head h2 {
      margin: 0;
      font-size: 20px;
      line-height: 1.3;
      letter-spacing: 0;
    }
    .status {
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 0 9px;
      border-radius: 999px;
      background: #e9f5f1;
      color: var(--main);
      font-size: 12px;
      font-weight: 700;
      white-space: nowrap;
    }
    .card-desc {
      margin: 0;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.65;
    }
    .tag-row {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .tag {
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 0 8px;
      border: 1px solid var(--line);
      border-radius: 999px;
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
    }
    .card-facts {
      margin: 0;
      padding: 0;
      list-style: none;
      display: grid;
      gap: 6px;
      color: var(--ink);
      font-size: 13px;
      line-height: 1.55;
    }
    .card-facts li::before {
      content: "";
      display: inline-block;
      width: 6px;
      height: 6px;
      margin-right: 8px;
      border-radius: 999px;
      background: var(--main);
      vertical-align: 1px;
    }
    .card-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 2px;
    }
    .button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 34px;
      padding: 0 13px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #ffffff;
      color: var(--ink);
      font-size: 13px;
      font-weight: 700;
      text-decoration: none;
    }
    .button.primary {
      border-color: var(--main);
      background: var(--main);
      color: #ffffff;
    }
    .resources {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
      gap: 10px;
      margin-top: 10px;
    }
    .resource-link {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      padding: 12px 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      color: var(--ink);
      text-decoration: none;
      font-size: 13px;
      line-height: 1.5;
    }
    .resource-link span {
      color: var(--muted);
      white-space: nowrap;
    }
    @media (max-width: 760px) {
      .overview {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
      .strategy-grid {
        grid-template-columns: 1fr;
      }
      .card-head {
        display: grid;
      }
      .value {
        font-size: 16px;
      }
    }
  </style>
</head>
<body>
<div data-myinvest-header></div>
<script src="https://invest.okbbc.com/header.js" charset="utf-8" defer></script>
<header class="site-header">
  <nav class="site-nav" aria-label="研究入口">
    <a class="brand active" href="/index.html">研究入口</a>
    <a href="__LOG_HREF__">Log回归通道</a>
    <a href="__ZIGZAG_HREF__">ZigZag拐点策略</a>
    <a href="__MAINLINE_HREF__">资产配置研究</a>
    <a href="__ALPHA_HREF__">资产 Alpha 研究</a>
    <a href="__STRATEGY_PORTFOLIO_HREF__">策略组合研究</a>
    <a href="__DAILY_HREF__">日线数据</a>
    <a href="__RECORDS_HREF__">拐点记录</a>
  </nav>
</header>
<main>
  <header class="page-head">
    <h1>各项研究入口</h1>
    <p class="subtitle">把每次研究都作为一个策略卡片沉淀；首页只负责进入研究，不直接承载具体图表。</p>
  </header>

  <section class="overview" aria-label="数据概览">
    <div class="metric"><span class="label">研究标的</span><span class="value">__CODE__</span></div>
    <div class="metric"><span class="label">数据区间</span><span class="value">__DATE_RANGE__</span></div>
    <div class="metric"><span class="label">最新收盘</span><span class="value">__LATEST_CLOSE__</span></div>
    <div class="metric"><span class="label">已收录研究</span><span class="value">5</span></div>
  </section>

  <h2 class="section-title">策略研究</h2>
  <section class="strategy-grid" aria-label="策略研究卡片">
    <article class="strategy-card">
      <div class="card-head">
        <h2>滚动 Log 回归通道</h2>
        <span class="status">当前主研究</span>
      </div>
      <p class="card-desc">用无未来函数的滚动 Log 回归通道观察趋势轨道，并动态比较买入持有与通道触发回放收益。</p>
      <div class="tag-row">
        <span class="tag">回看 1-10 年</span>
        <span class="tag">默认 2 年</span>
        <span class="tag">ZigZag 叠加</span>
        <span class="tag">中点线</span>
      </div>
      <ul class="card-facts">
        <li>通道宽度可调，默认 2.75σ</li>
        <li>ZigZag 阈值默认 15%，可调 5%-40%</li>
        <li>收益卡片动态显示持有年化、通道回放年化和超额年化</li>
      </ul>
      <div class="card-actions">
        <a class="button primary" href="__LOG_HREF__">打开研究</a>
        <a class="button" href="__DAILY_HREF__">查看数据</a>
      </div>
    </article>

    <article class="strategy-card">
      <div class="card-head">
        <h2>ZigZag 高低拐点策略</h2>
        <span class="status">历史研究</span>
      </div>
      <p class="card-desc">按标准 ZigZag 规则观察高低拐点形态，并使用无未来函数的 20% 回撤买入策略做真实回测。</p>
      <div class="tag-row">
        <span class="tag">阈值 5%-40%</span>
        <span class="tag">高低拐点</span>
        <span class="tag">趋势线勾选</span>
        <span class="tag">Y轴切换</span>
      </div>
      <ul class="card-facts">
        <li>当前默认拐点 __PIVOT_COUNT__ 个，高点 __HIGH_COUNT__ 个，低点 __LOW_COUNT__ 个</li>
        <li>ZigZag 折线中点线和交点差距只用于形态观察</li>
        <li>收益统计只来自无未来函数回测，并在主图显示 20% 策略和核心仓策略净值曲线</li>
      </ul>
      <div class="card-actions">
        <a class="button primary" href="__ZIGZAG_HREF__">打开研究</a>
        <a class="button" href="__RECORDS_HREF__">拐点记录</a>
      </div>
    </article>

    <article class="strategy-card">
      <div class="card-head">
        <h2>资产配置研究</h2>
        <span class="status">新研究</span>
      </div>
      <p class="card-desc">比较策略、宽基、产业主线、黄金、国债和海外市场，支持任意区间放大与动态统计。</p>
      <div class="tag-row">
        <span class="tag">多选指数</span>
        <span class="tag">牛熊背景</span>
        <span class="tag">阶段排名</span>
        <span class="tag">归一化对比</span>
      </div>
      <ul class="card-facts">
        <li>默认沪深300，可自由选择比较基准和人民币/美元口径</li>
        <li>图表可切换为相对自由现金流强弱，1.00x 代表同步</li>
        <li>表格按牛熊阶段显示自由现金流排名、阶段最强主线和差距</li>
      </ul>
      <div class="card-actions">
        <a class="button primary" href="__MAINLINE_HREF__">打开研究</a>
        <a class="button" href="__DAILY_HREF__">查看数据</a>
      </div>
    </article>

    <article class="strategy-card">
      <div class="card-head">
        <h2>资产 Alpha 研究</h2>
        <span class="status">新研究</span>
      </div>
      <p class="card-desc">比较策略基金与 A 股宽基的累计相对收益，观察策略是否持续跑赢基准。</p>
      <div class="tag-row">
        <span class="tag">策略可选</span>
        <span class="tag">宽基可选</span>
        <span class="tag">季度等权基准</span>
        <span class="tag">Alpha表格</span>
      </div>
      <ul class="card-facts">
        <li>默认自由现金流对沪深300，主图显示相对净值 Alpha 曲线</li>
        <li>多个宽基自动形成季度再平衡等权组合，表格保留逐一比较</li>
        <li>同步保留牛熊周期背景、区间放大和十字线观察</li>
      </ul>
      <div class="card-actions">
        <a class="button primary" href="__ALPHA_HREF__">打开研究</a>
        <a class="button" href="__MAINLINE_HREF__">资产配置研究</a>
      </div>
    </article>

    <article class="strategy-card">
      <div class="card-head">
        <h2>策略组合研究</h2>
        <span class="status">新研究</span>
      </div>
      <p class="card-desc">用四个策略资产构建可复现组合，比较权重模型与再平衡频率如何改变长期净值和回撤。</p>
      <div class="tag-row">
        <span class="tag">等权</span>
        <span class="tag">逆波动</span>
        <span class="tag">风险平价 ERC</span>
        <span class="tag">季度/年度再平衡</span>
      </div>
      <ul class="card-facts">
        <li>风险平价使用完整协方差矩阵，目标为各策略等风险贡献</li>
        <li>支持同时叠加不同权重模型和再平衡方式</li>
        <li>表格显示年化、波动、回撤、夏普、Calmar、换手和当前权重</li>
      </ul>
      <div class="card-actions">
        <a class="button primary" href="__STRATEGY_PORTFOLIO_HREF__">打开研究</a>
        <a class="button" href="__ALPHA_HREF__">资产 Alpha 研究</a>
      </div>
    </article>
  </section>

  <h2 class="section-title">资料入口</h2>
  <section class="resources" aria-label="资料入口">
    <a class="resource-link" href="__DAILY_HREF__">日线 CSV <span>收盘/高低/拐点标记</span></a>
    <a class="resource-link" href="__RECORDS_HREF__">拐点 CSV <span>高低拐点记录</span></a>
    <a class="resource-link" href="__LEGACY_HREF__">旧路径兼容页 <span>仍可访问</span></a>
  </section>
</main>
<div data-myinvest-footer></div>
<script src="https://invest.okbbc.com/footer.js" charset="utf-8" defer></script>
</body>
</html>
"""
    replacements = {
        "__LOG_HREF__": f"/{log_html_path.name}",
        "__ZIGZAG_HREF__": f"/{zigzag_html_path.name}",
        "__MAINLINE_HREF__": f"/{mainline_html_path.name}",
        "__ALPHA_HREF__": f"/{alpha_html_path.name}",
        "__STRATEGY_PORTFOLIO_HREF__": f"/{strategy_portfolio_html_path.name}",
        "__DAILY_HREF__": f"/{daily_csv_path.name}",
        "__RECORDS_HREF__": f"/{records_csv_path.name}",
        "__LEGACY_HREF__": f"/{legacy_html_path.name}",
        "__CODE__": series.code,
        "__DATE_RANGE__": data_range,
        "__LATEST_CLOSE__": latest_close,
        "__PIVOT_COUNT__": str(len(records)),
        "__HIGH_COUNT__": str(high_count),
        "__LOW_COUNT__": str(low_count),
    }
    html = html_template
    for key, value in replacements.items():
        html = html.replace(key, value)
    output_path.write_text(html, encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="生成 480092.CNI 研究入口和研究页。")
    parser.add_argument("--env-file", default=".env", help="可选环境文件。默认 .env。")
    parser.add_argument("--output-dir", default="output", help="输出目录。默认 output。")
    parser.add_argument("--code", default=DEFAULT_CODE, help="指数代码。默认 480092.CNI。")
    parser.add_argument("--start-date", default=DEFAULT_START_DATE, help="开始日期，格式 YYYYMMDD。默认 20160101。")
    parser.add_argument("--end-date", default=TODAY, help="结束日期，格式 YYYYMMDD。")
    parser.add_argument(
        "--turning-reversal",
        type=float,
        default=DEFAULT_TURNING_REVERSAL,
        help="确认拐点所需的反向涨跌幅，0.15 表示 15%%。默认 0.15。",
    )
    parser.add_argument(
        "--y-scale",
        choices=("linear", "percent", "log"),
        default=DEFAULT_Y_SCALE,
        help="Y 轴显示模式：linear 为点位，percent 为相对起点累计涨幅，log 为对数轴。默认 log。",
    )
    parser.add_argument("--no-open", action="store_true", help="生成后不自动打开 HTML。")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    load_env_file(Path(args.env_file))

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    series = fetch_index_series(args.code, args.start_date, args.end_date, args.turning_reversal)
    series.data, records = add_turning_point_flags(series.data, args.turning_reversal)

    daily_csv_path = output_dir / f"{series.code.replace('.', '_')}_daily.csv"
    records_csv_path = output_dir / f"{series.code.replace('.', '_')}_record_points.csv"
    index_html_path = output_dir / "index.html"
    html_path = output_dir / f"{series.code.replace('.', '_')}_new_high_low.html"
    zigzag_html_path = output_dir / f"{series.code.replace('.', '_')}_zigzag_strategy.html"
    mainline_html_path = output_dir / f"{series.code.replace('.', '_')}_mainline_background.html"
    alpha_html_path = output_dir / f"{series.code.replace('.', '_')}_alpha.html"
    strategy_portfolio_html_path = output_dir / f"{series.code.replace('.', '_')}_strategy_portfolio.html"
    legacy_html_path = output_dir / "a_share_free_cash_flow_total_return.html"
    legacy_csv_path = output_dir / "a_share_free_cash_flow_total_return.csv"

    write_daily_csv(series, daily_csv_path)
    write_daily_csv(series, legacy_csv_path)
    write_record_csv(records, records_csv_path)
    write_log_regression_html(series, records, html_path, args.y_scale, args.turning_reversal)
    write_html(series, records, zigzag_html_path, args.y_scale, args.turning_reversal)
    mainline_payload = build_mainline_payload(series)
    write_mainline_background_html(series, mainline_html_path, mainline_payload)
    write_alpha_html(series, alpha_html_path, mainline_payload)
    write_strategy_portfolio_html(series, strategy_portfolio_html_path, mainline_payload)
    write_log_regression_html(series, records, legacy_html_path, args.y_scale, args.turning_reversal)
    write_research_index_html(
        series,
        records,
        index_html_path,
        html_path,
        zigzag_html_path,
        mainline_html_path,
        alpha_html_path,
        strategy_portfolio_html_path,
        daily_csv_path,
        records_csv_path,
        legacy_html_path,
    )

    first = series.data.iloc[0]
    last = series.data.iloc[-1]
    high_count = int(series.data["turning_high"].sum())
    low_count = int(series.data["turning_low"].sum())
    print(f"已生成 {series.code} Log 回归通道研究页：")
    print(f"- 数据范围：{first['trade_date']} 至 {last['trade_date']}，共 {len(series.data)} 条")
    print(f"- 最新收盘：{last['close']:.4f}")
    print("- 默认回看年数：2年")
    print("- 默认通道宽度：2.75σ")
    print(f"- 附带拐点 CSV：{len(records)} 个；高点：{high_count} 个；低点：{low_count} 个")
    print(f"网页入口：{index_html_path.resolve()}")
    print(f"Log 回归通道页：{html_path.resolve()}")
    print(f"ZigZag 拐点策略页：{zigzag_html_path.resolve()}")
    print(f"资产配置研究页：{mainline_html_path.resolve()}")
    print(f"资产 Alpha 研究页：{alpha_html_path.resolve()}")
    print(f"策略组合研究页：{strategy_portfolio_html_path.resolve()}")
    print(f"当前浏览器旧路径也已覆盖：{legacy_html_path.resolve()}")
    print(f"日线 CSV：{daily_csv_path.resolve()}")
    print(f"拐点 CSV：{records_csv_path.resolve()}")

    if not args.no_open:
        webbrowser.open(index_html_path.resolve().as_uri())
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        raise SystemExit(1)
