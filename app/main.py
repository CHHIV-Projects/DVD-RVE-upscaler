from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.media import router as media_router
from app.config import settings

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title=settings.app_name)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.include_router(media_router)


@app.get("/", response_class=HTMLResponse)
async def landing_page(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "app_name": settings.app_name,
            "status": "Application foundation operational",
        },
    )


@app.get("/media", response_class=HTMLResponse)
async def media_page(request: Request):
    return templates.TemplateResponse(
        request,
        "media.html",
        {
            "app_name": settings.app_name,
            "status": "DVD media analysis workflow",
        },
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
