import json
import unittest
import sys
from types import SimpleNamespace
from unittest.mock import patch
from unified.urls import rewrite_body, local_url
from unified.registry import module_url, resolve_route
import server


class AddedChannelsTests(unittest.TestCase):
    def test_both_channels_are_same_origin(self):
        for system in ["taa", "test"]:
            self.assertEqual(local_url(f"https://{system}.okbbc.com/"), f"/{system}/")
            self.assertEqual(local_url(f"https://{system}.okbbc.com/api/index"), f"/api/{system}/index")
            self.assertEqual(resolve_route(module_url(system, "/api/index"))[0]["id"], system)
        links = {entry["id"]: entry["url"] for entry in server.header_links()}
        self.assertEqual(links["taa"], "/taa/")
        self.assertEqual(links["test"], "/test/")

    def test_html_parser_preserves_embedded_script_and_rewrites_only_attributes(self):
        script = '''const figure = {label:"/allocation", code:"<plot>"}; x.split('/');'''
        source = '<!doctype html><a href="/allocation">A &amp; B</a><script>' + script + '</script>'
        result = rewrite_body(source.encode(), "text/html", "taa").decode()
        self.assertIn('href="/taa/allocation"', result)
        self.assertIn(script, result)
        self.assertIn("A &amp; B", result)

    def test_static_research_paths_and_shared_widgets(self):
        source = b'<a href="/480092_CNI_alpha.html">chart</a><script src="https://invest.okbbc.com/header.js"></script>'
        result = rewrite_body(source, "text/html", "test")
        self.assertIn(b'href="/test/480092_CNI_alpha.html"', result)
        self.assertIn(b'src="/header.js?', result)

    def test_health_does_not_accept_a_missing_new_channel(self):
        self.assertIn("taa", server.BY_ID)
        self.assertIn("test", server.BY_ID)

    def test_taa_api_is_read_only_and_preserves_native_report_values(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from unified.taa_api import install
        reports = {"manifest": {"data_as_of": "2026-07-14", "model": "CURRENT_TAA"},
                   "allocation": {"weight": .25, "production_actionable": False}}
        fake = SimpleNamespace(load_current_reports=lambda: reports, CurrentReportsUnavailable=RuntimeError)
        with patch.dict(sys.modules, {"backend.current_web": fake}):
            app = FastAPI()
            install(app)
            with TestClient(app) as client:
                payload = client.get("/api/index").json()
                self.assertEqual(payload["reports"], reports)
                self.assertEqual(payload["basis_date"], "2026-07-14")
                self.assertTrue(payload["read_only"])
                self.assertEqual(client.post("/api/index", json={}).status_code, 405)

    def test_taa_unavailable_report_is_not_hidden_by_old_fallback(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from unified.taa_api import install
        def fail():
            raise RuntimeError("fixture unavailable")
        with patch.dict(sys.modules, {"backend.current_web": SimpleNamespace(load_current_reports=fail, CurrentReportsUnavailable=RuntimeError)}):
            app = FastAPI()
            install(app)
            with TestClient(app) as client:
                self.assertEqual(client.get("/api/index").status_code, 503)
                self.assertEqual(client.get("/api").status_code, 200)


if __name__ == "__main__":
    unittest.main()
