import io
import json
from types import SimpleNamespace

from scripts import serve_web


class Socket:
    def __init__(self, request):
        self.input = io.BytesIO(request)
        self.output = io.BytesIO()

    def makefile(self, *args):
        return self.input

    def sendall(self, data):
        self.output.write(data)


def request(tmp_path, monkeypatch, path, method="GET"):
    monkeypatch.setattr(serve_web, "OUTPUT", tmp_path)
    sock = Socket(f"{method} {path} HTTP/1.0\r\nHost: localhost\r\n\r\n".encode())
    serve_web.ResearchHandler(sock, ("127.0.0.1", 0), SimpleNamespace())
    return sock.output.getvalue()


def test_serves_existing_html_and_csv(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("<h1>Research</h1>")
    (tmp_path / "prices.csv").write_text("date,close\n2026-07-01,1\n")
    assert b"200 OK" in request(tmp_path, monkeypatch, "/")
    assert b"date,close" in request(tmp_path, monkeypatch, "/prices.csv")


def test_catalog_and_basis_come_from_existing_data(tmp_path, monkeypatch):
    (tmp_path / "480092_CNI_daily.csv").write_text("trade_date,close\n2026-07-01,1\n2026-07-02,2\n")
    response = request(tmp_path, monkeypatch, "/api/index")
    payload = json.loads(response.split(b"\r\n\r\n", 1)[1])
    assert payload["basis_date"] == "2026-07-02"
    assert payload["read_only"] is True
    assert b"api_directory" in request(tmp_path, monkeypatch, "/api")


def test_no_directory_listing_credentials_or_traversal(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("FIXTURE_ONLY=1")
    (tmp_path / "nested").mkdir()
    for path in ["/.env", "/nested/", "/../outside.html", "/%2e%2e/outside.html"]:
        assert b"404 Not Found" in request(tmp_path, monkeypatch, path)


def test_write_methods_rejected_and_head_body_empty(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("<h1>Research</h1>")
    assert b"501" in request(tmp_path, monkeypatch, "/api/index", "POST")
    assert request(tmp_path, monkeypatch, "/", "HEAD").split(b"\r\n\r\n", 1)[1] == b""
