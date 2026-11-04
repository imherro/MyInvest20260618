"""HTTP integration boundary for all modules on the hub's sole listener."""
import concurrent.futures
import gzip
import re
from http import HTTPStatus
from urllib.parse import unquote, urlsplit

from .registry import resolve_route
from .runtime import ModuleBusy
from .urls import local_url, rewrite_body

HOP_HEADERS = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
               "te", "trailer", "transfer-encoding", "upgrade", "content-length", "content-encoding"}
MAX_BODY = 8 * 1024 * 1024


def read_body(handler):
    encodings = handler.headers.get_all("Transfer-Encoding", [])
    lengths = handler.headers.get_all("Content-Length", [])
    if len(lengths) > 1 or (encodings and lengths):
        raise ValueError("ambiguous_request_length")
    if encodings:
        if encodings != ["chunked"]:
            raise ValueError("unsupported_transfer_encoding")
        chunks, size, overhead = [], 0, 0
        while True:
            line = handler.rfile.readline(8193)
            overhead += len(line)
            token = line.split(b";", 1)[0].strip()
            if len(line) > 8192 or not line.endswith(b"\r\n") or not re.fullmatch(b"[0-9a-fA-F]+", token) or overhead > 65536:
                raise ValueError("invalid_chunk_framing")
            length = int(token, 16)
            size += length
            if size > MAX_BODY:
                raise ValueError("invalid_request_size")
            if not length:
                while True:
                    trailer = handler.rfile.readline(8193)
                    overhead += len(trailer)
                    if len(trailer) > 8192 or not trailer.endswith(b"\r\n") or overhead > 65536:
                        raise ValueError("invalid_chunk_trailer")
                    if trailer == b"\r\n":
                        return b"".join(chunks)
                    if b":" not in trailer:
                        raise ValueError("invalid_chunk_trailer")
            chunk = handler.rfile.read(length)
            if len(chunk) != length or handler.rfile.read(2) != b"\r\n":
                raise ValueError("incomplete_request")
            chunks.append(chunk)
    token = lengths[0] if lengths else "0"
    if not token.isascii() or not token.isdecimal() or int(token) > MAX_BODY:
        raise ValueError("invalid_request_size")
    length = int(token)
    body = handler.rfile.read(length)
    if len(body) != length:
        raise ValueError("incomplete_request")
    return body


def dispatch(handler):
    route = resolve_route(handler.path)
    if not route:
        return False
    system, original_path = route
    runtime = getattr(handler.server, "runtime", None)
    if runtime is None:
        handler.write_json({"error": "integrated_runtime_unavailable"}, status=503)
        return True
    decoded = unquote(unquote(urlsplit(original_path).path))
    if "\\" in decoded or "\0" in decoded or any(p in {".", ".."} for p in decoded.split("/")):
        handler.write_json({"error": "invalid_module_path"}, status=400)
        return True
    if handler.command not in {"GET", "HEAD", "OPTIONS"}:
        origin = handler.headers.get("Origin")
        if origin and urlsplit(origin).netloc != handler.headers.get("Host"):
            handler.close_connection = True
            handler.write_json({"error": "cross_origin_write_rejected"}, status=403)
            return True
    # Slash-normalize page roots so relative links/assets resolve inside the module.
    parsed = urlsplit(handler.path)
    if original_path.startswith("/") and parsed.path.count("/") == 1:
        handler.close_connection = True
        handler.send_response(308)
        handler.send_header("Location", parsed.path + "/" + ("?" + parsed.query if parsed.query else ""))
        handler.send_header("Content-Length", "0")
        handler.end_headers()
        return True
    try:
        body = read_body(handler)
    except ValueError as exc:
        handler.close_connection = True
        handler.write_json({"error": str(exc)}, status=413 if str(exc) == "invalid_request_size" else 400)
        return True
    headers = [(k, v) for k, v in handler.headers.items() if k.lower() not in HOP_HEADERS | {"host", "accept-encoding"}]
    headers += [("Host", f"{system['id']}.okbbc.com"), ("Content-Length", str(len(body))), ("Accept-Encoding", "identity")]
    try:
        status, response_headers, response_body = runtime.request(system["id"], (handler.command, original_path, headers, body))
    except concurrent.futures.TimeoutError:
        handler.write_json({"error": "module_timeout", "module": system["id"], "retry_write": False}, status=504)
        return True
    except ModuleBusy:
        handler.write_json({"error": "module_unavailable", "module": system["id"]}, status=503)
        return True
    content_type = next((v for k, v in response_headers if k.lower() == "content-type"), "application/octet-stream")
    encoding = next((v for k, v in response_headers if k.lower() == "content-encoding"), "")
    if encoding == "gzip":
        response_body = gzip.decompress(response_body)
    response_body = rewrite_body(response_body, content_type, system["id"])
    compressed = len(response_body) > 512 and "gzip" in handler.headers.get("Accept-Encoding", "") and "gzip;q=0" not in handler.headers.get("Accept-Encoding", "").replace(" ", "")
    if compressed:
        response_body = gzip.compress(response_body, compresslevel=6, mtime=0)
    handler.send_response(status)
    for key, value in response_headers:
        lower = key.lower()
        if lower in HOP_HEADERS | {"server", "date", "etag", "content-md5"}:
            continue
        if lower == "location":
            value = local_url(value, system["id"])
        if lower == "set-cookie":
            import re
            value = re.sub(r"(?i)(;\s*path=)(/[^;]*)", lambda m: m[1] + local_url(m[2], system["id"]), value)
        handler.send_header(key, value)
    handler.send_header("Content-Length", str(len(response_body)))
    handler.send_header("X-MyInvest-Module", system["id"])
    handler.send_header("Vary", "Accept-Encoding")
    if compressed:
        handler.send_header("Content-Encoding", "gzip")
    handler.end_headers()
    if handler.command != "HEAD" and status not in {204, 304}:
        handler.wfile.write(response_body)
    return True
