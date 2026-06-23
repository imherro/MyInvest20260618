from __future__ import annotations

import argparse
import concurrent.futures
import copy
import json
import mimetypes
import os
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
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8888
PUBLIC_HOME_URL = "https://invest.okbbc.com/"
REQUEST_TIMEOUT_SECONDS = 12
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
CACHE_TTL_SECONDS = 10 * 60
STATIC_CACHE_SECONDS = 60
_SOURCE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_SOURCE_CACHE_LOCK = threading.Lock()

SOURCES: "OrderedDict[str, dict[str, str]]" = OrderedDict(
    [
        (
            "market",
            {
                "label": "市场",
                "subtitle": "A股市场评分",
                "home_url": "https://market.okbbc.com/",
                "api_url": "https://market.okbbc.com/api/index",
                "accent": "market",
            },
        ),
        (
            "theme",
            {
                "label": "主线",
                "subtitle": "主题主线排名",
                "home_url": "https://theme.okbbc.com/",
                "api_url": "https://theme.okbbc.com/api/index",
                "accent": "theme",
            },
        ),
        (
            "shadow",
            {
                "label": "影子",
                "subtitle": "影子观察",
                "home_url": "https://shadow.okbbc.com/",
                "api_url": "https://shadow.okbbc.com/api/index",
                "accent": "shadow",
            },
        ),
        (
            "position",
            {
                "label": "操作",
                "subtitle": "仓位与执行",
                "home_url": "https://position.okbbc.com/",
                "api_url": "https://position.okbbc.com/api/index",
                "accent": "position",
            },
        ),
        (
            "leader",
            {
                "label": "龙头",
                "subtitle": "龙头研究",
                "home_url": "https://leader.okbbc.com/",
                "api_url": "https://leader.okbbc.com/api/index",
                "accent": "leader",
            },
        ),
    ]
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def utc_iso_from_epoch(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat(timespec="seconds")


def china_now_iso() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


def source_config(source_id: str, source: dict[str, str]) -> dict[str, str]:
    return {
        "id": source_id,
        "label": source["label"],
        "subtitle": source["subtitle"],
        "home_url": source["home_url"],
        "api_url": source["api_url"],
        "accent": source["accent"],
    }


def public_sources() -> list[dict[str, str]]:
    return [source_config(source_id, source) for source_id, source in SOURCES.items()]


def footer_links() -> list[dict[str, str]]:
    return [
        {
            "id": "invest",
            "label": "本系统",
            "title": "MyInvest 总览",
            "url": PUBLIC_HOME_URL,
        },
        *[
            {
                "id": source_id,
                "label": source["label"],
                "title": source["subtitle"],
                "url": source["home_url"],
            }
            for source_id, source in SOURCES.items()
        ],
    ]


def decode_response(body: bytes, content_type: str) -> Any:
    charset = "utf-8"
    for part in content_type.split(";"):
        part = part.strip()
        if part.lower().startswith("charset="):
            charset = part.split("=", 1)[1].strip() or charset
            break

    text = body.decode(charset, errors="replace")
    if "json" in content_type.lower() or text.lstrip().startswith(("{", "[")):
        return json.loads(text)
    return {"text": text}


def fetch_source(source_id: str) -> dict[str, Any]:
    if source_id not in SOURCES:
        raise KeyError(source_id)

    source = SOURCES[source_id]
    request = Request(
        source["api_url"],
        headers={
            "Accept": "application/json, text/plain;q=0.8, */*;q=0.5",
            "User-Agent": "MyInvest20260618-WebHub/1.0",
        },
    )
    started_at = utc_now_iso()

    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
            truncated = len(body) > MAX_RESPONSE_BYTES
            body = body[:MAX_RESPONSE_BYTES]
            content_type = response.headers.get("content-type", "")
            data = decode_response(body, content_type)
            return {
                **source_config(source_id, source),
                "ok": True,
                "status": response.status,
                "content_type": content_type,
                "fetched_at": utc_now_iso(),
                "started_at": started_at,
                "truncated": truncated,
                "data": data,
            }
    except HTTPError as exc:
        body = exc.read(4096)
        detail = body.decode("utf-8", errors="replace").strip()
        return {
            **source_config(source_id, source),
            "ok": False,
            "status": exc.code,
            "fetched_at": utc_now_iso(),
            "started_at": started_at,
            "error": exc.reason or "HTTP error",
            "detail": detail,
        }
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {
            **source_config(source_id, source),
            "ok": False,
            "status": None,
            "fetched_at": utc_now_iso(),
            "started_at": started_at,
            "error": exc.__class__.__name__,
            "detail": str(exc),
        }


def extract_shanghai_index(market_source: dict[str, Any]) -> dict[str, Any]:
    data = market_source.get("data") or {}
    summary = data.get("summary") or {}
    data_quality = summary.get("data_quality") or {}
    cross_validation = data_quality.get("cross_validation") or {}
    baostock_indices = cross_validation.get("baostock_indices") or {}
    shanghai = baostock_indices.get("000001.SH") or {}
    value = shanghai.get("tushare_close") or shanghai.get("baostock_close")
    return {
        "name": "上证指数",
        "code": "000001.SH",
        "value": value,
        "display": f"{value:.2f}" if isinstance(value, (int, float)) else "--",
        "as_of": summary.get("basis_trade_date") or data_quality.get("generated_at"),
        "source": SOURCES["market"]["api_url"],
        "available": value is not None,
    }


def clear_source_cache(source_id: str | None = None) -> None:
    with _SOURCE_CACHE_LOCK:
        if source_id is None:
            _SOURCE_CACHE.clear()
        else:
            _SOURCE_CACHE.pop(source_id, None)


def add_cache_metadata(
    payload: dict[str, Any],
    *,
    hit: bool,
    stored_at: float,
    now: float,
) -> dict[str, Any]:
    result = copy.deepcopy(payload)
    ttl_remaining = max(0, int(round(CACHE_TTL_SECONDS - (now - stored_at))))
    result["cache"] = {
        "hit": hit,
        "ttl_seconds": CACHE_TTL_SECONDS,
        "ttl_remaining_seconds": ttl_remaining,
        "cached_at": utc_iso_from_epoch(stored_at),
        "expires_at": utc_iso_from_epoch(stored_at + CACHE_TTL_SECONDS),
    }
    return result


def fetch_source_cached(
    source_id: str,
    *,
    force_refresh: bool = False,
    fetcher: Callable[[str], dict[str, Any]] = fetch_source,
    now: float | None = None,
) -> dict[str, Any]:
    checked_at = time.time() if now is None else now
    if force_refresh:
        clear_source_cache(source_id)
    else:
        with _SOURCE_CACHE_LOCK:
            cached = _SOURCE_CACHE.get(source_id)
        if cached is not None:
            stored_at, payload = cached
            if checked_at - stored_at < CACHE_TTL_SECONDS:
                return add_cache_metadata(payload, hit=True, stored_at=stored_at, now=checked_at)

    payload = fetcher(source_id)
    stored_at = time.time() if now is None else now
    with _SOURCE_CACHE_LOCK:
        _SOURCE_CACHE[source_id] = (stored_at, copy.deepcopy(payload))
    return add_cache_metadata(payload, hit=False, stored_at=stored_at, now=stored_at)


def build_all_sources_payload(
    fetcher: Callable[[str], dict[str, Any]] = fetch_source,
    *,
    force_refresh: bool = False,
) -> dict[str, Any]:
    if force_refresh:
        clear_source_cache()

    results: dict[str, dict[str, Any]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(SOURCES)) as executor:
        future_map = {
            executor.submit(
                fetch_source_cached,
                source_id,
                force_refresh=force_refresh,
                fetcher=fetcher,
            ): source_id
            for source_id in SOURCES
        }
        for future in concurrent.futures.as_completed(future_map):
            source_id = future_map[future]
            try:
                results[source_id] = future.result()
            except Exception as exc:  # pragma: no cover - defensive route isolation
                source = SOURCES[source_id]
                results[source_id] = {
                    **source_config(source_id, source),
                    "ok": False,
                    "status": None,
                    "fetched_at": utc_now_iso(),
                    "error": exc.__class__.__name__,
                    "detail": str(exc),
                }

    ordered_results = [results[source_id] for source_id in SOURCES]
    return {
        "ok": all(item.get("ok") for item in ordered_results),
        "generated_at": utc_now_iso(),
        "sources": ordered_results,
    }


def build_single_source_payload(
    source_id: str,
    *,
    force_refresh: bool = False,
    fetcher: Callable[[str], dict[str, Any]] = fetch_source,
) -> tuple[int, dict[str, Any]]:
    if source_id not in SOURCES:
        return (
            HTTPStatus.NOT_FOUND,
            {
                "ok": False,
                "generated_at": utc_now_iso(),
                "error": "Unknown source",
                "source_id": source_id,
                "available_sources": list(SOURCES),
            },
        )
    return (
        HTTPStatus.OK,
        {
            "ok": True,
            "generated_at": utc_now_iso(),
            "source": fetch_source_cached(
                source_id,
                force_refresh=force_refresh,
                fetcher=fetcher,
            ),
        },
    )


def build_footer_payload(
    fetcher: Callable[[str], dict[str, Any]] = fetch_source,
) -> dict[str, Any]:
    generated_at = china_now_iso()
    market_source = fetch_source_cached("market", fetcher=fetcher)
    return {
        "ok": True,
        "generated_at": generated_at,
        "timezone": "Asia/Shanghai",
        "market_index": extract_shanghai_index(market_source),
        "links": footer_links(),
    }


class WebHubHandler(BaseHTTPRequestHandler):
    server_version = "MyInvestWebHub/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        query = parse_qs(parsed.query)
        force_refresh = query.get("refresh", ["0"])[0].lower() in {"1", "true", "yes"}

        if path == "/healthz":
            self.write_json({"ok": True, "generated_at": utc_now_iso()})
            return
        if path == "/api/config":
            self.write_json({"ok": True, "sources": public_sources()})
            return
        if path == "/api/footer":
            self.write_json(build_footer_payload(), cors=True)
            return
        if path == "/api/sources":
            self.write_json(build_all_sources_payload(force_refresh=force_refresh))
            return
        if path.startswith("/api/sources/"):
            source_id = path.rsplit("/", 1)[-1]
            status, payload = build_single_source_payload(
                source_id,
                force_refresh=force_refresh,
            )
            self.write_json(payload, status=status)
            return

        self.serve_static(path)

    def serve_static(self, path: str) -> None:
        if path in {"", "/"}:
            target = WEB_ROOT / "index.html"
        else:
            clean_path = path.lstrip("/")
            target = (WEB_ROOT / clean_path).resolve()
            if not str(target).startswith(str(WEB_ROOT.resolve())):
                self.send_error(HTTPStatus.FORBIDDEN)
                return

        if not target.exists() or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        payload = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", f"private, max-age={STATIC_CACHE_SECONDS}")
        self.end_headers()
        self.wfile.write(payload)

    def write_json(
        self,
        payload: dict[str, Any],
        status: int = HTTPStatus.OK,
        *,
        cors: bool = False,
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if cors:
            self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        print("%s - - [%s] %s" % (self.address_string(), self.log_date_time_string(), format % args))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the MyInvest web hub.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", DEFAULT_PORT)))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), WebHubHandler)
    print(f"MyInvest Web Hub: http://{args.host}:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping MyInvest Web Hub.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
