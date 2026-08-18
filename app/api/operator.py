from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from app.services.operator_state import public_location, public_workflow

router = APIRouter(prefix="/api")


class CreateLocationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str
    role: Literal["ORIGINAL_SOURCE", "FINISHED_DESTINATION"]
    folder: str


class UpdateLocationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = None
    enabled: bool | None = None


class CreateWorkflowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_location_id: str
    source_relative_path: str


class UpdateWorkflowDestinationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    destination_location_id: str


def _service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=422, detail=str(exc))


@router.get("/library-locations")
def list_library_locations(
    request: Request,
    role: Literal["ORIGINAL_SOURCE", "FINISHED_DESTINATION"] | None = None,
):
    locations = request.app.state.operator_store.list_locations(role=role)
    return {"locations": [public_location(location) for location in locations]}


@router.post("/library-locations")
def create_library_location(payload: CreateLocationRequest, request: Request):
    try:
        location = request.app.state.operator_store.create_location(
            payload.display_name,
            payload.role,
            payload.folder,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise _service_error(exc) from exc
    return public_location(location)


@router.patch("/library-locations/{location_id}")
def update_library_location(
    location_id: str,
    payload: UpdateLocationRequest,
    request: Request,
):
    try:
        location = request.app.state.operator_store.update_location(
            location_id,
            display_name=payload.display_name,
            enabled=payload.enabled,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise _service_error(exc) from exc
    return public_location(location)


@router.get("/workflows/current")
def get_current_workflow(request: Request):
    workflow = request.app.state.operator_store.get_current_workflow()
    return {"workflow": public_workflow(workflow) if workflow else None}


@router.post("/workflows")
def create_workflow(payload: CreateWorkflowRequest, request: Request):
    try:
        workflow = request.app.state.operator_store.create_workflow(
            payload.source_location_id,
            payload.source_relative_path,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise _service_error(exc) from exc
    return public_workflow(workflow)


@router.patch("/workflows/{workflow_id}/destination")
def set_workflow_destination(
    workflow_id: str,
    payload: UpdateWorkflowDestinationRequest,
    request: Request,
):
    try:
        workflow = request.app.state.operator_store.set_destination(
            workflow_id,
            payload.destination_location_id,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise _service_error(exc) from exc
    return public_workflow(workflow)


@router.get("/system/telemetry")
def get_system_telemetry(request: Request):
    return request.app.state.telemetry_service.snapshot()
