from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.media import router as media_router
from app.api.finalization import router as finalization_router
from app.api.operator import router as operator_router
from app.api.rve import router as rve_router
from app.config import settings
from app.services.operator_state import OperatorStateStore
from app.services.finalization import FinalizationService, FinalizationStore
from app.services.rve_jobs import RVEJobManager, RVEJobStore
from app.services.system_telemetry import TelemetryService

BASE_DIR = Path(__file__).resolve().parent

@asynccontextmanager
async def lifespan(application: FastAPI):
    store = RVEJobStore()
    store.initialize()
    store.reconcile_interrupted()
    operator_store = OperatorStateStore()
    operator_store.initialize()
    finalization_store = FinalizationStore()
    finalization_store.initialize()
    finalization_store.reconcile_interrupted()
    manager = RVEJobManager(store)
    application.state.rve_store = store
    application.state.rve_manager = manager
    application.state.operator_store = operator_store
    application.state.finalization_store = finalization_store
    application.state.finalization_service = FinalizationService(
        finalization_store,
        operator_store,
        store,
    )
    application.state.telemetry_service = TelemetryService()
    yield
    manager.shutdown()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.include_router(media_router)
app.include_router(finalization_router)
app.include_router(rve_router)
app.include_router(operator_router)


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
