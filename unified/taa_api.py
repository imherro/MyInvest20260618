"""Unified read-only TAA catalog; native strategy and route contracts stay unchanged."""
def install(app):
    from fastapi import APIRouter
    from fastapi.responses import JSONResponse
    from backend.current_web import load_current_reports, CurrentReportsUnavailable

    router = APIRouter()

    @router.get("/api")
    @router.get("/api/", include_in_schema=False)
    def catalog():
        return {"system": "taa", "kind": "api_directory", "read_only": True, "home_url": "/",
                "endpoints": [{"method": "GET", "path": "/api/index"}]}

    @router.get("/api/index")
    def index():
        try:
            reports = load_current_reports()
        except CurrentReportsUnavailable:
            return JSONResponse({"system": "taa", "ok": False, "error": "current_reports_unavailable"}, status_code=503)
        manifest = reports["manifest"]
        return {"system": "taa", "ok": True, "read_only": True,
                "basis_date": manifest.get("data_as_of"), "generated_at": manifest.get("generated_at"),
                "model": manifest.get("model"), "home_url": "/", "reports": reports}

    app.include_router(router)
