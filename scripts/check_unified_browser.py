"""Browser acceptance against a disposable unified instance, never production data."""
import argparse
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright
from source_copy import ROOT

PAGES = ["", "market", "theme", "leader", "etf", "stock", "shadow", "intraday",
         "position", "cycle", "strategy", "short", "picking", "ten", "taa", "test"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:18988")
    parser.add_argument("--mobile", action="store_true")
    parser.add_argument("--page", choices=PAGES, action="append")
    parser.add_argument("--path", action="append", help="Additional exact module detail path")
    args = parser.parse_args()
    if not args.base_url.startswith("http://127.0.0.1:") or args.base_url.endswith(":8888"):
        parser.error("Use an isolated loopback instance on a non-production port")
    folder = ROOT / "temp/unified-browser" / time.strftime("%Y%m%d_%H%M%S")
    folder.mkdir(parents=True, exist_ok=True)
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 390 if args.mobile else 1366, "height": 844 if args.mobile else 900}, device_scale_factor=1)
        selected = ["/" + (name + "/" if name else "") for name in (args.page or ([] if args.path else PAGES))]
        selected += args.path or []
        if any(not path.startswith("/") or path.startswith("//") for path in selected):
            parser.error("Detail paths must be same-origin absolute paths")
        for path in selected:
            name = path.strip("/") or "home"
            page = context.new_page()
            row = {"module": name or "home", "errors": [], "failed_responses": [], "old_domain_requests": []}
            page.on("pageerror", lambda error: row["errors"].append(str(error)))
            page.on("response", lambda response: row["failed_responses"].append({"url": response.url, "status": response.status}) if response.status >= 400 else None)
            page.on("request", lambda request: row["old_domain_requests"].append(request.url) if ".okbbc.com" in request.url else None)
            try:
                response = page.goto(args.base_url + path, wait_until="domcontentloaded", timeout=30000)
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    row["pending_network_after_15s"] = True
                page.wait_for_timeout(300)
                row.update(status=response.status, title=page.title(), body_chars=len(page.locator("body").inner_text()),
                           overflow=page.evaluate("document.documentElement.scrollWidth > innerWidth + 1"),
                           active_links=page.locator(".mi-header__link[aria-current='page']").count())
                if row["overflow"]:
                    row["wide_elements"] = page.evaluate("""Array.from(document.querySelectorAll('body *')).filter(e => !['TR','TD','TH','TBODY','THEAD'].includes(e.tagName) && e.getBoundingClientRect().right > innerWidth + 1).slice(0, 12).map(e => ({tag:e.tagName, cls:e.className, width:e.getBoundingClientRect().width, right:e.getBoundingClientRect().right, overflow:getComputedStyle(e).overflowX, parent:e.parentElement.className, text:e.textContent.slice(0,60)}))""")
                page.screenshot(path=str(folder / (name.replace("/", "_") + ".png")), full_page=False)
            except Exception as exc:
                row["errors"].append(str(exc))
            results.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
            page.close()
        browser.close()
    (folder / "summary.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Browser evidence: {folder}")
    # Offline live-data failures are recorded, never hidden as transport success.
    for row in results:
        row["expected_offline_data_failures"] = [r for r in row["failed_responses"] if "/api/cycle/" in r["url"] and r["status"] == 503]
    (folder / "summary.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return int(any(row["errors"] or row["old_domain_requests"] or row.get("status") != 200 or row.get("overflow") or row.get("active_links") != 1
                   or len(row["failed_responses"]) != len(row["expected_offline_data_failures"]) for row in results))


if __name__ == "__main__":
    raise SystemExit(main())
