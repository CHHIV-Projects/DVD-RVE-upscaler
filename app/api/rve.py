from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from app.services.rve_jobs import create_rve_job, list_local_preparations, public_job

router = APIRouter(prefix="/api/rve")


class CreateRVEJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preparation_id: str


def _service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, RuntimeError):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=422, detail=str(exc))


@router.get("/preparations")
def list_preparations():
    return {"preparations": list_local_preparations()}


@router.post("/jobs")
def create_job(payload: CreateRVEJobRequest, request: Request):
    try:
        job = create_rve_job(payload.preparation_id, request.app.state.rve_store)
    except (FileNotFoundError, FileExistsError, RuntimeError, ValueError, TypeError) as exc:
        raise _service_error(exc) from exc
    return public_job(job)


@router.post("/jobs/{job_id}/start")
def start_job(job_id: str, request: Request):
    try:
        return public_job(request.app.state.rve_manager.start(job_id))
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        raise _service_error(exc) from exc


@router.get("/jobs/{job_id}")
def get_job(job_id: str, request: Request):
    try:
        return public_job(request.app.state.rve_store.get(job_id))
    except (FileNotFoundError, ValueError) as exc:
        raise _service_error(exc) from exc


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, request: Request):
    try:
        return public_job(request.app.state.rve_manager.cancel(job_id))
    except (FileNotFoundError, ValueError) as exc:
        raise _service_error(exc) from exc
