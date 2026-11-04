from __future__ import annotations

import argparse
import concurrent.futures
import copy
import csv
import json
import mimetypes
import os
import re
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"
ENV_PATH = ROOT / ".env"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8022
REQUEST_TIMEOUT_SECONDS = 6
SOCKET_TIMEOUT_SECONDS = 4
READ_CHUNK_BYTES = 64 * 1024
AGGREGATE_TIMEOUT_SECONDS = REQUEST_TIMEOUT_SECONDS + 2
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
CACHE_TTL_SECONDS = 60
PUBLIC_HOME_URL = "https://intraday.okbbc.com/"
INVEST_API_ROOT = "https://invest.okbbc.com/api"
QMT_DEFAULT_PATH = Path(r"D:\国金证券QMT交易端")
STRATEGY_ROOT = ROOT.parent / "MyInvestStrategyIndex"
STRATEGY_WEIGHTS_PATH = (
    STRATEGY_ROOT
    / "reports"
    / "calmar_optimizer"
    / "calmar_optimization_2026-07-03_153952_weights.csv"
)
EASTMONEY_QUOTE_URL = "https://push2.eastmoney.com/api/qt/ulist.np/get"
EASTMONEY_FIELDS = "f12,f14,f2,f3,f4,f5,f6,f15,f16,f17,f18,f62"

MARKET_WATCH = [
    {"id": "sh000001", "label": "上证", "symbol": "000001.SH", "secid": "1.000001", "group": "market"},
    {"id": "sz399001", "label": "深成", "symbol": "399001.SZ", "secid": "0.399001", "group": "market"},
    {"id": "sz399006", "label": "创业板", "symbol": "399006.SZ", "secid": "0.399006", "group": "market"},
    {"id": "csi300", "label": "沪深300", "symbol": "000300.SH", "secid": "1.000300", "group": "market"},
    {"id": "csi500", "label": "中证500", "symbol": "000905.SH", "secid": "1.000905", "group": "market"},
    {"id": "csi1000", "label": "中证1000", "symbol": "000852.SH", "secid": "1.000852", "group": "market"},
    {"id": "star50", "label": "科创50", "symbol": "000688.SH", "secid": "1.000688", "group": "market"},
    {"id": "sh50", "label": "上证50", "symbol": "000016.SH", "secid": "1.000016", "group": "market"},
]

_SOURCE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_SOURCE_CACHE_LOCK = threading.Lock()

CHANNELS: "OrderedDict[str, dict[str, str]]" = OrderedDict(
    [
        (
            "market",
            {
                "label": "市场",
                "title": "A股市场评分",
                "home_url": "https://market.okbbc.com/",
                "api_url": "https://market.okbbc.com/api",
                "index_api_url": "https://market.okbbc.com/api/index",
                "fetch_url": "https://market.okbbc.com/api/research/latest/market-score",
            },
        ),
        (
            "theme",
            {
                "label": "主线",
                "title": "主题主线排名",
                "home_url": "https://theme.okbbc.com/",
                "api_url": "https://theme.okbbc.com/api",
                "index_api_url": "https://theme.okbbc.com/api/index",
                "fetch_url": "https://theme.okbbc.com/api/health",
            },
        ),
        (
            "leader",
            {
                "label": "龙头",
                "title": "龙头研究",
                "home_url": "https://leader.okbbc.com/",
                "api_url": "https://leader.okbbc.com/api",
                "index_api_url": "https://leader.okbbc.com/api/index",
                "fetch_url": "https://leader.okbbc.com/api/stocks/deep/latest",
            },
        ),
        (
            "shadow",
            {
                "label": "影子",
                "title": "影子观察",
                "home_url": "https://shadow.okbbc.com/",
                "api_url": "https://shadow.okbbc.com/api",
                "index_api_url": "https://shadow.okbbc.com/api/index",
                "fetch_url": "https://shadow.okbbc.com/api/latest",
            },
        ),
        (
            "position",
            {
                "label": "操作",
                "title": "仓位与执行",
                "home_url": "https://position.okbbc.com/",
                "api_url": "https://position.okbbc.com/api",
                "index_api_url": "https://position.okbbc.com/api/index",
            },
        ),
        (
            "stock",
            {
                "label": "个股",
                "title": "个股研究",
                "home_url": "https://stock.okbbc.com/",
                "api_url": "https://stock.okbbc.com/api",
                "index_api_url": "https://stock.okbbc.com/api/index",
            },
        ),
    ]
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def china_now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Shanghai"))


def china_now_iso() -> str:
    return china_now().isoformat(timespec="seconds")


def public_endpoint(path: str) -> str:
    return f"{PUBLIC_HOME_URL.rstrip('/')}{path}"


def read_env_flags(path: Path = ENV_PATH) -> dict[str, bool]:
    flags = {
        "env_file": path.exists(),
        "tushare_token": False,
        "fred_api_key": False,
    }
    if not path.exists():
        return flags

    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        normalized_key = key.strip().upper()
        has_value = bool(value.strip())
        if normalized_key == "TUSHARE_TOKEN":
            flags["tushare_token"] = has_value
        elif normalized_key == "FRED_API_KEY":
            flags["fred_api_key"] = has_value
    return flags


def source_health() -> dict[str, Any]:
    env = read_env_flags()
    return {
        "generated_at": china_now_iso(),
        "policy": "local-read-only",
        "data_sources": [
            {
                "id": "qmt",
                "label": "QMT",
                "role": "盘中价格和真实持仓只读导入",
                "available": QMT_DEFAULT_PATH.exists(),
                "status": "ready" if QMT_DEFAULT_PATH.exists() else "not_detected",
                "path_hint": str(QMT_DEFAULT_PATH),
            },
            {
                "id": "tushare",
                "label": "Tushare",
                "role": "A股结构化主源",
                "available": env["tushare_token"],
                "status": "configured" if env["tushare_token"] else "missing_token",
            },
            {
                "id": "baostock",
                "label": "BaoStock",
                "role": "A股交叉验证和备用数据源",
                "available": True,
                "status": "tokenless_source",
            },
            {
                "id": "fred",
                "label": "FRED",
                "role": "宏观补充证据",
                "available": env["fred_api_key"],
                "status": "configured" if env["fred_api_key"] else "missing_key",
            },
            {
                "id": "yfinance",
                "label": "yfinance",
                "role": "海外市场补充",
                "available": True,
                "status": "network_source",
            },
            {
                "id": "web",
                "label": "网络数据",
                "role": "外部子系统和补充信息",
                "available": True,
                "status": "network_source",
            },
        ],
    }


def market_clock(now: datetime | None = None) -> dict[str, str | bool]:
    current = now or china_now()
    weekday = current.weekday()
    minute_of_day = current.hour * 60 + current.minute
    if weekday >= 5:
        session = "closed"
        label = "休市"
        detail = "周末"
        live = False
    elif 9 * 60 + 15 <= minute_of_day < 9 * 60 + 30:
        session = "preopen"
        label = "集合竞价"
        detail = "盘前撮合"
        live = True
    elif 9 * 60 + 30 <= minute_of_day < 11 * 60 + 30:
        session = "morning"
        label = "早盘"
        detail = "连续竞价"
        live = True
    elif 11 * 60 + 30 <= minute_of_day < 13 * 60:
        session = "lunch"
        label = "午间"
        detail = "午休"
        live = False
    elif 13 * 60 <= minute_of_day < 15 * 60:
        session = "afternoon"
        label = "午盘"
        detail = "连续竞价"
        live = True
    elif 15 * 60 <= minute_of_day < 20 * 60:
        session = "post_close"
        label = "盘后"
        detail = "等待收盘数据"
        live = False
    else:
        session = "closed"
        label = "休市"
        detail = "非交易时段"
        live = False
    return {
        "session": session,
        "label": label,
        "detail": detail,
        "is_live": live,
        "now": current.isoformat(timespec="seconds"),
        "timezone": "Asia/Shanghai",
    }


def fetch_json(url: str) -> dict[str, Any]:
    deadline = time.monotonic() + REQUEST_TIMEOUT_SECONDS
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "MyInvestIntraday/1.0",
        },
    )
    with urlopen(request, timeout=SOCKET_TIMEOUT_SECONDS) as response:
        content_type = response.headers.get("content-type", "")
        chunks = []
        total = 0
        while True:
            if time.monotonic() > deadline:
                raise TimeoutError("response_deadline_exceeded")
            chunk = response.read(READ_CHUNK_BYTES)
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_RESPONSE_BYTES:
                raise ValueError("response_too_large")
        body = b"".join(chunks)
        if len(body) > MAX_RESPONSE_BYTES:
            raise ValueError("response_too_large")
        if "json" not in content_type.lower():
            raise ValueError(f"unexpected_content_type:{content_type}")
    payload = json.loads(body.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("expected_json_object")
    return payload


def symbol_to_secid(symbol: str) -> str | None:
    normalized = symbol.strip().upper()
    if normalized.endswith(".SH"):
        return f"1.{normalized[:-3]}"
    if normalized.endswith(".SZ"):
        return f"0.{normalized[:-3]}"
    return None


def secid_to_symbol(secid: str) -> str:
    market, code = secid.split(".", 1)
    return f"{code}.{'SH' if market == '1' else 'SZ'}"


def normalize_quote(raw: dict[str, Any], secid: str, label: str | None = None, group: str = "watch") -> dict[str, Any]:
    symbol = secid_to_symbol(secid)
    return {
        "symbol": symbol,
        "code": str(raw.get("f12") or symbol.split(".")[0]),
        "name": str(raw.get("f14") or label or symbol),
        "label": label or str(raw.get("f14") or symbol),
        "group": group,
        "price": raw.get("f2"),
        "pct_chg": raw.get("f3"),
        "change": raw.get("f4"),
        "volume": raw.get("f5"),
        "amount": raw.get("f6"),
        "high": raw.get("f15"),
        "low": raw.get("f16"),
        "open": raw.get("f17"),
        "prev_close": raw.get("f18"),
        "main_net_inflow": raw.get("f62"),
    }


def fetch_live_quotes(targets: list[dict[str, str]]) -> dict[str, Any]:
    unique_targets: OrderedDict[str, dict[str, str]] = OrderedDict()
    for target in targets:
        secid = target.get("secid")
        if secid:
            unique_targets.setdefault(secid, target)
    if not unique_targets:
        return {"ok": True, "source": "eastmoney", "quotes": [], "generated_at": china_now_iso()}
    url = (
        f"{EASTMONEY_QUOTE_URL}?fltt=2&invt=2&fields={EASTMONEY_FIELDS}"
        f"&secids={','.join(unique_targets.keys())}"
    )
    try:
        payload = fetch_json(url)
        rows = payload.get("data", {}).get("diff", [])
        quotes = []
        for raw in rows if isinstance(rows, list) else []:
            if not isinstance(raw, dict):
                continue
            code = str(raw.get("f12") or "")
            matched = next(
                (
                    (secid, target)
                    for secid, target in unique_targets.items()
                    if secid.endswith(f".{code}")
                ),
                None,
            )
            if matched is None:
                continue
            secid, target = matched
            quotes.append(normalize_quote(raw, secid, target.get("label"), target.get("group", "watch")))
        return {"ok": True, "source": "eastmoney", "quotes": quotes, "generated_at": china_now_iso()}
    except Exception as exc:
        return {"ok": False, "source": "eastmoney", "quotes": [], "generated_at": china_now_iso(), "error": str(exc)}


def fetch_position_payload() -> dict[str, Any] | None:
    try:
        return fetch_json(CHANNELS["position"]["index_api_url"])
    except Exception:
        return None


def top_position_items(position_payload: dict[str, Any] | None, limit: int = 12) -> list[dict[str, Any]]:
    if not isinstance(position_payload, dict):
        return []
    container = position_payload.get("real_top_positions")
    if isinstance(container, dict) and isinstance(container.get("items"), list):
        return [item for item in container["items"][:limit] if isinstance(item, dict)]
    return []


def position_actions(position_payload: dict[str, Any] | None, limit: int = 5) -> list[dict[str, Any]]:
    if not isinstance(position_payload, dict) or not isinstance(position_payload.get("actions"), list):
        return []
    return [item for item in position_payload["actions"][:limit] if isinstance(item, dict)]


def position_recommendations(position_payload: dict[str, Any] | None, limit: int = 4) -> list[str]:
    if not isinstance(position_payload, dict) or not isinstance(position_payload.get("recommendations"), list):
        return []
    return [str(item) for item in position_payload["recommendations"][:limit]]


def build_position_monitor(position_payload: dict[str, Any] | None, quote_by_symbol: dict[str, dict[str, Any]]) -> dict[str, Any]:
    holdings = []
    for item in top_position_items(position_payload):
        symbol = str(item.get("code") or "").upper()
        quote = quote_by_symbol.get(symbol)
        holdings.append(
            {
                "symbol": symbol,
                "name": item.get("name") or symbol,
                "weight_pct": item.get("weight_pct"),
                "quote": quote,
                "status": holding_status(quote),
            }
        )
    actions = position_actions(position_payload)
    return {
        "ok": isinstance(position_payload, dict),
        "basis_date": value_at(position_payload or {}, "page.basis_date"),
        "primary_signal": value_at(position_payload or {}, "page.primary_signal"),
        "market_state": value_at(position_payload or {}, "market_state.label"),
        "holdings": holdings,
        "actions": actions,
        "recommendations": position_recommendations(position_payload),
    }


def holding_status(quote: dict[str, Any] | None) -> str:
    pct = quote.get("pct_chg") if isinstance(quote, dict) else None
    if isinstance(pct, (int, float)):
        if pct <= -2:
            return "pressure"
        if pct >= 2:
            return "strong"
    return "normal"


def read_strategy_weights(path: Path = STRATEGY_WEIGHTS_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    weights = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            code = row.get("code", "")
            weights.append(
                {
                    "code": code,
                    "name": row.get("name") or code,
                    "full_sample_opt_weight": ratio_percent(row.get("full_sample_opt_weight")),
                    "train_70pct_opt_weight": ratio_percent(row.get("train_70pct_opt_weight")),
                    "equal_weight": ratio_percent(row.get("equal_weight")),
                    "tradable": code.endswith(".SH") or code.endswith(".SZ"),
                }
            )
    return weights


def ratio_percent(value: str | None) -> float | None:
    try:
        return round(float(value or 0) * 100, 2)
    except ValueError:
        return None


def build_strategy_anchor(
    quote_by_symbol: dict[str, dict[str, Any]],
    weights: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    weights = weights or read_strategy_weights()
    for item in weights:
        item["quote"] = quote_by_symbol.get(str(item["code"]).upper())
    return {
        "ok": bool(weights),
        "source_file": str(STRATEGY_WEIGHTS_PATH),
        "weights": weights,
        "notes": [
            "策略权重是长期锚点，不是盘中交易指令。",
            "CNI/CSI 全收益指数没有盘中交易报价，仅展示权重。",
        ],
    }


def build_intraday_alerts(
    base_alerts: list[dict[str, str]],
    position_monitor: dict[str, Any],
    live_quotes: dict[str, Any],
) -> list[dict[str, str]]:
    alerts: list[dict[str, str]] = []
    for action in position_monitor.get("actions", [])[:2]:
        reason = str(action.get("reason") or action.get("constraint_reason") or "")
        target_delta = action.get("target_delta")
        alerts.append(
            {
                "level": "warn" if action.get("risk_level") == "high" else "ok",
                "title": f"{action.get('action', 'ACTION')} · {action.get('symbol', '')}",
                "message": f"目标偏移 {fmt_ratio_point(target_delta)}。{reason}".strip(),
            }
        )
    pressure = [
        item
        for item in position_monitor.get("holdings", [])
        if item.get("status") == "pressure" and isinstance(item.get("quote"), dict)
    ]
    for item in pressure[:3]:
        quote = item["quote"]
        alerts.append(
            {
                "level": "error",
                "title": f"{item.get('name')} 盘中承压",
                "message": f"持仓占比 {fmt_ratio_point(item.get('weight_pct'))}，涨跌幅 {fmt_ratio_point(quote.get('pct_chg'))}。",
            }
        )
    if not live_quotes.get("ok"):
        alerts.append(
            {
                "level": "error",
                "title": "实时行情读取失败",
                "message": str(live_quotes.get("error") or "东方财富行情接口不可用"),
            }
        )
    if not alerts:
        alerts.extend(base_alerts)
    return alerts[:6]


def fmt_ratio_point(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.2f}%"
    return "--"


def fetch_board_page(kind: str, direction: str) -> list[dict[str, Any]]:
    fs = "m:90+t:2" if kind == "industry" else "m:90+t:3"
    po = "1" if direction == "top" else "0"
    url = (
        "https://push2.eastmoney.com/api/qt/clist/get"
        "?pn=1&pz=24&np=1&fltt=2&invt=2&fid=f3"
        f"&po={po}&fs={fs}&fields=f12,f14,f2,f3,f4,f5,f6,f62"
    )
    payload = fetch_json(url)
    rows = payload.get("data", {}).get("diff", [])
    result = []
    for raw in rows if isinstance(rows, list) else []:
        if not isinstance(raw, dict):
            continue
        result.append(
            {
                "code": raw.get("f12"),
                "name": raw.get("f14"),
                "price": raw.get("f2"),
                "pct_chg": raw.get("f3"),
                "change": raw.get("f4"),
                "amount": raw.get("f6"),
                "main_net_inflow": raw.get("f62"),
                "kind": kind,
                "direction": direction,
            }
        )
    return result


def fetch_industry_boards() -> dict[str, Any]:
    specs = [
        ("industry", "top"),
        ("industry", "bottom"),
        ("concept", "top"),
        ("concept", "bottom"),
    ]
    data: dict[str, list[dict[str, Any]]] = {}
    errors: dict[str, str] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        future_map = {executor.submit(fetch_board_page, kind, direction): (kind, direction) for kind, direction in specs}
        for future in concurrent.futures.as_completed(future_map):
            kind, direction = future_map[future]
            key = f"{kind}_{direction}"
            try:
                data[key] = future.result()
            except Exception as exc:
                data[key] = []
                errors[key] = str(exc)
    return {
        "ok": not errors,
        "generated_at": china_now_iso(),
        "groups": data,
        "errors": errors,
    }


def build_predictions(
    channels: list[dict[str, Any]],
    live_quotes: dict[str, Any],
    boards: dict[str, Any],
    strategy_anchor: dict[str, Any],
    position_monitor: dict[str, Any],
) -> dict[str, Any]:
    return {
        "market": build_market_prediction(channels, live_quotes),
        "industries": build_industry_predictions(boards),
        "strategies": build_strategy_predictions(strategy_anchor, live_quotes, channels),
        "focus_assets": build_focus_assets(position_monitor, boards, strategy_anchor),
    }


def build_market_prediction(channels: list[dict[str, Any]], live_quotes: dict[str, Any]) -> dict[str, Any]:
    market_channel = next((channel for channel in channels if channel.get("id") == "market"), {})
    metrics = market_channel.get("metrics", [])
    market_score = metric_value(metrics, "市场分")
    regime = metric_value(metrics, "市场状态") or "未知"
    position_range = metric_value(metrics, "权益区间") or "--"
    market_quotes = [quote for quote in live_quotes.get("quotes", []) if quote.get("group") == "market"]
    pct_values = [quote.get("pct_chg") for quote in market_quotes if isinstance(quote.get("pct_chg"), (int, float))]
    positive_count = sum(1 for value in pct_values if value > 0)
    avg_pct = round(sum(pct_values) / len(pct_values), 2) if pct_values else None
    breadth = positive_count / len(pct_values) if pct_values else 0

    if isinstance(market_score, (int, float)) and market_score < 30:
        if avg_pct is not None and avg_pct > 0.35:
            direction = "弱修复震荡"
            probability = 58
            stance = "反弹先按修复看，追涨需要等待宽度继续扩散。"
        else:
            direction = "弱势延续"
            probability = 64
            stance = "仓位约束仍偏防守，反抽不等于趋势反转。"
    elif avg_pct is not None and avg_pct > 0.7 and breadth >= 0.65:
        direction = "修复延续"
        probability = 61
        stance = "指数和宽度共振，盘中回落不破开盘区间前偏多观察。"
    elif avg_pct is not None and avg_pct < -0.5 and breadth <= 0.35:
        direction = "承压回落"
        probability = 62
        stance = "指数和宽度同时走弱，优先保护风险预算。"
    else:
        direction = "震荡分化"
        probability = 55
        stance = "没有单边确认，重点看强行业能否扩散。"

    return {
        "direction": direction,
        "probability": probability,
        "regime": regime,
        "position_range": position_range,
        "market_score": market_score,
        "avg_index_pct": avg_pct,
        "positive_index_count": positive_count,
        "index_count": len(pct_values),
        "stance": stance,
        "evidence": [
            f"收盘模型状态：{regime}，权益区间 {position_range}",
            f"实时指数：{positive_count}/{len(pct_values)} 个上涨，平均涨跌幅 {fmt_ratio_point(avg_pct)}",
        ],
    }


def build_industry_predictions(boards: dict[str, Any]) -> dict[str, Any]:
    top = boards.get("groups", {}).get("industry_top", [])[:8]
    bottom = boards.get("groups", {}).get("industry_bottom", [])[:6]
    concepts = boards.get("groups", {}).get("concept_top", [])[:8]
    leaders = []
    for board in top:
        pct = board.get("pct_chg")
        inflow = board.get("main_net_inflow")
        if isinstance(pct, (int, float)) and pct >= 5:
            outlook = "高强度延续，但午后分歧概率上升"
            probability = 60
        elif isinstance(inflow, (int, float)) and inflow > 0:
            outlook = "强势延续"
            probability = 63
        else:
            outlook = "冲高震荡"
            probability = 56
        leaders.append({**board, "outlook": outlook, "probability": probability})
    laggards = []
    for board in bottom:
        pct = board.get("pct_chg")
        if isinstance(pct, (int, float)) and pct <= -5:
            outlook = "弱势延续，反抽先看修复"
            probability = 64
        else:
            outlook = "承压震荡"
            probability = 58
        laggards.append({**board, "outlook": outlook, "probability": probability})
    hot_concepts = [
        {
            **board,
            "outlook": "题材热度活跃，适合观察扩散和回落承接",
            "probability": 60 if isinstance(board.get("pct_chg"), (int, float)) and board["pct_chg"] >= 4 else 55,
        }
        for board in concepts
    ]
    return {
        "leaders": leaders,
        "laggards": laggards,
        "hot_concepts": hot_concepts,
        "source_ok": boards.get("ok"),
    }


def build_strategy_predictions(
    strategy_anchor: dict[str, Any],
    live_quotes: dict[str, Any],
    channels: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    market_prediction = build_market_prediction(channels, live_quotes)
    strategies = []
    for item in strategy_anchor.get("weights", []):
        code = str(item.get("code") or "")
        quote = item.get("quote")
        pct = quote.get("pct_chg") if isinstance(quote, dict) else None
        weight = item.get("full_sample_opt_weight")
        if "黄金" in str(item.get("name")):
            outlook = "避险/趋势锚仍需重点盯"
            probability = 62 if isinstance(pct, (int, float)) and pct > 0 else 54
        elif "国债" in str(item.get("name")):
            outlook = "防御锚优先级高"
            probability = 64 if market_prediction["direction"] in {"弱势延续", "承压回落"} else 56
        elif item.get("tradable"):
            outlook = "跟随权益修复，确认度取决于宽基能否扩散"
            probability = 58 if market_prediction["direction"] in {"修复延续", "弱修复震荡"} else 50
        else:
            outlook = "日内无直接报价，按相关行业和收盘模型观察"
            probability = 52
        strategies.append(
            {
                "code": code,
                "name": item.get("name"),
                "weight": weight,
                "quote": quote,
                "outlook": outlook,
                "probability": probability,
            }
        )
    return strategies


def build_focus_assets(
    position_monitor: dict[str, Any],
    boards: dict[str, Any],
    strategy_anchor: dict[str, Any],
) -> list[dict[str, Any]]:
    focus: list[dict[str, Any]] = []
    for item in position_monitor.get("holdings", []):
        quote = item.get("quote")
        pct = quote.get("pct_chg") if isinstance(quote, dict) else None
        weight = item.get("weight_pct")
        if (isinstance(weight, (int, float)) and weight >= 3) or (
            isinstance(pct, (int, float)) and abs(pct) >= 1.2
        ):
            focus.append(
                {
                    "type": "持仓",
                    "name": item.get("name"),
                    "symbol": item.get("symbol"),
                    "priority": focus_priority(weight, pct),
                    "reason": f"持仓占比 {fmt_ratio_point(weight)}，盘中涨跌 {fmt_ratio_point(pct)}",
                }
            )
    for board in boards.get("groups", {}).get("industry_top", [])[:5]:
        focus.append(
            {
                "type": "行业",
                "name": board.get("name"),
                "symbol": board.get("code"),
                "priority": focus_priority(None, board.get("pct_chg")),
                "reason": f"行业涨幅 {fmt_ratio_point(board.get('pct_chg'))}，主力净流 {format_money(board.get('main_net_inflow'))}",
            }
        )
    for item in strategy_anchor.get("weights", []):
        weight = item.get("full_sample_opt_weight")
        if item.get("tradable") and isinstance(weight, (int, float)) and weight >= 20:
            quote = item.get("quote")
            pct = quote.get("pct_chg") if isinstance(quote, dict) else None
            focus.append(
                {
                    "type": "策略锚",
                    "name": item.get("name"),
                    "symbol": item.get("code"),
                    "priority": focus_priority(weight, pct),
                    "reason": f"策略权重 {fmt_ratio_point(weight)}，盘中涨跌 {fmt_ratio_point(pct)}",
                }
            )
    focus.sort(key=lambda item: item.get("priority", 0), reverse=True)
    return focus[:12]


def metric_value(metrics: Any, label: str) -> Any:
    if not isinstance(metrics, list):
        return None
    for metric in metrics:
        if isinstance(metric, dict) and metric.get("label") == label:
            return metric.get("value")
    return None


def focus_priority(weight: Any, pct: Any) -> float:
    result = 0.0
    if isinstance(weight, (int, float)):
        result += min(60, abs(weight) * 1.5)
    if isinstance(pct, (int, float)):
        result += min(40, abs(pct) * 8)
    return round(result, 2)


def format_money(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "--"
    yi = value / 100000000
    return f"{yi:.2f}亿"


def fetch_channel(channel_id: str) -> dict[str, Any]:
    if channel_id not in CHANNELS:
        raise KeyError(channel_id)
    config = CHANNELS[channel_id]
    try:
        payload = fetch_json(config.get("fetch_url", config["index_api_url"]))
    except HTTPError as exc:
        return source_error(channel_id, exc.code, str(exc))
    except (URLError, TimeoutError, ValueError, json.JSONDecodeError, OSError) as exc:
        return source_error(channel_id, None, str(exc))
    return normalize_channel(channel_id, payload)


def source_error(channel_id: str, status: int | None, message: str) -> dict[str, Any]:
    config = CHANNELS[channel_id]
    return {
        "id": channel_id,
        "label": config["label"],
        "title": config["title"],
        "home_url": config["home_url"],
        "api_url": config["api_url"],
        "index_api_url": config["index_api_url"],
        "ok": False,
        "status": "error",
        "status_code": status,
        "fetched_at": china_now_iso(),
        "metrics": [],
        "items": [],
        "error": message,
    }


def fetch_channel_cached(
    channel_id: str,
    *,
    refresh: bool = False,
    now: float | None = None,
    fetcher: Callable[[str], dict[str, Any]] = fetch_channel,
) -> dict[str, Any]:
    checked_at = now or time.time()
    if not refresh:
        with _SOURCE_CACHE_LOCK:
            cached = _SOURCE_CACHE.get(channel_id)
        if cached is not None:
            stored_at, payload = cached
            if checked_at - stored_at <= CACHE_TTL_SECONDS:
                result = copy.deepcopy(payload)
                result["cache"] = {
                    "hit": True,
                    "ttl_seconds": CACHE_TTL_SECONDS,
                    "ttl_remaining_seconds": max(0, int(CACHE_TTL_SECONDS - (checked_at - stored_at))),
                }
                return result

    payload = fetcher(channel_id)
    with _SOURCE_CACHE_LOCK:
        _SOURCE_CACHE[channel_id] = (checked_at, copy.deepcopy(payload))
    result = copy.deepcopy(payload)
    result["cache"] = {
        "hit": False,
        "ttl_seconds": CACHE_TTL_SECONDS,
        "ttl_remaining_seconds": CACHE_TTL_SECONDS,
    }
    return result


def is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def compact_metrics(source: dict[str, Any], keys: list[tuple[str, str]]) -> list[dict[str, Any]]:
    metrics = []
    for label, key in keys:
        value = value_at(source, key)
        if value not in (None, "", []):
            metrics.append({"label": label, "value": value})
    return metrics


def value_at(source: dict[str, Any], path: str) -> Any:
    current: Any = source
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    if is_scalar(current):
        return current
    return None


def first_list(source: dict[str, Any], paths: list[str]) -> list[Any]:
    for path in paths:
        current: Any = source
        for part in path.split("."):
            if isinstance(current, dict):
                current = current.get(part)
            else:
                current = None
                break
        if isinstance(current, list):
            return current
    return []


def item_label(item: Any) -> str:
    if not isinstance(item, dict):
        return str(item)
    for key in ["label", "name", "theme", "theme_name", "symbol", "code", "title", "action"]:
        value = item.get(key)
        if value not in (None, ""):
            return str(value)
    return "项目"


def item_value(item: Any) -> Any:
    if not isinstance(item, dict):
        return None
    for key in [
        "score_pct",
        "score",
        "target_weight_ratio",
        "drift_ratio",
        "pct_chg",
        "confidence",
        "status",
        "state",
        "tracking_result",
    ]:
        if item.get(key) not in (None, ""):
            return item.get(key)
    return None


def item_note(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    for key in ["summary", "message", "recommendation", "stage", "state", "title", "reason"]:
        value = item.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def compact_items(items: list[Any], limit: int = 6) -> list[dict[str, Any]]:
    result = []
    for item in items[:limit]:
        result.append(
            {
                "label": item_label(item),
                "value": item_value(item),
                "note": item_note(item),
            }
        )
    return result


def normalize_channel(channel_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    config = CHANNELS[channel_id]
    basis_date = basis_date_for(channel_id, payload)
    metrics = metrics_for(channel_id, payload)
    items = items_for(channel_id, payload)
    return {
        "id": channel_id,
        "label": config["label"],
        "title": config["title"],
        "home_url": config["home_url"],
        "api_url": config["api_url"],
        "index_api_url": config["index_api_url"],
        "ok": True,
        "status": "ok",
        "fetched_at": china_now_iso(),
        "basis_date": basis_date,
        "metrics": metrics,
        "items": items,
        "raw_keys": list(payload.keys())[:24],
    }


def basis_date_for(channel_id: str, payload: dict[str, Any]) -> str | None:
    path_map = {
        "market": ["record.basis_trade_date", "summary.basis_trade_date"],
        "theme": ["latest_report.basis_date", "page.basis_date"],
        "leader": ["result.basis_date", "report.basis_date", "page.basis_date"],
        "shadow": ["run.basis_date", "metrics.basis_date"],
        "position": ["page.basis_date"],
        "stock": ["report.basis_date", "page.basis_date"],
    }
    for path in path_map.get(channel_id, []):
        value = value_at(payload, path)
        if value:
            return str(value)[:10]
    if channel_id == "theme":
        report_id = value_at(payload, "latest_report_id")
        if report_id:
            match = re.search(r"\d{4}-\d{2}-\d{2}", str(report_id))
            if match:
                return match.group(0)
    return None


def metrics_for(channel_id: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    metric_paths = {
        "market": [
            ("市场状态", "record.market_regime"),
            ("市场分", "record.market_position_score"),
            ("机会分", "record.market_opportunity_score"),
            ("权益区间", "record.equity_position_range"),
            ("置信度", "record.confidence"),
        ],
        "theme": [
            ("最强主线", "latest_report.top_theme"),
            ("阶段", "latest_report.top_stage"),
            ("评分", "latest_report.top_score"),
            ("基准日", "latest_report.basis_date"),
            ("报告数", "report_count"),
            ("最新报告", "latest_report_id"),
            ("质量", "latest_data_quality_status"),
            ("策略", "latest_policy_provenance_status"),
        ],
        "leader": [
            ("基准日", "result.basis_date"),
            ("报告", "report_id"),
            ("只读", "result.constraints.read_only"),
            ("ResearchFirst", "result.constraints.research_first"),
            ("RatioOnly", "result.constraints.ratio_only_for_shadow"),
            ("候选数", "metrics.item_count"),
            ("置信度", "report.confidence"),
        ],
        "shadow": [
            ("基准日", "run.basis_date"),
            ("状态", "metrics.status"),
            ("组合数", "metrics.item_count"),
            ("风控", "metrics.risk_status"),
        ],
        "position": [
            ("基准日", "page.basis_date"),
            ("状态", "page.status"),
            ("主信号", "page.primary_signal"),
            ("市场状态", "market_state.label"),
        ],
        "stock": [
            ("基准日", "report.basis_date"),
            ("报告", "report.report_id"),
            ("候选数", "key_results.item_count"),
            ("约束", "constraints.status"),
        ],
    }
    return compact_metrics(payload, metric_paths.get(channel_id, []))


def items_for(channel_id: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    if channel_id == "market" and isinstance(payload.get("record"), dict):
        record = payload["record"]
        fields = [
            ("市场分", "market_position_score"),
            ("机会分", "market_opportunity_score"),
            ("风险后分", "risk_adjusted_market_position_score"),
            ("拥挤惩罚", "crowding_penalty"),
            ("风险惩罚", "risk_penalty_score"),
        ]
        return [
            {
                "label": label,
                "value": record.get(key),
                "note": str(record.get("market_regime") or ""),
            }
            for label, key in fields
            if record.get(key) not in (None, "")
        ]
    paths = {
        "market": ["modules.cards", "summary.cards"],
        "theme": ["mainline_ranking", "theme_ranking", "canonical_mainline_summary.items"],
        "leader": ["key_results", "themes", "stock_deep_research"],
        "shadow": ["allocations", "sleeves", "sleeve_summary"],
        "position": ["actions", "recommendations", "decision_set"],
        "stock": ["key_results.items", "key_results", "links"],
    }
    return compact_items(first_list(payload, paths.get(channel_id, [])))


def build_alerts(channels: list[dict[str, Any]], health: dict[str, Any]) -> list[dict[str, str]]:
    alerts: list[dict[str, str]] = []
    for source in health["data_sources"]:
        if source["id"] == "qmt" and not source["available"]:
            alerts.append(
                {
                    "level": "warn",
                    "title": "QMT 未检测到",
                    "message": "当前版本显示为参考模式，盘中价格和真实持仓需要 QMT 在线后接入。",
                }
            )
        if source["id"] == "tushare" and not source["available"]:
            alerts.append(
                {
                    "level": "warn",
                    "title": "Tushare 未配置",
                    "message": "A股结构化主源不可用，后续研究型补全会受限。",
                }
            )
    failed = [channel for channel in channels if not channel.get("ok")]
    for channel in failed[:3]:
        alerts.append(
            {
                "level": "error",
                "title": f"{channel['label']}接口异常",
                "message": str(channel.get("error") or "读取失败"),
            }
        )
    if not alerts:
        alerts.append(
            {
                "level": "ok",
                "title": "只读看盘已就绪",
                "message": "外部子系统可读取，本地 key 仅用于后续数据源采集。",
            }
        )
    return alerts


def build_index_payload(
    *,
    refresh: bool = False,
    fetcher: Callable[[str], dict[str, Any]] = fetch_channel,
) -> dict[str, Any]:
    health = source_health()
    outer_executor = concurrent.futures.ThreadPoolExecutor(max_workers=3)
    channels_future = outer_executor.submit(fetch_channels_for_index, refresh, fetcher)
    position_future = outer_executor.submit(fetch_position_payload)
    boards_future = outer_executor.submit(fetch_industry_boards)
    position_payload = position_future.result(timeout=AGGREGATE_TIMEOUT_SECONDS)
    strategy_weights = read_strategy_weights()
    quote_targets = list(MARKET_WATCH)
    for item in top_position_items(position_payload):
        symbol = str(item.get("code") or "").upper()
        secid = symbol_to_secid(symbol)
        if secid:
            quote_targets.append(
                {
                    "id": symbol.lower(),
                    "label": str(item.get("name") or symbol),
                    "symbol": symbol,
                    "secid": secid,
                    "group": "holding",
                }
            )
    for item in strategy_weights:
        code = str(item.get("code") or "").upper()
        secid = symbol_to_secid(code)
        if secid:
            quote_targets.append(
                {
                    "id": code.lower(),
                    "label": str(item.get("name") or code),
                    "symbol": code,
                    "secid": secid,
                    "group": "strategy",
                }
            )
    live_quotes = fetch_live_quotes(quote_targets)
    channels = channels_future.result(timeout=AGGREGATE_TIMEOUT_SECONDS)
    boards = boards_future.result(timeout=AGGREGATE_TIMEOUT_SECONDS)
    outer_executor.shutdown(wait=False, cancel_futures=True)
    quote_by_symbol = {
        str(quote.get("symbol")).upper(): quote
        for quote in live_quotes.get("quotes", [])
        if quote.get("symbol")
    }
    position_monitor = build_position_monitor(position_payload, quote_by_symbol)
    strategy_anchor = build_strategy_anchor(quote_by_symbol, strategy_weights)
    base_alerts = build_alerts(channels, health)
    predictions = build_predictions(channels, live_quotes, boards, strategy_anchor, position_monitor)
    return {
        "ok": True,
        "schema_version": 1,
        "system": {
            "id": "intraday",
            "name": "MyInvestIntraday",
            "description": "MyInvest20260618 的盘中只读看盘子系统。",
            "home_url": PUBLIC_HOME_URL,
            "api_url": public_endpoint("/api"),
        },
        "page": {
            "title": "日间看盘",
            "subtitle": "盘中观察层",
            "layout": "fullscreen",
            "refresh_seconds": 60,
        },
        "generated_at": china_now_iso(),
        "timezone": "Asia/Shanghai",
        "market_clock": market_clock(),
        "source_health": health,
        "live_quotes": live_quotes,
        "position_monitor": position_monitor,
        "strategy_anchor": strategy_anchor,
        "industry_boards": boards,
        "predictions": predictions,
        "channels": channels,
        "alerts": build_intraday_alerts(base_alerts, position_monitor, live_quotes),
    }


def fetch_channels_for_index(
    refresh: bool,
    fetcher: Callable[[str], dict[str, Any]],
) -> list[dict[str, Any]]:
    channel_ids = list(CHANNELS.keys())
    channels: list[dict[str, Any]] = []
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=min(6, len(channel_ids)))
    futures = {
        executor.submit(fetch_channel_cached, channel_id, refresh=refresh, fetcher=fetcher): channel_id
        for channel_id in channel_ids
    }
    done, pending = concurrent.futures.wait(futures, timeout=AGGREGATE_TIMEOUT_SECONDS)
    for future in done:
        channel_id = futures[future]
        try:
            channels.append(future.result())
        except Exception as exc:  # defensive boundary for API output
            channels.append(source_error(channel_id, None, str(exc)))
    for future in pending:
        channel_id = futures[future]
        future.cancel()
        channels.append(source_error(channel_id, None, "channel_timeout"))
    executor.shutdown(wait=False, cancel_futures=True)
    order = {channel_id: idx for idx, channel_id in enumerate(channel_ids)}
    channels.sort(key=lambda item: order.get(item["id"], 999))
    return channels


def build_api_catalog() -> dict[str, Any]:
    endpoints = [
        {
            "method": "GET",
            "path": "/api",
            "url": public_endpoint("/api"),
            "description": "接口目录。",
        },
        {
            "method": "GET",
            "path": "/api/index",
            "url": public_endpoint("/api/index"),
            "description": "全屏看盘页聚合数据；支持 refresh=1 跳过本地缓存。",
        },
        {
            "method": "GET",
            "path": "/api/config",
            "url": public_endpoint("/api/config"),
            "description": "子系统频道配置。",
        },
        {
            "method": "GET",
            "path": "/api/sources/health",
            "url": public_endpoint("/api/sources/health"),
            "description": "本地数据源配置和可用性，只返回布尔状态，不返回 key。",
        },
    ]
    return {
        "ok": True,
        "system_name": "MyInvestIntraday",
        "version": 1,
        "description": "MyInvest20260618 的盘中只读看盘子系统。",
        "generated_at": china_now_iso(),
        "base_url": PUBLIC_HOME_URL,
        "recommended_entrypoints": [
            {"method": "GET", "path": "/api/index"},
            {"method": "GET", "path": "/api/sources/health"},
        ],
        "safety": {
            "mode": "read_only",
            "trading": "disabled",
            "local_secrets": "redacted",
            "qmt": "read_only_planned",
        },
        "embeds": {
            "header_js": "https://invest.okbbc.com/header.js",
            "footer_js": "https://invest.okbbc.com/footer.js",
        },
        "endpoints": endpoints,
        "total_endpoints": len(endpoints),
    }


def build_config_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "generated_at": china_now_iso(),
        "channels": [
            {
                "id": channel_id,
                **config,
            }
            for channel_id, config in CHANNELS.items()
        ],
        "invest_api_root": INVEST_API_ROOT,
    }


class IntradayHandler(BaseHTTPRequestHandler):
    server_version = "MyInvestIntraday/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        query = parse_qs(parsed.query)

        if path in {"/", "/index.html"}:
            self.write_static(WEB_ROOT / "index.html")
            return
        if path == "/api" or path == "/api/":
            self.write_json(build_api_catalog(), cors=True)
            return
        if path == "/api/index":
            self.write_json(build_index_payload(refresh=query.get("refresh") == ["1"]), cors=True)
            return
        if path == "/api/config":
            self.write_json(build_config_payload(), cors=True)
            return
        if path == "/api/sources/health":
            self.write_json(source_health(), cors=True)
            return

        static_path = (WEB_ROOT / path.lstrip("/")).resolve()
        try:
            static_path.relative_to(WEB_ROOT.resolve())
        except ValueError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if static_path.is_file():
            self.write_static(static_path)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def write_static(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        if path.suffix == ".js":
            content_type = "application/javascript; charset=utf-8"
        elif path.suffix in {".html", ".css"}:
            content_type = f"{content_type}; charset=utf-8"
        payload = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def write_json(self, payload: dict[str, Any], *, cors: bool = False) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if cors:
            self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the MyInvest intraday dashboard.")
    parser.add_argument("--host", default=os.environ.get("MYINVEST_INTRADAY_HOST", DEFAULT_HOST))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("MYINVEST_INTRADAY_PORT", DEFAULT_PORT)),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), IntradayHandler)
    print(f"MyInvestIntraday: http://{args.host}:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
