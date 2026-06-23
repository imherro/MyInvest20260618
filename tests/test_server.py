import json
import unittest

import server


class ServerPayloadTests(unittest.TestCase):
    def setUp(self):
        server.clear_source_cache()

    def test_public_sources_have_expected_entries(self):
        sources = server.public_sources()
        self.assertEqual(["market", "theme", "shadow", "position", "leader"], [item["id"] for item in sources])
        self.assertEqual("https://market.okbbc.com/", sources[0]["home_url"])
        self.assertEqual("https://market.okbbc.com/api/index", sources[0]["api_url"])
        self.assertNotEqual(sources[0]["home_url"], sources[0]["api_url"])
        self.assertEqual("https://leader.okbbc.com/", sources[4]["home_url"])
        self.assertEqual("https://leader.okbbc.com/api/index", sources[4]["api_url"])

    def test_all_sources_payload_preserves_source_order(self):
        def fake_fetch(source_id):
            return {"id": source_id, "ok": True, "data": {"source_id": source_id}}

        payload = server.build_all_sources_payload(fake_fetch)

        self.assertTrue(payload["ok"])
        self.assertEqual(["market", "theme", "shadow", "position", "leader"], [item["id"] for item in payload["sources"]])

    def test_footer_links_include_system_and_channels(self):
        links = server.footer_links()

        self.assertEqual(["invest", "market", "theme", "shadow", "position", "leader"], [item["id"] for item in links])
        self.assertEqual("https://invest.okbbc.com/", links[0]["url"])
        self.assertEqual("https://leader.okbbc.com/", links[-1]["url"])

    def test_footer_payload_extracts_shanghai_index(self):
        def fake_fetch(source_id):
            self.assertEqual("market", source_id)
            return {
                "id": source_id,
                "ok": True,
                "data": {
                    "summary": {
                        "basis_trade_date": "2026-06-22",
                        "data_quality": {
                            "cross_validation": {
                                "baostock_indices": {
                                    "000001.SH": {
                                        "available": True,
                                        "tushare_close": 4163.0965,
                                        "baostock_close": 4163.0965,
                                    }
                                }
                            }
                        },
                    }
                },
            }

        payload = server.build_footer_payload(fake_fetch)

        self.assertTrue(payload["ok"])
        self.assertEqual("上证指数", payload["market_index"]["name"])
        self.assertEqual("4163.10", payload["market_index"]["display"])
        self.assertEqual("2026-06-22", payload["market_index"]["as_of"])
        self.assertEqual("invest", payload["links"][0]["id"])

    def test_cached_source_reuses_value_inside_ttl(self):
        calls = []

        def fake_fetch(source_id):
            calls.append(source_id)
            return {"id": source_id, "ok": True, "data": {"call": len(calls)}}

        first = server.fetch_source_cached("market", fetcher=fake_fetch, now=1000)
        second = server.fetch_source_cached("market", fetcher=fake_fetch, now=1005)

        self.assertEqual(1, len(calls))
        self.assertFalse(first["cache"]["hit"])
        self.assertTrue(second["cache"]["hit"])
        self.assertEqual({"call": 1}, second["data"])

    def test_force_refresh_replaces_cached_source(self):
        calls = []

        def fake_fetch(source_id):
            calls.append(source_id)
            return {"id": source_id, "ok": True, "data": {"call": len(calls)}}

        server.fetch_source_cached("market", fetcher=fake_fetch, now=1000)
        refreshed = server.fetch_source_cached(
            "market",
            force_refresh=True,
            fetcher=fake_fetch,
            now=1005,
        )

        self.assertEqual(2, len(calls))
        self.assertFalse(refreshed["cache"]["hit"])
        self.assertEqual({"call": 2}, refreshed["data"])

    def test_unknown_source_payload_is_404(self):
        status, payload = server.build_single_source_payload("missing")

        self.assertEqual(404, status)
        self.assertFalse(payload["ok"])
        self.assertIn("market", payload["available_sources"])

    def test_json_response_keeps_chinese_text(self):
        body = json.dumps({"label": "市场"}, ensure_ascii=False).encode("utf-8")
        decoded = server.decode_response(body, "application/json; charset=utf-8")

        self.assertEqual({"label": "市场"}, decoded)


if __name__ == "__main__":
    unittest.main()
