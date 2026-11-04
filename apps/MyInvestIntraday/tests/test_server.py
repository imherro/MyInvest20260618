from __future__ import annotations

import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zoneinfo import ZoneInfo

import server


class IntradayServerTests(unittest.TestCase):
    def setUp(self) -> None:
        server._SOURCE_CACHE.clear()

    def test_default_port_is_8022(self) -> None:
        self.assertEqual(8022, server.DEFAULT_PORT)

    def test_api_catalog_is_read_only(self) -> None:
        payload = server.build_api_catalog()
        self.assertEqual("read_only", payload["safety"]["mode"])
        self.assertEqual("disabled", payload["safety"]["trading"])
        methods = {endpoint["method"] for endpoint in payload["endpoints"]}
        self.assertEqual({"GET"}, methods)

    def test_env_flags_do_not_expose_secret_values(self) -> None:
        with TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "TUSHARE_TOKEN=abc123\nFRED_API_KEY=xyz789\n",
                encoding="utf-8",
            )
            flags = server.read_env_flags(env_path)
        self.assertEqual(
            {
                "env_file": True,
                "tushare_token": True,
                "fred_api_key": True,
            },
            flags,
        )
        self.assertNotIn("abc123", str(flags))
        self.assertNotIn("xyz789", str(flags))

    def test_market_clock_detects_morning_session(self) -> None:
        now = datetime(2026, 7, 3, 10, 15, tzinfo=ZoneInfo("Asia/Shanghai"))
        clock = server.market_clock(now)
        self.assertEqual("morning", clock["session"])
        self.assertTrue(clock["is_live"])

    def test_index_payload_uses_injected_fetcher(self) -> None:
        def fake_fetcher(channel_id: str) -> dict[str, object]:
            config = server.CHANNELS[channel_id]
            return {
                "id": channel_id,
                "label": config["label"],
                "title": config["title"],
                "home_url": config["home_url"],
                "api_url": config["api_url"],
                "index_api_url": config["index_api_url"],
                "ok": True,
                "status": "ok",
                "fetched_at": "2026-07-03T10:00:00+08:00",
                "basis_date": "2026-07-02",
                "metrics": [{"label": "市场分", "value": 55}] if channel_id == "market" else [],
                "items": [],
            }

        with (
            patch.object(server, "fetch_position_payload", return_value=None),
            patch.object(server, "read_strategy_weights", return_value=[]),
            patch.object(
                server,
                "fetch_live_quotes",
                return_value={"ok": True, "source": "test", "quotes": [], "generated_at": "2026-07-03T10:00:00+08:00"},
            ),
            patch.object(
                server,
                "fetch_industry_boards",
                return_value={"ok": True, "generated_at": "2026-07-03T10:00:00+08:00", "groups": {}, "errors": {}},
            ),
        ):
            payload = server.build_index_payload(fetcher=fake_fetcher)
        self.assertTrue(payload["ok"])
        self.assertEqual("fullscreen", payload["page"]["layout"])
        self.assertEqual(list(server.CHANNELS.keys()), [channel["id"] for channel in payload["channels"]])


if __name__ == "__main__":
    unittest.main()
