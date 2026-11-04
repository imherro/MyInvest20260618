from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.api.catalog import router as catalog_router
from app.api.stock import router as stock_router
from config.settings import APP_NAME, APP_VERSION


BASE_DIR = Path(__file__).resolve().parent
PAGES_DIR = BASE_DIR / "pages"

app = FastAPI(title=APP_NAME, version=APP_VERSION)
app.include_router(catalog_router)
app.include_router(stock_router)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(PAGES_DIR / "index.html")
