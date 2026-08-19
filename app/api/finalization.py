from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from app.services.finalization import public_finalization

router = APIRouter(prefix="/api")


class CreateFinalizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    movie_title: str


def _service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (FileExistsError, RuntimeError)):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=422, detail=str(exc))


@router.get("/workflows/{workflow_id}/finalization")
def get_workflow_finalization(workflow_id: str, request: Request):
    try:
        return request.app.state.finalization_service.preview(workflow_id)
    except (FileNotFoundError, OSError, RuntimeError, ValueError, TypeError) as exc:
        raise _service_error(exc) from exc


@router.post("/workflows/{workflow_id}/finalization")
def create_workflow_finalization(
    workflow_id: str,
    payload: CreateFinalizationRequest,
    request: Request,
):
    try:
        record = request.app.state.finalization_service.create(
            workflow_id,
            payload.movie_title,
        )
    except (FileNotFoundError, FileExistsError, OSError, RuntimeError, ValueError, TypeError) as exc:
        raise _service_error(exc) from exc
    return public_finalization(record)


@router.get("/finalizations/{finalization_id}")
def get_finalization(finalization_id: str, request: Request):
    try:
        record = request.app.state.finalization_store.get(finalization_id)
        result = public_finalization(record)
        if record["state"] == "finalized":
            result["publication"] = request.app.state.finalization_service.publication_readiness(
                finalization_id
            )
        return result
    except (FileNotFoundError, OSError, RuntimeError, ValueError, TypeError) as exc:
        raise _service_error(exc) from exc


@router.post("/finalizations/{finalization_id}/finalize")
def finalize(finalization_id: str, request: Request):
    try:
        record = request.app.state.finalization_service.finalize(finalization_id)
    except (FileNotFoundError, FileExistsError, OSError, RuntimeError, ValueError, TypeError) as exc:
        raise _service_error(exc) from exc
    return public_finalization(record)


@router.post("/finalizations/{finalization_id}/publish")
def publish(finalization_id: str, request: Request):
    try:
        record = request.app.state.finalization_service.publish(finalization_id)
    except (FileNotFoundError, FileExistsError, OSError, RuntimeError, ValueError, TypeError) as exc:
        raise _service_error(exc) from exc
    return public_finalization(record)
