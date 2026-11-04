import gzip
import http.client
import threading
import unittest

import server


class HttpTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.WebHubHandler)
        cls.worker = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.worker.join()

    def setUp(self):
        self.connection = http.client.HTTPConnection(*self.httpd.server_address, timeout=3)
        self.addCleanup(self.connection.close)

    def get(self, path, headers=None):
        self.connection.request("GET", path, headers=headers or {})
        response = self.connection.getresponse()
        return response, response.read()

    def test_compressed_static_and_keepalive(self):
        response, body = self.get("/", {"Accept-Encoding": "gzip"})
        self.assertEqual(response.version, 11)
        self.assertEqual(response.getheader("Content-Encoding"), "gzip")
        self.assertEqual(int(response.getheader("Content-Length")), len(body))
        self.assertEqual(gzip.decompress(body), (server.WEB_ROOT / "index.html").read_bytes())
        sock = self.connection.sock
        health, _ = self.get("/healthz")
        self.assertEqual(health.status, 200)
        self.assertIs(self.connection.sock, sock)

    def test_conditional_get_and_following_response(self):
        response, _ = self.get("/header.js", {"Accept-Encoding": "gzip"})
        cached, body = self.get("/header.js", {
            "Accept-Encoding": "gzip", "If-None-Match": response.getheader("ETag")})
        self.assertEqual(cached.status, 304)
        self.assertEqual(body, b"")
        health, _ = self.get("/healthz")
        self.assertEqual(health.status, 200)

    def test_gzip_disabled_and_etag_representation(self):
        zipped, _ = self.get("/", {"Accept-Encoding": "gzip"})
        plain, body = self.get("/", {"Accept-Encoding": "gzip;q=0, *;q=1",
                                     "If-None-Match": zipped.getheader("ETag")})
        self.assertEqual(plain.status, 200)
        self.assertIsNone(plain.getheader("Content-Encoding"))
        self.assertEqual(body, (server.WEB_ROOT / "index.html").read_bytes())

    def test_api_not_cached(self):
        response, body = self.get("/api", {"Accept-Encoding": "gzip", "If-None-Match": "*"})
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Cache-Control"), "no-store")
        self.assertEqual(response.getheader("Access-Control-Allow-Origin"), "*")
        self.assertIsNone(response.getheader("ETag"))
        self.assertTrue(gzip.decompress(body))
