import json
import unittest

import server


class ServerPayloadTests(unittest.TestCase):
    def test_public_sources_have_four_entries(self):
        sources = server.public_sources()
        self.assertEqual(["market", "theme", "shadow", "position"], [item["id"] for item in sources])

    def test_all_sources_payload_preserves_source_order(self):
        def fake_fetch(source_id):
            return {"id": source_id, "ok": True, "data": {"source_id": source_id}}

        payload = server.build_all_sources_payload(fake_fetch)

        self.assertTrue(payload["ok"])
        self.assertEqual(["market", "theme", "shadow", "position"], [item["id"] for item in payload["sources"]])

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

