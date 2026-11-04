"""API directories for the two legacy handlers that never had a catalog route."""
import json

ENDPOINTS = {
    "strategyindex": ["/health.json", "/api/strategy-backtests/index.json", "/api/value-compare/history.json",
                      "/api/chinext-compare/history.json", "/api/four-asset-compare/history.json",
                      "/api/three-asset-compare/history.json", "/api/cashflow-growth-compare/history.json",
                      "/api/us-etf-compare/history.json", "/api/us-inflation-portfolio/history.json",
                      "/api/us-etf-strategy-observer/history.json"],
    "short": ["/health.json", "/api/etf-compare/history.json", "/api/index-compare/history.json",
              "/api/value-compare/history.json", "/api/trend-channels/broad.json",
              "/api/trend-channels/theme.json", "/api/capital-migration/radar.json"],
}


def catalog_response(system_id):
    payload = {"system": system_id, "kind": "api_directory", "home_url": "/",
               "endpoints": [{"method": "GET", "path": path} for path in ENDPOINTS[system_id]]}
    return 200, [("Content-Type", "application/json; charset=utf-8")], json.dumps(payload).encode()
