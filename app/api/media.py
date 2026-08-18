from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.media_analysis import analyze_candidate
from app.services.media_discovery import discover_candidates, validate_candidate_relative_path

router = APIRouter(prefix="/api/media")


class MediaAnalysisRequest(BaseModel):
    relative_path: str


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

    return analysis
