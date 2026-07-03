import json
import unittest

import server


class ServerPayloadTests(unittest.TestCase):
    expected_system_ids = [
        "invest",
        "market",
        "cycle",
        "theme",
        "leader",
        "shadow",
        "position",
        "etf",
        "stock",
        "intraday",
        "short",
        "picking",
        "ten",
    ]

    def setUp(self):
        server.clear_source_cache()

    def test_public_sources_have_expected_entries(self):
        sources = server.public_sources()
        self.assertEqual(["market", "theme", "shadow", "leader", "stock", "position"], [item["id"] for item in sources])
        self.assertEqual("https://market.okbbc.com/", sources[0]["home_url"])
        self.assertEqual("https://market.okbbc.com/api/index", sources[0]["api_url"])
        self.assertNotEqual(sources[0]["home_url"], sources[0]["api_url"])
        self.assertEqual("https://leader.okbbc.com/", sources[3]["home_url"])
        self.assertEqual("https://leader.okbbc.com/api/index", sources[3]["api_url"])
        self.assertEqual("https://stock.okbbc.com/", sources[4]["home_url"])
        self.assertEqual("https://stock.okbbc.com/api/index", sources[4]["api_url"])

    def test_all_sources_payload_preserves_source_order(self):
        def fake_fetch(source_id):
            return {"id": source_id, "ok": True, "data": {"source_id": source_id}}

        payload = server.build_all_sources_payload(fake_fetch)

        self.assertTrue(payload["ok"])
        self.assertEqual(["market", "theme", "shadow", "leader", "stock", "position"], [item["id"] for item in payload["sources"]])

    def test_footer_links_include_system_and_channels(self):
        links = server.footer_links()

        self.assertEqual(self.expected_system_ids, [item["id"] for item in links])
        self.assertEqual("首页", links[0]["label"])
        self.assertEqual("https://invest.okbbc.com/", links[0]["url"])
        self.assertEqual("https://cycle.okbbc.com/", links[2]["url"])
        self.assertEqual("https://leader.okbbc.com/", links[4]["url"])
        self.assertEqual("https://position.okbbc.com/", links[6]["url"])
        self.assertEqual("https://etf.okbbc.com/", links[7]["url"])
        self.assertEqual("https://stock.okbbc.com/", links[8]["url"])
        self.assertEqual("https://intraday.okbbc.com/", links[9]["url"])
        self.assertEqual("https://short.okbbc.com/", links[10]["url"])
        self.assertEqual("https://picking.okbbc.com/", links[11]["url"])
        self.assertEqual("https://ten.okbbc.com/", links[12]["url"])

    def test_header_payload_uses_shared_navigation_links(self):
        payload = server.build_header_payload()

        self.assertTrue(payload["ok"])
        self.assertEqual("MyInvest", payload["brand"]["label"])
        self.assertEqual("https://invest.okbbc.com/", payload["brand"]["url"])
        self.assertEqual(self.expected_system_ids, [item["id"] for item in payload["links"]])

    def test_api_index_payload_lists_system_api_entries(self):
        payload = server.build_api_index_payload()

        self.assertTrue(payload["ok"])
        self.assertEqual("https://invest.okbbc.com/api", payload["system"]["api_url"])
        self.assertEqual(self.expected_system_ids, [item["id"] for item in payload["systems"]])

        systems_by_id = {item["id"]: item for item in payload["systems"]}
        self.assertEqual("https://market.okbbc.com/api", systems_by_id["market"]["api_url"])
        self.assertEqual("https://market.okbbc.com/api/index", systems_by_id["market"]["index_api_url"])
        self.assertEqual("https://cycle.okbbc.com/api", systems_by_id["cycle"]["api_url"])
        self.assertNotIn("index_api_url", systems_by_id["cycle"])
        self.assertEqual("https://intraday.okbbc.com/api", systems_by_id["intraday"]["api_url"])
        self.assertNotIn("index_api_url", systems_by_id["intraday"])
        self.assertEqual("https://short.okbbc.com/api", systems_by_id["short"]["api_url"])
        self.assertNotIn("index_api_url", systems_by_id["short"])

        endpoint_paths = [item["path"] for item in payload["endpoints"]]
        self.assertIn("/api", endpoint_paths)
        self.assertIn("/api/header", endpoint_paths)
        self.assertIn("/api/footer", endpoint_paths)

    def test_footer_payload_prefers_realtime_shanghai_index(self):
        def fake_quote():
            return {
                "name": "上证指数",
                "code": "000001.SH",
                "value": 4131.52,
                "display": "4131.52",
                "change": -31.58,
                "change_display": "-31.58",
                "change_pct": -0.76,
                "change_pct_display": "-0.76%",
                "as_of": "2026-06-23T13:20:48+08:00",
                "link": "https://xueqiu.com/S/SH000001",
                "quote_type": "realtime",
                "available": True,
            }

        payload = server.build_footer_payload(
            fetcher=lambda source_id: self.fail("market fallback should not be used"),
            quote_fetcher=fake_quote,
        )

        self.assertTrue(payload["ok"])
        self.assertEqual("realtime", payload["market_index"]["quote_type"])
        self.assertEqual("4131.52", payload["market_index"]["display"])
        self.assertEqual("-31.58", payload["market_index"]["change_display"])
        self.assertEqual("-0.76%", payload["market_index"]["change_pct_display"])
        self.assertEqual("https://xueqiu.com/S/SH000001", payload["market_index"]["link"])

    def test_footer_payload_falls_back_to_market_close(self):
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

        payload = server.build_footer_payload(fake_fetch, quote_fetcher=lambda: None)

        self.assertTrue(payload["ok"])
        self.assertEqual("上证指数", payload["market_index"]["name"])
        self.assertEqual("4163.10", payload["market_index"]["display"])
        self.assertEqual("--", payload["market_index"]["change_pct_display"])
        self.assertEqual("2026-06-22", payload["market_index"]["as_of"])
        self.assertEqual("previous_close", payload["market_index"]["quote_type"])
        self.assertEqual("https://xueqiu.com/S/SH000001", payload["market_index"]["link"])
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
