"""Read-only serving of existing research output; never generate reports here."""
import argparse
import csv
import json
from datetime import date
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

OUTPUT = Path(__file__).resolve().parents[1] / "output"
PUBLIC_SUFFIXES = {".html", ".csv", ".json", ".md", ".js", ".css", ".png", ".svg"}


def index_payload():
    dates = []
    daily = OUTPUT / "480092_CNI_daily.csv"
    if daily.is_file():
        with daily.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                try:
                    dates.append(date.fromisoformat(row.get("trade_date", "")))
                except ValueError:
                    continue
    return {"system": "test", "read_only": True, "home_url": "/",
            "basis_date": max(dates).isoformat() if dates else None,
            "artifacts": [{"name": path.name, "url": "/" + path.name, "bytes": path.stat().st_size}
                          for path in sorted(OUTPUT.glob("*"))
                          if path.is_file() and not path.is_symlink() and path.resolve().parent == OUTPUT.resolve()
                          and path.suffix in PUBLIC_SUFFIXES]}


class ResearchHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(OUTPUT), **kwargs)

    def send_head(self):
        path = unquote(urlsplit(self.path).path)
        if path in {"/api", "/api/", "/api/index"}:
            payload = index_payload() if path == "/api/index" else {
                "system": "test", "kind": "api_directory", "read_only": True, "home_url": "/",
                "endpoints": [{"method": "GET", "path": "/api/index"}]}
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            import io
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return io.BytesIO(data)
        target = OUTPUT / ("index.html" if path == "/" else path.lstrip("/"))
        if ("\\" in path or any(p in {".", ".."} for p in path.split("/"))
                or not target.resolve().is_relative_to(OUTPUT.resolve()) or target.is_symlink()
                or not target.is_file() or target.suffix not in PUBLIC_SUFFIXES):
            self.send_error(404)
            return None
        return super().send_head()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8024)
    args = parser.parse_args()
    ThreadingHTTPServer((args.host, args.port), ResearchHandler).serve_forever()
