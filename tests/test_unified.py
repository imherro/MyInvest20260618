import io
import concurrent.futures
import http.client
from email.message import Message
from types import SimpleNamespace
import json
import threading
import tempfile
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from pathlib import Path
from unittest.mock import patch

from unified.registry import SYSTEMS, module_url, resolve_route
from unified.urls import local_url, rewrite_body
from unified.worker import dispatch_handler
from unified.runtime import ModuleBusy, ModuleWorker
from unified.gateway import read_body, MAX_BODY


class UnifiedTests(unittest.TestCase):
    def test_bounded_chunked_body_and_trailers(self):
        headers = Message()
        headers["Transfer-Encoding"] = "chunked"
        handler = SimpleNamespace(headers=headers, rfile=io.BytesIO(b"3;ext=1\r\nabc\r\n2\r\nde\r\n0\r\nX-Trailer: ok\r\n\r\n"))
        self.assertEqual(read_body(handler), b"abcde")

    def test_invalid_chunked_framing_rejected(self):
        for body in [b"wat\r\n", b"3\r\nab", b"0\r\nbad\r\n", f"{MAX_BODY + 1:x}\r\n".encode()]:
            with self.subTest(body=body):
                headers = Message()
                headers["Transfer-Encoding"] = "chunked"
                with self.assertRaises(ValueError):
                    read_body(SimpleNamespace(headers=headers, rfile=io.BytesIO(body)))

    def test_ambiguous_lengths_rejected(self):
        for chunked in [True, False]:
            headers = Message()
            headers["Content-Length"] = "0"
            headers["Transfer-Encoding" if chunked else "Content-Length"] = "chunked" if chunked else "0"
            with self.assertRaisesRegex(ValueError, "ambiguous_request_length"):
                read_body(SimpleNamespace(headers=headers, rfile=io.BytesIO(b"")))

    def test_worker_exit_fails_pending_without_replay(self):
        worker = ModuleWorker(SYSTEMS[0], Path("."), "http://127.0.0.1", Path("."), True)
        future = concurrent.futures.Future()
        worker.pending[1] = future
        worker.ready = True
        worker.fail_pending()
        with self.assertRaisesRegex(ModuleBusy, "not replayed"):
            future.result(timeout=0)
        self.assertEqual(worker.pending, {})
        self.assertFalse(worker.ready)

    def test_old_reader_cannot_fail_new_worker_requests(self):
        worker = ModuleWorker(SYSTEMS[0], Path("."), "http://127.0.0.1", Path("."), True)
        worker.connection = object()
        future = concurrent.futures.Future()
        worker.pending[2] = future
        worker.ready = True
        worker.fail_pending(object())
        self.assertFalse(future.done())
        self.assertTrue(worker.ready)
        worker.close()
        self.assertTrue(future.done())

    def test_all_modules_round_trip(self):
        for system in SYSTEMS:
            for path in ["/", "/api", "/api/index?x=1", "/static/a.js", "/stock/600000.SH"]:
                with self.subTest(module=system["id"], path=path):
                    target, actual = resolve_route(module_url(system["id"], path))
                    self.assertEqual(target["id"], system["id"])
                    self.assertEqual(actual, path)

    def test_known_hosts_only(self):
        self.assertEqual(local_url("https://leader.okbbc.com/api/index?q=1#abc"), "/api/leader/index?q=1#abc")
        self.assertEqual(local_url("https://market.okbbc.com//api/latest"), "/api/market/latest")
        self.assertEqual(local_url("http://127.0.0.1:8021/api"), "/api/cycle")
        self.assertEqual(local_url("https://xueqiu.com/S/SH000001"), "https://xueqiu.com/S/SH000001")
        self.assertEqual(local_url("https://market.okbbc.com.evil.test/api"), "https://market.okbbc.com.evil.test/api")

    def test_javascript_and_html_urls_without_rewriting_split(self):
        source = b'''<a href="/">home</a><script src="https://invest.okbbc.com/header.js"></script>
        fetch(`/api/index?q=${code}`); x.split('/'); const re = /foo/;
        <link href="/static/a.css"><a href="https://stock.okbbc.com/">stock</a>'''
        result = rewrite_body(source, "text/html", "theme").decode()
        self.assertIn('href="/theme/"', result)
        self.assertIn('src="/header.js?mi=unified-20261104"', result)
        self.assertIn('`/api/theme/index?q=${code}`', result)
        self.assertIn("x.split('/')", result)
        self.assertIn('href="/theme/static/a.css"', result)
        self.assertIn('href="/stock/"', result)
        self.assertEqual(rewrite_body(b'''fetch(`/api/index${refresh ? "?refresh=1" : ""}`)''', "text/javascript", "intraday"),
                         b'''fetch(`/api/intraday/index${refresh ? "?refresh=1" : ""}`)''')

    def test_css_rewritten_once(self):
        result = rewrite_body(b'''a{background:url("/static/a.png")} b{background:url(/static/b.png)}''', "text/css", "theme")
        self.assertEqual(result.count(b"/theme/static/"), 2)
        self.assertNotIn(b"/theme/theme", result)

    def test_json_contract_values_preserved(self):
        source = {"ratio": .23, "date": "2026-11-04", "rows": [{"url": "/api/index"}], "private": False}
        result = json.loads(rewrite_body(json.dumps(source).encode(), "application/json", "shadow"))
        self.assertEqual(result, {**source, "rows": [{"url": "/api/shadow/index"}]})

    def test_openapi_paths_are_integrated(self):
        source = {"openapi": "3.1.0", "paths": {"/api/index": {"get": {}}}}
        result = json.loads(rewrite_body(json.dumps(source).encode(), "application/json", "theme"))
        self.assertEqual(list(result["paths"]), ["/api/theme/index"])
        self.assertEqual(result["servers"], [{"url": "/"}])

    def test_handler_adapter_preserves_body_status_and_headers(self):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(201)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Location", "/result")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass
        body = b"\x00test\xff"
        status, headers, result = dispatch_handler(Handler, ("POST", "/submit", [("Content-Length", str(len(body)))], body))
        self.assertEqual(status, 201)
        self.assertIn(("Location", "/result"), headers)
        self.assertEqual(result, body)

    def test_binary_is_not_modified(self):
        body = b'\xff\x00"/api/test"'
        self.assertEqual(rewrite_body(body, "image/png", "theme"), body)

    def test_source_copy_does_not_walk_runtime_directories(self):
        from scripts.source_copy import copy_source
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "source"
            copy_source("MyInvestPicking", target)
            self.assertTrue((target / "data/cache_manager.py").is_file())
            self.assertFalse((target / "data/cache").exists())
            self.assertFalse((target / ".env").exists())


class GatewayTests(unittest.TestCase):
    def setUp(self):
        import server
        self.calls = []
        owner = self
        class Runtime:
            def request(self, system_id, request):
                owner.calls.append((system_id, request))
                return 201 if request[0] == "POST" else 200, [("Content-Type", "application/json"), ("Location", "/api/next")], b'{"url":"/api/index","value":3}'
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), server.WebHubHandler)
        self.server.runtime = Runtime()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_post_preserves_query_body_and_auth(self):
        request = Request(self.origin + "/api/market/submit?x=%2F", data=b'{"x":1}', headers={"Authorization": "Bearer fixture", "Content-Type": "application/json"})
        with urlopen(request) as response:
            self.assertEqual(response.status, 201)
            self.assertEqual(response.headers["Location"], "/api/market/next")
        system, (method, path, headers, body) = self.calls[0]
        self.assertEqual((system, method, path, body), ("market", "POST", "/api/submit?x=%2F", b'{"x":1}'))
        self.assertIn(("Authorization", "Bearer fixture"), headers)

    def test_head_has_no_body(self):
        with urlopen(Request(self.origin + "/api/theme", method="HEAD")) as response:
            self.assertEqual(response.read(), b"")

    def test_chunked_post_is_decoded_before_module_dispatch(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        try:
            connection.request("POST", "/api/market/submit", body=iter([b"abc", b"de"]), encode_chunked=True)
            response = connection.getresponse()
            self.assertEqual(response.status, 201)
            response.read()
            self.assertEqual(self.calls[0][1][3], b"abcde")
            self.assertIn(("Content-Length", "5"), self.calls[0][1][2])
        finally:
            connection.close()

    def test_traversal_rejected_before_dispatch(self):
        with self.assertRaises(HTTPError) as caught:
            urlopen(self.origin + "/market/%252e%252e/.env")
        self.assertEqual(caught.exception.code, 400)
        caught.exception.close()
        self.assertFalse(self.calls)

    def test_cross_origin_write_rejected_before_dispatch(self):
        with self.assertRaises(HTTPError) as caught:
            urlopen(Request(self.origin + "/api/shadow/refresh", data=b"{}", headers={"Origin": "https://evil.test"}))
        self.assertEqual(caught.exception.code, 403)
        caught.exception.close()
        self.assertFalse(self.calls)

    def test_unknown_module_does_not_reach_worker(self):
        with self.assertRaises(HTTPError) as caught:
            urlopen(self.origin + "/api/not-a-module/index")
        self.assertEqual(caught.exception.code, 404)
        caught.exception.close()
        self.assertFalse(self.calls)
