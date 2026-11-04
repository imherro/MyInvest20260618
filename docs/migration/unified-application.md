# Unified MyInvest Application

## Deployment contract

The root `server.py` serves the homepage and 13 business modules on **8888**.
Modules do not bind TCP ports. The parent owns isolated Python workers and sends
requests over private multiprocessing pipes. This preserves incompatible `core`,
`web` and `app` namespaces while presenting one application and one deployment.
Existing FastAPI lifecycles and HTTP handlers remain the business implementation.
Each worker supports bounded concurrent calls. Failed requests are never replayed;
a dead worker is recreated on the next request. A timed-out write is not killed or
retried automatically. Workers exit when the parent exits.

Routes: `/market/`, `/theme/`, `/leader/`, `/etf/`, `/stock/`, `/shadow/`,
`/intraday/`, `/position/`, `/cycle/`, `/strategy/`, `/short/`, `/picking/`, `/ten/`.
API directories: `/api/<module>`. Native API routes retain their suffix, e.g.
`/api/market/index`. The original `/module/api/...` shape is also accepted.
Not every original module has an `/api/index`; the directory documents the actual
endpoints. Short and Strategy now receive read-only API directories from the adapter.
`/api` is the complete entrypoint; `/api/health` reports worker readiness, not market
data freshness. `/healthz` remains a cheap parent-process liveness check.

Only `invest.okbbc.com -> localhost:8888` is required in Cloudflare. Existing
subdomain routes are not deleted. Old standalone ports remain recorded solely for
explicit rollback, not normal startup. Test/TAA are outside these 13 modules and
retain their existing external links and standalone deployment.

## Original data and credentials

`subsystems.json` explicitly lists 21 runtime directory bindings. `prepare_runtime.ps1`
creates Windows junctions to the original sibling directories, after checking every
target and refusing to replace any existing content. Picking's Python `data` package
stays in this repository; only its cache/frozen directories are bound. Market's
generated `web/data` charts are read from their original location too.

No databases, reports or credentials are moved into Git. Each worker independently
loads its original `.env`; values are not copied into source or logged. Original
repositories must remain on disk. **Never recursively delete, clean or copy an app
runtime junction.** Development and tests use `source_copy.py` to copy tracked
source into fresh sandboxes, never a recursive copy of the mounted app directory.

## Start and monitor

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/prepare_runtime.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/prepare_runtime.ps1 -Apply
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/ensure_web_services.ps1 -Only home
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/ensure_web_services.ps1 -Only home -NoStart
python scripts/subsystems.py check
```

The normal monitor starts one parent, probes the 13 module routes and checks worker
readiness. It does not relaunch the old 13 ports. Default monitoring also retains
Test/TAA checks; `-Only home` limits work to this integrated application.
The existing 00:00/18:00 automation can keep invoking the same monitor path.
Explicit restart requires `-Restart -Only home`; unknown port owners are refused.
`-NoStart -Restart` is rejected before doing anything. Logs are under ignored
`temp/unified/` and `temp/web_service_monitor/`.

## Verification

```powershell
python -m unittest discover -s tests -q
python scripts/test_subsystems.py --data-root C:/Users/kunpeng/Documents --timeout 1200
python scripts/check_unified.py --data-root C:/Users/kunpeng/Documents
python scripts/check_unified_browser.py --base-url http://127.0.0.1:18988
python scripts/check_unified_browser.py --base-url http://127.0.0.1:18988 --mobile
python scripts/audit_subsystems.py
```

The integration check starts a disposable source copy on a temporary port, strips
credentials, blocks external network, and loads only inventoried report fixtures
plus explicit consistent read-only SQLite backups. It covers pages, API catalogs,
business endpoints, concurrent requests, worker crash/recovery and zero worker TCP
listeners. SQLite backups and browser captures stay local and are not published.
Browser checks use an isolated instance, desktop/mobile screenshots, navigation
selection, JavaScript errors, broken responses and old-domain request detection.
The gateway accepts bounded chunked requests from Cloudflare, rejects conflicting
length headers and malformed framing, and forwards the decoded body only once.
Cycle's live Tushare endpoints intentionally return 503 without test credentials;
those failures are recorded separately, and its saved backtest API is also checked.
Passing isolated tests does not certify current upstream market data.

Deployment probes record full response completion, module identity and readiness:

```powershell
python scripts/verify_deployment.py --output temp/unified-tests/production-local.json
python scripts/verify_deployment.py --origin https://invest.okbbc.com --curl --output temp/unified-tests/production-public.json
```

For DNS/proxy diagnosis only, `--curl --resolve HOST:443:IP` tests a currently
resolved Cloudflare edge without changing DNS, certificates, hosts files or proxy
settings. Record this override separately from normal-domain acceptance; an edge
address is not a permanent application configuration. Production validation is
summarized in `unified-validation.json`. No production mutation/refresh action is
replayed as part of deployment checks.

## Rollback

Keep the prior source-only commit `4f37ed9` and the original sibling repositories.
Before cutover, export that commit's `server.py` and `web/` into an ignored rollback
directory. If needed, stop only the verified integrated parent, run the exported
old hub on 8888, and start the original subsystems explicitly:

```powershell
# Select only legacy modules, never the homepage, during this rollback step.
powershell -NoProfile -ExecutionPolicy Bypass -Command "& ./scripts/ensure_web_services.ps1 -LegacyServices -Layout legacy -Only market,theme,leader,etf,stock,shadow,intraday,position,cycle,strategyindex,short,picking,ten"
```

Old Cloudflare mappings and original data paths remain available for rollback.
Do not run the legacy and integrated workers concurrently against the same writable
database. This migration does not redirect existing daily research automations;
their original data writes remain visible through the bindings. Consolidating those
writers/automation working directories is a separate controlled change.
