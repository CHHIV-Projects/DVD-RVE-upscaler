from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from pathlib import Path

from app.services.media_preparation import load_preparation_plan
from app.services.operator_state import public_workflow
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
        operator_store = getattr(request.app.state, "operator_store", None)
        if operator_store and hasattr(operator_store, "find_workflow_by_preparation"):
            workflow = operator_store.find_workflow_by_preparation(payload.preparation_id)
            if workflow and workflow["rve_job_id"]:
                raise RuntimeError(
                    "This workflow already has an RVE job; duplicate enhancement is not the default action."
                )
        job = create_rve_job(payload.preparation_id, request.app.state.rve_store)
        if hasattr(request.app.state, "operator_store"):
            request.app.state.operator_store.associate_rve_job(
                payload.preparation_id,
                job["job_id"],
            )
    except (FileNotFoundError, FileExistsError, RuntimeError, ValueError, TypeError) as exc:
        raise _service_error(exc) from exc
    return public_job(job)


@router.get("/jobs")
def list_jobs(request: Request, limit: int = 10):
    jobs = []
    for record in request.app.state.rve_store.list_recent(limit):
        job = public_job(record)
        try:
            plan = load_preparation_plan(record["preparation_id"])
            source_relative_path = plan.get("source_relative_path")
        except (FileNotFoundError, OSError, TypeError, ValueError):
            source_relative_path = None
        source_path = Path(source_relative_path) if source_relative_path else None
        workflow = (
            request.app.state.operator_store.find_workflow_by_job(record["job_id"])
            if hasattr(request.app.state, "operator_store")
            else None
        )
        job["source_relative_path"] = source_relative_path
        job["movie_name"] = (
            source_path.parent.name
            if source_path and source_path.parent != Path(".")
            else source_path.stem if source_path else "Unknown source"
        )
        job["workflow"] = public_workflow(workflow) if workflow else None
        jobs.append(job)
    return {"jobs": jobs}


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
