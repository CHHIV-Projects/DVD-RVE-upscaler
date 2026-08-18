from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from app.config import settings
from app.services.media_analysis import analyze_candidate
from app.services.media_discovery import (
    discover_candidates,
    discover_candidates_across_locations,
    validate_candidate_relative_path,
)
from app.services.media_preparation import (
    assess_preparation_eligibility,
    create_preparation_plan,
    execute_preparation,
    load_preparation_plan,
    propose_preparation_decision,
    public_preparation_plan,
)

router = APIRouter(prefix="/api/media")
PREPARATION_ID_NAMESPACE = uuid.UUID("2f10b2bd-120a-4acd-af63-16bbcf09877f")


class MediaAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location_id: str | None = None
    relative_path: str


class PreparationPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location_id: str | None = None
    workflow_id: str | None = None
    relative_path: str
    decision: Literal["progressive", "deinterlace_tff", "deinterlace_bff"]


class PreparationExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preparation_id: str


def _preparation_http_error(exc: Exception) -> HTTPException:
    detail = str(exc)
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=404, detail=detail)
    if isinstance(exc, FileExistsError):
        return HTTPException(status_code=409, detail=detail)
    return HTTPException(status_code=422, detail=detail)


def _source_location(request: Request | None, location_id: str | None) -> dict:
    if request is None or not hasattr(request.app.state, "operator_store"):
        if location_id:
            raise FileNotFoundError("Library location state is unavailable.")
        return {
            "location_id": None,
            "display_name": "DVD Intake",
            "server_root": settings.dvd_source_root,
        }
    store = request.app.state.operator_store
    if location_id:
        return store.get_location(
            location_id,
            role="ORIGINAL_SOURCE",
            require_enabled=True,
        )
    for location in store.list_locations(role="ORIGINAL_SOURCE", enabled=True):
        if location["server_root"] == settings.dvd_source_root:
            return location
    raise FileNotFoundError("Initial DVD source location is not configured.")


def _workflow_preparation_id(workflow: dict, decision: str) -> str:
    identity = ":".join(
        (
            workflow["workflow_id"],
            workflow["source_location_id"],
            workflow["source_relative_path"],
            workflow["destination_location_id"],
            decision,
            "preparation-v1",
        )
    )
    return uuid.uuid5(PREPARATION_ID_NAMESPACE, identity).hex


def _validate_workflow_plan(
    plan: dict,
    workflow: dict,
    location: dict,
    decision: str,
) -> None:
    if (
        plan.get("source_location_id") not in {None, location["location_id"]}
        or plan.get("source_relative_path") != workflow["source_relative_path"]
    ):
        raise ValueError("Workflow preparation plan does not match the selected source.")
    if plan.get("selected_preparation_decision") != decision:
        raise ValueError(
            "Workflow preparation decision conflicts with the existing preparation plan."
        )
    if plan.get("workflow_id") not in {None, workflow["workflow_id"]}:
        raise ValueError("Preparation plan belongs to a different workflow.")
    if plan.get("destination_location_id") not in {
        None,
        workflow["destination_location_id"],
    }:
        raise ValueError("Workflow preparation plan does not match the intended destination.")


@router.get("/discover")
def discover_media(request: Request, query: str = ""):
    if not hasattr(request.app.state, "operator_store"):
        candidates = discover_candidates()
        normalized_query = query.strip().lower()
        results = []
        for candidate in candidates:
            searchable = " ".join(
                (
                    candidate.get("filename", ""),
                    candidate.get("movie_folder", "."),
                    "DVD Intake",
                )
            ).lower()
            if normalized_query and normalized_query not in searchable:
                continue
            eligibility = assess_preparation_eligibility(
                candidate["relative_path"],
                root=settings.dvd_source_root,
                verify_read_only_mount=False,
            )
            if not eligibility["eligible"]:
                continue
            results.append({**candidate, "preparation_eligibility": eligibility})
        return {"count": len(results), "candidates": results}

    locations = request.app.state.operator_store.list_locations(
        role="ORIGINAL_SOURCE",
        enabled=True,
    )
    candidates = discover_candidates_across_locations(locations)
    roots = {location["location_id"]: location["server_root"] for location in locations}
    normalized_query = query.strip().lower()
    results = []
    for candidate in candidates:
        searchable = " ".join(
            (
                candidate["filename"],
                candidate["movie_folder"],
                candidate["location_name"],
            )
        ).lower()
        if normalized_query and normalized_query not in searchable:
            continue
        eligibility = assess_preparation_eligibility(
            candidate["relative_path"],
            root=roots[candidate["location_id"]],
            verify_read_only_mount=False,
        )
        if not eligibility["eligible"]:
            continue
        results.append({**candidate, "preparation_eligibility": eligibility})
    return {"count": len(results), "candidates": results}


@router.post("/analyze")
def analyze_media(payload: MediaAnalysisRequest, request: Request):
    try:
        location = _source_location(request, payload.location_id)
        validate_candidate_relative_path(
            payload.relative_path,
            root=location["server_root"],
        )
        analysis = analyze_candidate(payload.relative_path, root=location["server_root"])
    except (FileNotFoundError, ValueError, TypeError) as exc:
        detail = str(exc)
        if "Absolute paths" in detail:
            raise HTTPException(status_code=400, detail="invalid path") from exc
        if "Path traversal" in detail:
            raise HTTPException(status_code=400, detail="invalid path") from exc
        if "outside the approved DVD source root" in detail:
            raise HTTPException(status_code=400, detail="outside approved root") from exc
        if "not found" in detail.lower():
            raise HTTPException(status_code=404, detail="not found") from exc
        if "Symlinks are not allowed" in detail:
            raise HTTPException(status_code=400, detail="symlink") from exc
        if "Only MKV candidates" in detail:
            raise HTTPException(status_code=400, detail="not an MKV") from exc
        raise HTTPException(status_code=400, detail="invalid path") from exc

    if analysis.get("status") == "unsupported":
        raise HTTPException(status_code=422, detail="analysis failure")

    eligibility = assess_preparation_eligibility(
        payload.relative_path,
        root=location["server_root"],
    )
    analysis["source_location_id"] = location.get("location_id")
    analysis["source_location_name"] = location["display_name"]
    analysis["preparation_eligibility"] = eligibility
    analysis["preparation_proposal"] = (
        propose_preparation_decision(analysis)
        if eligibility["eligible"]
        else {
            "status": "not_eligible",
            "proposed_decision": None,
            "reason": eligibility["reason"],
        }
    )
    return analysis


@router.post("/prepare/plan")
def plan_preparation(payload: PreparationPlanRequest, request: Request):
    try:
        location = _source_location(request, payload.location_id)
        workflow = None
        if payload.workflow_id:
            workflow = request.app.state.operator_store.get_workflow(payload.workflow_id)
            if (
                workflow["source_location_id"] != location["location_id"]
                or workflow["source_relative_path"] != payload.relative_path
            ):
                raise ValueError("Workflow source does not match the preparation source.")
            if not workflow["destination_location_id"]:
                raise ValueError("Select an intended finished destination before preparation.")
            if workflow["preparation_id"]:
                plan = load_preparation_plan(
                    workflow["preparation_id"],
                    work_root=settings.preparation_work_root,
                )
                _validate_workflow_plan(plan, workflow, location, payload.decision)
                return public_preparation_plan(plan)

        if payload.workflow_id:
            preparation_id = _workflow_preparation_id(workflow, payload.decision)
            try:
                plan = load_preparation_plan(
                    preparation_id,
                    work_root=settings.preparation_work_root,
                )
                _validate_workflow_plan(plan, workflow, location, payload.decision)
            except FileNotFoundError:
                try:
                    plan = create_preparation_plan(
                        payload.relative_path,
                        payload.decision,
                        preparation_id=preparation_id,
                        workflow_id=workflow["workflow_id"],
                        source_location_id=location["location_id"],
                        destination_location_id=workflow["destination_location_id"],
                        root=location["server_root"],
                    )
                except FileExistsError:
                    plan = load_preparation_plan(
                        preparation_id,
                        work_root=settings.preparation_work_root,
                    )
                    _validate_workflow_plan(plan, workflow, location, payload.decision)
            request.app.state.operator_store.associate_preparation(
                payload.workflow_id,
                plan["preparation_id"],
            )
        else:
            plan = create_preparation_plan(
                payload.relative_path,
                payload.decision,
                source_location_id=location["location_id"],
                root=location["server_root"],
            )
    except (FileNotFoundError, FileExistsError, ValueError, TypeError) as exc:
        raise _preparation_http_error(exc) from exc
    return public_preparation_plan(plan)


@router.post("/prepare")
def prepare_media(payload: PreparationExecutionRequest):
    try:
        result = execute_preparation(payload.preparation_id)
    except (FileNotFoundError, FileExistsError, ValueError, TypeError) as exc:
        raise _preparation_http_error(exc) from exc
    return result
