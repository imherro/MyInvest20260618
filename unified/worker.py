"""Business-module adapters. Workers use private pipes, not listening ports."""
import asyncio
import concurrent.futures
import http.client
import importlib
import io
import os
import multiprocessing
import sys
import threading
import traceback
from pathlib import Path
from types import SimpleNamespace

HANDLERS = {
    "market": ("serve_market_web", "MarketWebHandler"),
    "etf": ("myinvestetf.web", "MyInvestETFHandler"),
    "stock": ("myinveststock.web", "MyInvestStockHandler"),
    "intraday": ("server", "IntradayHandler"),
    "position": ("app.server", "ApiHandler"),
    "strategyindex": ("myinvest_strategy_index.webapp", "StrategyIndexHandler"),
    "short": ("shortterm_trader.webapp", "DashboardHandler"),
    "test": ("serve_web", "ResearchHandler"),
}
ASGI = {"theme": "web.main", "leader": "leader_app.main", "shadow": "shadow_app.main",
        "cycle": "web.app", "picking": "app.main", "ten": "tenbagger.web_app", "taa": "backend.main"}


class MemorySocket:
    def __init__(self, content):
        self.input = io.BytesIO(content)
        self.output = io.BytesIO()

    def makefile(self, mode, *args):
        return self.input

    def sendall(self, content):
        self.output.write(content)

    def settimeout(self, timeout):
        pass


def dispatch_handler(handler, request):
    method, path, headers, body = request
    # HTTP/1.0 plus close prevents handlers waiting for a second request.
    raw = f"{method} {path} HTTP/1.0\r\n".encode("ascii")
    raw += b"".join(f"{key}: {value}\r\n".encode("latin-1") for key, value in headers)
    raw += b"Connection: close\r\n\r\n" + body
    sock = MemorySocket(raw)
    handler(sock, ("127.0.0.1", 0), SimpleNamespace(server_address=("127.0.0.1", 8888)))
    response = http.client.HTTPResponse(MemorySocket(sock.output.getvalue()), method=method)
    response.begin()
    return response.status, response.getheaders(), response.read()


def load_handler(system_id):
    module_name, class_name = HANDLERS[system_id]
    if system_id == "intraday":
        spec = importlib.util.spec_from_file_location("myinvest_intraday_module", Path.cwd() / "server.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    else:
        module = importlib.import_module(module_name)
    handler = getattr(module, class_name)
    if system_id in {"strategyindex", "short"}:
        handler.settings = module.load_settings()
    if system_id in {"etf", "stock"}:
        importlib.import_module(f"myinvest{system_id}.db").init_db()
    return handler


def error_response():
    traceback.print_exc()
    return 500, [("Content-Type", "application/json")], b'{"error":"module_request_failed"}'


async def serve_asgi(connection, system_id):
    import httpx
    module = importlib.import_module(ASGI[system_id])
    app = module.create_app(report_dir=Path.cwd() / "reports") if system_id == "ten" else module.app
    if system_id == "taa":
        from .taa_api import install
        install(app)
    # FastAPI/Starlette's lifecycle includes the application's existing startup jobs.
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://module.internal", follow_redirects=False) as client:
            connection.send(("ready", os.getpid()))
            tasks = set()
            async def handle(request_id, request):
                method, path, headers, body = request
                try:
                    # A fresh request prevents the shared transport client from
                    # carrying one visitor's cookies into another request.
                    outbound = httpx.Request(method, "http://module.internal" + path, headers=headers, content=body)
                    response = await client.send(outbound)
                    # HTTPX has decoded content already; do not decode it twice at the gateway.
                    response_headers = [(k, v) for k, v in response.headers.multi_items() if k.lower() not in {"content-encoding", "content-length"}]
                    result = response.status_code, response_headers, response.content
                except Exception:
                    result = error_response()
                connection.send((request_id, result))
            while True:
                message = await asyncio.to_thread(connection.recv)
                if message is None:
                    await asyncio.gather(*tasks)
                    return
                task = asyncio.create_task(handle(*message))
                tasks.add(task)
                task.add_done_callback(tasks.discard)


def worker_main(connection, system, app_root, original_root, origin, log_path, isolated):
    with open(log_path, "a", encoding="utf-8", buffering=1) as log:
        sys.stdout = sys.stderr = log
        def watch_parent():
            parent = multiprocessing.parent_process()
            if parent:
                parent.join()
                os._exit(0)
        threading.Thread(target=watch_parent, daemon=True).start()
        try:
            # No module code is imported until its working directory and environment are isolated.
            root = Path(app_root)
            os.chdir(root)
            sys.path[:0] = [str(root), str(root / "scripts")]
            for key in list(os.environ):
                if any(word in key.upper() for word in ("TOKEN", "SECRET", "API_KEY", "PASSWORD", "MYINVEST", "TUSHARE", "PYTHONPATH")):
                    os.environ.pop(key, None)
            if isolated:
                sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
                import offline_tests
                offline_tests.pytest_configure(None)
                os.environ["MYINVESTPICKING_FORCE_MOCK"] = "1"
            else:
                original = Path(original_root)
                for relative in system["runtime_paths"]:
                    if not (root / relative).is_dir() or (root / relative).resolve() != (original / relative).resolve():
                        raise RuntimeError(f"Invalid runtime binding: {relative}")
                from dotenv import load_dotenv
                env_file = original / ".env"
                if not env_file.is_file():
                    raise RuntimeError("Original environment file is missing")
                load_dotenv(env_file, encoding="utf-8-sig", override=False)
                os.environ["MYINVEST_ENV_FILE"] = str(env_file)
                if system["id"] == "market":
                    os.environ["MYINVEST_MARKET_WEB_DATA"] = str(original / "web/data")
            from .urls import install_internal_http
            install_internal_http(origin)
            if system["id"] in ASGI:
                asyncio.run(serve_asgi(connection, system["id"]))
            else:
                handler = load_handler(system["id"])
                connection.send(("ready", os.getpid()))
                send_lock = threading.Lock()
                def handle(request_id, request):
                    try:
                        from .catalog import ENDPOINTS, catalog_response
                        if system["id"] in ENDPOINTS and request[0] in {"GET", "HEAD"} and request[1].split("?")[0] in {"/api", "/api/"}:
                            result = catalog_response(system["id"])
                        else:
                            result = dispatch_handler(handler, request)
                    except Exception:
                        result = error_response()
                    with send_lock:
                        connection.send((request_id, result))
                with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                    while True:
                        message = connection.recv()
                        if message is None:
                            break
                        executor.submit(handle, *message)
        except EOFError:
            pass
        except Exception:
            traceback.print_exc()
        finally:
            connection.close()
