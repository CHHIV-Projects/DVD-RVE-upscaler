from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.media_analysis import analyze_candidate
from app.services.media_discovery import discover_candidates, validate_candidate_relative_path
from app.services.media_preparation import (
    assess_preparation_eligibility,
    create_preparation_plan,
    execute_preparation,
    propose_preparation_decision,
    public_preparation_plan,
)

router = APIRouter(prefix="/api/media")


class MediaAnalysisRequest(BaseModel):
    relative_path: str


class PreparationPlanRequest(BaseModel):
    relative_path: str
    decision: Literal["progressive", "deinterlace_tff", "deinterlace_bff"]


class PreparationExecutionRequest(BaseModel):
    preparation_id: str


def _preparation_http_error(exc: Exception) -> HTTPException:
    detail = str(exc)
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=404, detail=detail)
    if isinstance(exc, FileExistsError):
        return HTTPException(status_code=409, detail=detail)
    return HTTPException(status_code=422, detail=detail)


@router.get("/discover")
def discover_media():
    candidates = discover_candidates()
    return {"count": len(candidates), "candidates": candidates}


@router.post("/analyze")
def analyze_media(payload: MediaAnalysisRequest):
    try:
        validate_candidate_relative_path(payload.relative_path)
        analysis = analyze_candidate(payload.relative_path)
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

    eligibility = assess_preparation_eligibility(payload.relative_path)
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
def plan_preparation(payload: PreparationPlanRequest):
    try:
        plan = create_preparation_plan(payload.relative_path, payload.decision)
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
