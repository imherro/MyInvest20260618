from __future__ import annotations

import argparse
import concurrent.futures
import json
import mimetypes
import os
from collections import OrderedDict
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8888
REQUEST_TIMEOUT_SECONDS = 12
MAX_RESPONSE_BYTES = 2 * 1024 * 1024

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
    ]
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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


def build_all_sources_payload(
    fetcher: Callable[[str], dict[str, Any]] = fetch_source,
) -> dict[str, Any]:
    results: dict[str, dict[str, Any]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(SOURCES)) as executor:
        future_map = {
            executor.submit(fetcher, source_id): source_id for source_id in SOURCES
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


def build_single_source_payload(source_id: str) -> tuple[int, dict[str, Any]]:
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
            "source": fetch_source(source_id),
        },
    )


class WebHubHandler(BaseHTTPRequestHandler):
    server_version = "MyInvestWebHub/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        if path == "/healthz":
            self.write_json({"ok": True, "generated_at": utc_now_iso()})
            return
        if path == "/api/config":
            self.write_json({"ok": True, "sources": public_sources()})
            return
        if path == "/api/sources":
            self.write_json(build_all_sources_payload())
            return
        if path.startswith("/api/sources/"):
            source_id = path.rsplit("/", 1)[-1]
            status, payload = build_single_source_payload(source_id)
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
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def write_json(self, payload: dict[str, Any], status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
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
