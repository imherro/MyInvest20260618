"""The module registry is shared by routing, workers and operational tooling."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYSTEMS = json.loads((ROOT / "subsystems.json").read_text(encoding="utf-8"))["systems"]
BY_ID = {s["id"]: s for s in SYSTEMS}
SLUGS = {s["id"]: ("strategy" if s["id"] == "strategyindex" else s["id"]) for s in SYSTEMS}
BY_SLUG = {SLUGS[s["id"]]: s for s in SYSTEMS}


def module_url(system_id, path="/"):
    slug = SLUGS[system_id]
    if path == "/api" or path.startswith("/api/") or path.startswith("/api?"):
        return f"/api/{slug}" + path[4:]
    return f"/{slug}" + (path if path.startswith("/") else "/" + path)


def resolve_route(path):
    """Return (module, original path). Query/percent encoding is preserved."""
    if path.startswith("/api/"):
        slug, sep, rest = path[5:].partition("/")
        slug, query_sep, query = slug.partition("?")
        if slug in BY_SLUG:
            return BY_SLUG[slug], "/api" + ("/" + rest if sep else "") + ("?" + query if query_sep else "")
    slug, sep, rest = path.lstrip("/").partition("/")
    slug, query_sep, query = slug.partition("?")
    if slug in BY_SLUG:
        return BY_SLUG[slug], ("/" + rest if sep else "/") + ("?" + query if query_sep else "")
    return None
