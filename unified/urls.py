"""URL compatibility at the integration boundary; business payloads stay intact."""
import json
import re
from urllib.parse import urlsplit, urlunsplit

from .registry import BY_ID, SYSTEMS, module_url
ASSET_VERSION = "unified-20261104"


def local_url(value, system_id=None):
    if not isinstance(value, str):
        return value
    if value.startswith(("https://", "http://", "//")):
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        if host == "invest.okbbc.com":
            path = parsed.path or "/"
            if path in {"/header.js", "/footer.js"}:
                query = (parsed.query + "&" if parsed.query else "") + "mi=" + ASSET_VERSION
                return urlunsplit(("", "", path, query, parsed.fragment))
        elif host in {"127.0.0.1", "localhost"} and parsed.port in {s["port"] for s in SYSTEMS}:
            target = next(s["id"] for s in SYSTEMS if s["port"] == parsed.port)
            path = module_url(target, parsed.path or "/")
        elif host.endswith(".okbbc.com") and host.split(".")[0] in BY_ID:
            path = module_url(host.split(".")[0], "/" + parsed.path.lstrip("/"))
        else:
            return value
        return urlunsplit(("", "", path, parsed.query, parsed.fragment))
    if system_id and value.startswith("/") and not value.startswith("//"):
        return module_url(system_id, value)
    return value


def json_urls(value, system_id):
    if isinstance(value, dict):
        return {key: json_urls(item, system_id) for key, item in value.items()}
    if isinstance(value, list):
        return [json_urls(item, system_id) for item in value]
    return local_url(value, system_id) if isinstance(value, str) else value


# Only URL-bearing literals: a bare '/' in JS split/replace must remain unchanged.
URL_LITERAL = re.compile(r'''(?P<quote>["'])(?P<url>(?:https?://|//)[^\s"'`<>]+|/[A-Za-z][^\s"'`<>]*)(?P=quote)''')
TEMPLATE_URL = re.compile(r'''`(?P<url>(?:https?://|//)[^`$\s<>]+|/[A-Za-z][^`$\s<>]*)''')
HTML_ROOT = re.compile(r'''(?P<attr>\b(?:href|src|action|poster)\s*=\s*)(?P<q>["'])(?P<url>/)(?P=q)''', re.I)
CSS_URL = re.compile(r'''url\(\s*(?P<url>/[^\s)'"]+)\s*\)''', re.I)


def rewrite_body(body, content_type, system_id):
    if not any(kind in content_type.lower() for kind in ("html", "javascript", "json", "text/css")):
        return body
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return body
    if "json" in content_type.lower():
        try:
            original = json.loads(text)
            payload = json_urls(original, system_id)
            if isinstance(original, dict) and "openapi" in original and "paths" in original:
                payload["paths"] = {module_url(system_id, key): json_urls(value, system_id) for key, value in original["paths"].items()}
                payload["servers"] = [{"url": "/"}]
            return json.dumps(payload, ensure_ascii=False).encode("utf-8")
        except ValueError:
            return body
    text = URL_LITERAL.sub(lambda m: m["quote"] + local_url(m["url"], system_id) + m["quote"], text)
    text = TEMPLATE_URL.sub(lambda m: "`" + local_url(m["url"], system_id), text)
    text = HTML_ROOT.sub(lambda m: m["attr"] + m["q"] + module_url(system_id) + m["q"], text)
    text = CSS_URL.sub(lambda m: "url(" + local_url(m["url"], system_id) + ")", text)
    return text.encode("utf-8")


def install_internal_http(origin):
    """Keep existing API consumers local without changing third-party data sources."""
    def convert(url):
        value = str(url)
        result = local_url(value)
        return origin + result if result != value else url

    import urllib.request
    original_request = urllib.request.Request.__init__

    def request(self, url, *args, **kwargs):
        original_request(self, convert(url), *args, **kwargs)

    urllib.request.Request.__init__ = request
    import httpx
    original_build = httpx.Client.build_request
    original_async_build = httpx.AsyncClient.build_request
    httpx.Client.build_request = lambda self, method, url, **kwargs: original_build(self, method, convert(url), **kwargs)
    httpx.AsyncClient.build_request = lambda self, method, url, **kwargs: original_async_build(self, method, convert(url), **kwargs)
    import requests
    original_prepare = requests.Session.prepare_request

    def prepare(self, request):
        request.url = convert(request.url)
        return original_prepare(self, request)

    requests.Session.prepare_request = prepare
