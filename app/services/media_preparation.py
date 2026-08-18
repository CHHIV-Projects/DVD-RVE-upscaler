from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import uuid
from fractions import Fraction
from pathlib import Path
from typing import Any

from app.config import settings
from app.services.media_analysis import analyze_candidate, probe_media
from app.services.media_discovery import get_approved_root, validate_candidate_relative_path

PREPARATION_DECISIONS = {"progressive", "deinterlace_tff", "deinterlace_bff"}
ANALYSIS_PROPOSALS = {
    "progressive": "progressive",
    "interlaced_tff": "deinterlace_tff",
    "interlaced_bff": "deinterlace_bff",
}
NETWORK_FILESYSTEMS = {"cifs", "nfs", "nfs4", "smb3", "sshfs", "fuse.sshfs"}
PREPARATION_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
ENHANCEMENT_MARKERS = (
    ("RVE", re.compile(r"(?<![a-z0-9])rve(?![a-z0-9])", re.IGNORECASE)),
    ("Nomos", re.compile(r"(?<![a-z0-9])nomos(?:8k)?(?![a-z0-9])", re.IGNORECASE)),
    ("Medium 2x", re.compile(r"(?<![a-z0-9])medium[\s._-]+2x(?![a-z0-9])", re.IGNORECASE)),
)


def _find_mount_value(path: Path, column: str) -> str | None:
    try:
        process = subprocess.run(
            ["findmnt", "-n", "-T", str(path), "-o", column],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if process.returncode != 0:
        return None
    value = (process.stdout or "").strip()
    return value or None


def source_mount_is_read_only(source_path: Path) -> bool:
    options = _find_mount_value(source_path, "OPTIONS")
    if options is None:
        return False
    return "ro" in {option.strip().lower() for option in options.split(",")}


def work_root_is_local(work_root: Path) -> bool:
    probe_path = work_root
    while not probe_path.exists() and probe_path != probe_path.parent:
        probe_path = probe_path.parent
    filesystem = _find_mount_value(probe_path, "FSTYPE")
    return filesystem is not None and filesystem.lower() not in NETWORK_FILESYSTEMS


def _enhancement_marker(filename: str) -> str | None:
    stem = Path(filename).stem
    for label, pattern in ENHANCEMENT_MARKERS:
        if pattern.search(stem):
            return label
    return None


def assess_preparation_eligibility(
    relative_path: str | None,
    *,
    root: str | Path | None = None,
    verify_read_only_mount: bool = True,
) -> dict[str, Any]:
    try:
        source_path = validate_candidate_relative_path(relative_path, root=root)
    except (FileNotFoundError, ValueError, TypeError) as exc:
        return {"eligible": False, "status": "not_eligible", "reason": str(exc)}

    if not os.access(source_path, os.R_OK):
        return {
            "eligible": False,
            "status": "not_eligible",
            "reason": "The selected source is not readable.",
        }

    marker = _enhancement_marker(source_path.name)
    if marker:
        return {
            "eligible": False,
            "status": "not_eligible",
            "reason": f"Source appears to be an existing enhanced/RVE-derived version ({marker} marker).",
            "matched_marker": marker,
        }

    if verify_read_only_mount and not source_mount_is_read_only(source_path):
        return {
            "eligible": False,
            "status": "not_eligible",
            "reason": "The approved source mount is not verified read-only.",
        }

    return {
        "eligible": True,
        "status": "eligible",
        "reason": "Source satisfies the preparation eligibility boundary.",
        "relative_path": str(relative_path),
    }


def propose_preparation_decision(analysis: dict[str, Any]) -> dict[str, Any]:
    final_classification = analysis.get("final_classification")
    analysis_status = analysis.get("analysis_status")
    if final_classification == "ambiguous" or analysis_status == "review_required":
        return {
            "status": "review_required",
            "proposed_decision": None,
            "reason": "Analysis requires an explicit Product Owner preparation decision.",
        }

    proposed = ANALYSIS_PROPOSALS.get(str(final_classification))
    if proposed is None:
        return {
            "status": "blocked",
            "proposed_decision": None,
            "reason": f"Analysis classification {final_classification!r} is not executable.",
        }

    return {
        "status": "proposed",
        "proposed_decision": proposed,
        "reason": f"Final analysis classification maps to {proposed}.",
    }


def validate_preparation_decision(analysis: dict[str, Any], decision: str) -> dict[str, Any]:
    if decision not in PREPARATION_DECISIONS:
        raise ValueError("Invalid preparation decision.")

    proposal = propose_preparation_decision(analysis)
    if proposal["status"] == "blocked":
        raise ValueError(proposal["reason"])
    if proposal["status"] == "proposed" and decision != proposal["proposed_decision"]:
        raise ValueError("The selected decision conflicts with the unambiguous analysis result.")

    return {
        "decision": decision,
        "explicit_override": proposal["status"] == "review_required",
        "proposal": proposal,
    }


def build_video_filter(decision: str, width: int, height: int) -> str:
    if width <= 0 or height <= 0 or width % 2 or height % 2:
        raise ValueError("Prepared geometry must contain positive even dimensions.")

    base = f"scale={width}:{height},setsar=1,setfield=prog"
    if decision == "progressive":
        return base
    if decision == "deinterlace_tff":
        return f"bwdif=mode=send_frame:parity=tff:deint=all,{base}"
    if decision == "deinterlace_bff":
        return f"bwdif=mode=send_frame:parity=bff:deint=all,{base}"
    raise ValueError("Invalid preparation decision.")


def _resolve_work_root(work_root: str | Path | None = None) -> Path:
    resolved = Path(work_root or settings.preparation_work_root).expanduser().resolve()
    source_root = get_approved_root()
    if resolved == source_root or source_root in resolved.parents or resolved in source_root.parents:
        raise ValueError("Preparation work root must be separate from the NAS source tree.")
    return resolved


def _required_free_bytes(source_size: int) -> int:
    return max(
        int(settings.preparation_min_free_bytes),
        source_size * int(settings.preparation_source_size_multiplier),
    )


def check_available_space(work_root: Path, source_size: int) -> dict[str, Any]:
    probe_path = work_root
    while not probe_path.exists() and probe_path != probe_path.parent:
        probe_path = probe_path.parent
    available = shutil.disk_usage(probe_path).free
    required = _required_free_bytes(source_size)
    return {
        "sufficient": available >= required,
        "available_bytes": available,
        "required_bytes": required,
        "rule": "available >= max(10 GiB, 2 x source file size)",
    }


def build_ffmpeg_command(plan: dict[str, Any]) -> list[str]:
    return [
        "ffmpeg",
        "-v",
        "info",
        "-nostdin",
        "-n",
        "-i",
        plan["source_absolute_path"],
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-map",
        "0:s?",
        "-map",
        "0:t?",
        "-map_metadata",
        "0",
        "-map_chapters",
        "0",
        "-vf",
        plan["video_filter"],
        "-c:v",
        "h264_nvenc",
        "-preset",
        "p7",
        "-rc",
        "vbr",
        "-cq",
        "16",
        "-b:v",
        "0",
        "-pix_fmt",
        "yuv420p",
        "-fps_mode",
        "passthrough",
        "-c:a",
        "copy",
        "-c:s",
        "copy",
        "-c:t",
        "copy",
        plan["temporary_output_path"],
    ]


def create_preparation_plan(
    relative_path: str,
    decision: str,
    *,
    analysis: dict[str, Any] | None = None,
    preparation_id: str | None = None,
    workflow_id: str | None = None,
    source_location_id: str | None = None,
    destination_location_id: str | None = None,
    root: str | Path | None = None,
    work_root: str | Path | None = None,
    verify_runtime: bool = True,
) -> dict[str, Any]:
    eligibility = assess_preparation_eligibility(
        relative_path,
        root=root,
        verify_read_only_mount=verify_runtime,
    )
    if not eligibility["eligible"]:
        raise ValueError(eligibility["reason"])

    source_path = validate_candidate_relative_path(relative_path, root=root)
    analysis_result = (
        analysis
        if analysis is not None
        else analyze_candidate(relative_path, root=root)
    )
    if analysis_result.get("status") != "ok":
        raise ValueError("Source analysis is not usable for preparation.")

    decision_result = validate_preparation_decision(analysis_result, decision)
    geometry = analysis_result.get("geometry", {})
    if geometry.get("status") != "ok":
        raise ValueError("Prepared geometry is not safely executable.")

    prepared_width = int(geometry.get("prepared_width") or 0)
    prepared_height = int(geometry.get("prepared_height") or 0)
    video_filter = build_video_filter(decision, prepared_width, prepared_height)

    resolved_work_root = _resolve_work_root(work_root)
    if verify_runtime and not work_root_is_local(resolved_work_root):
        raise ValueError("Preparation work root is not verified server-local storage.")

    source_stat = source_path.stat()
    space = check_available_space(resolved_work_root, source_stat.st_size)
    if not space["sufficient"]:
        raise ValueError("Insufficient local free space for the preparation artifact.")

    preparation_id = preparation_id or uuid.uuid4().hex
    if not PREPARATION_ID_PATTERN.fullmatch(preparation_id):
        raise ValueError("Invalid preparation identifier.")
    preparation_directory = resolved_work_root / preparation_id
    resolved_work_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    preparation_directory.mkdir(mode=0o700, exist_ok=False)

    temporary_output = preparation_directory / "prepared.partial.mkv"
    final_output = preparation_directory / "prepared.mkv"
    plan_path = preparation_directory / "plan.json"
    plan = {
        "preparation_id": preparation_id,
        "workflow_id": workflow_id,
        "source_location_id": source_location_id,
        "destination_location_id": destination_location_id,
        "source_root": str(Path(root or settings.dvd_source_root).expanduser().resolve()),
        "source_relative_path": relative_path,
        "source_absolute_path": str(source_path),
        "source_size_bytes": source_stat.st_size,
        "source_mtime_ns": source_stat.st_mtime_ns,
        "source_analysis_classification": {
            "content": analysis_result.get("content_classification"),
            "final": analysis_result.get("final_classification"),
            "status": analysis_result.get("analysis_status"),
        },
        "source_analysis_review_reasons": analysis_result.get("classification_reasons", []),
        "selected_preparation_decision": decision_result["decision"],
        "explicit_override": decision_result["explicit_override"],
        "source_geometry": geometry,
        "target_prepared_geometry": {
            "width": prepared_width,
            "height": prepared_height,
            "sample_aspect_ratio": "1:1",
            "field_order": "progressive",
        },
        "video_filter": video_filter,
        "video_encoder": "h264_nvenc",
        "encoder_settings": {
            "preset": "p7",
            "rate_control": "vbr",
            "constant_quality": 16,
            "video_bitrate": 0,
        },
        "pixel_format": "yuv420p",
        "frame_rate": (
            analysis_result.get("video_stream", {}).get("avg_frame_rate")
            or analysis_result.get("video_stream", {}).get("r_frame_rate")
        ),
        "source_duration_seconds": analysis_result.get("duration_seconds"),
        "source_audio_streams": analysis_result.get("audio_streams", []),
        "source_subtitle_streams": analysis_result.get("subtitle_streams", []),
        "source_chapter_count": int(analysis_result.get("chapter_count") or 0),
        "audio_policy": "copy",
        "subtitle_policy": "copy",
        "chapter_policy": "preserve",
        "metadata_policy": "preserve",
        "working_directory": str(preparation_directory),
        "temporary_output_path": str(temporary_output),
        "final_prepared_output_path": str(final_output),
        "free_space_check": space,
        "timeout_seconds": int(settings.preparation_timeout_seconds),
    }
    plan["ffmpeg_arguments"] = build_ffmpeg_command(plan)

    with plan_path.open("x", encoding="utf-8") as plan_file:
        json.dump(plan, plan_file, indent=2)
        plan_file.write("\n")
    plan_path.chmod(0o600)
    return plan


def public_preparation_plan(plan: dict[str, Any]) -> dict[str, Any]:
    internal_fields = {
        "source_absolute_path",
        "source_root",
        "source_mtime_ns",
        "ffmpeg_arguments",
        "temporary_output_path",
    }
    public = {key: value for key, value in plan.items() if key not in internal_fields}
    public.update(preparation_execution_state(plan))
    return public


def preparation_execution_state(plan: dict[str, Any]) -> dict[str, Any]:
    temporary_value = plan.get("temporary_output_path")
    final_value = plan.get("final_prepared_output_path")
    directory = Path(
        plan.get("working_directory")
        or (Path(final_value).parent if final_value else Path(temporary_value).parent)
    )
    final_output = Path(final_value or directory / "prepared.mkv")
    partial_output = Path(
        temporary_value or directory / "prepared.partial.mkv"
    )
    execution_started = (directory / "execution.started").is_file()
    if final_output.is_file():
        status = "completed"
    elif execution_started:
        status = "output_missing"
    elif partial_output.exists():
        status = "unexpected_partial_output"
    else:
        status = "plan_ready"
    return {
        "preparation_status": status,
        "ready_to_prepare": status == "plan_ready",
    }


def _validated_preparation_directory(preparation_id: str, work_root: Path) -> Path:
    if not PREPARATION_ID_PATTERN.fullmatch(preparation_id):
        raise ValueError("Invalid preparation identifier.")
    preparation_directory = (work_root / preparation_id).resolve()
    try:
        preparation_directory.relative_to(work_root)
    except ValueError as exc:
        raise ValueError("Preparation identifier escapes the work root.") from exc
    return preparation_directory


def load_preparation_plan(
    preparation_id: str,
    *,
    work_root: str | Path | None = None,
) -> dict[str, Any]:
    resolved_work_root = _resolve_work_root(work_root)
    preparation_directory = _validated_preparation_directory(preparation_id, resolved_work_root)
    plan_path = preparation_directory / "plan.json"
    if not plan_path.is_file():
        raise FileNotFoundError("Preparation plan was not found.")
    with plan_path.open(encoding="utf-8") as plan_file:
        plan = json.load(plan_file)
    if plan.get("preparation_id") != preparation_id:
        raise ValueError("Preparation plan identifier does not match its directory.")
    return plan


def _ratio(value: Any) -> float | None:
    text = str(value or "").strip()
    separator = ":" if ":" in text else "/" if "/" in text else None
    try:
        if separator:
            numerator, denominator = text.split(separator, 1)
            if Fraction(denominator) == 0:
                return None
            return float(Fraction(numerator) / Fraction(denominator))
        parsed = float(text)
        return parsed if parsed > 0 else None
    except (ValueError, ZeroDivisionError):
        return None


def validate_prepared_output(output_path: Path, plan: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def record(name: str, passed: bool, expected: Any, actual: Any, *, warning: bool = False) -> None:
        checks.append(
            {
                "name": name,
                "outcome": "PASS" if passed else ("WARNING / REVIEW REQUIRED" if warning else "FAIL"),
                "expected": expected,
                "actual": actual,
            }
        )

    if not output_path.is_file():
        record("file_exists", False, True, False)
        return {"outcome": "FAIL", "checks": checks, "reasons": ["Prepared output file is missing."]}
    record("file_exists", True, True, True)
    non_zero = output_path.stat().st_size > 0
    record("file_non_zero", non_zero, "> 0 bytes", output_path.stat().st_size)
    if not non_zero:
        return {"outcome": "FAIL", "checks": checks, "reasons": ["Prepared output file is empty."]}

    probe = probe_media(output_path)
    probe_ok = probe.get("status") == "ok"
    record("ffprobe_readable", probe_ok, "ok", probe.get("status"))
    if not probe_ok:
        return {
            "outcome": "FAIL",
            "checks": checks,
            "reasons": [probe.get("error", "Prepared output is not ffprobe-readable.")],
        }

    video = probe.get("video_stream", {})
    target = plan["target_prepared_geometry"]
    record("video_codec", video.get("codec") == "h264", "h264", video.get("codec"))
    record("video_width", video.get("width") == target["width"], target["width"], video.get("width"))
    record("video_height", video.get("height") == target["height"], target["height"], video.get("height"))
    sar = _ratio(video.get("sample_aspect_ratio"))
    record("square_pixel_sar", sar is not None and abs(sar - 1.0) < 0.0001, "1:1", video.get("sample_aspect_ratio"))
    record("progressive_field_order", video.get("field_order") == "progressive", "progressive", video.get("field_order"))
    record("pixel_format", video.get("pixel_format") == plan["pixel_format"], plan["pixel_format"], video.get("pixel_format"))

    expected_rate = _ratio(plan.get("frame_rate"))
    actual_rate = _ratio(video.get("avg_frame_rate") or video.get("r_frame_rate"))
    rate_matches = (
        expected_rate is not None
        and actual_rate is not None
        and abs(actual_rate - expected_rate) / expected_rate <= 0.001
    )
    record("frame_rate", rate_matches, plan.get("frame_rate"), video.get("avg_frame_rate") or video.get("r_frame_rate"))

    source_duration = float(plan.get("source_duration_seconds") or 0.0)
    output_duration = float(probe.get("duration_seconds") or 0.0)
    duration_tolerance = max(0.5, source_duration * 0.005)
    duration_matches = source_duration > 0 and abs(output_duration - source_duration) <= duration_tolerance
    record(
        "duration",
        duration_matches,
        f"{source_duration}s +/- {duration_tolerance}s",
        output_duration,
    )

    source_audio = plan.get("source_audio_streams", [])
    output_audio = probe.get("audio_streams", [])
    record("audio_stream_count", len(output_audio) == len(source_audio), len(source_audio), len(output_audio))
    if len(output_audio) == len(source_audio):
        for index, (expected, actual) in enumerate(zip(source_audio, output_audio, strict=True)):
            for field in ("codec", "channels", "language"):
                expected_value = expected.get(field)
                if expected_value is not None:
                    record(
                        f"audio_{index}_{field}",
                        actual.get(field) == expected_value,
                        expected_value,
                        actual.get(field),
                        warning=True,
                    )

    source_subtitles = plan.get("source_subtitle_streams", [])
    output_subtitles = probe.get("subtitle_streams", [])
    record(
        "subtitle_stream_count",
        len(output_subtitles) == len(source_subtitles),
        len(source_subtitles),
        len(output_subtitles),
    )
    if len(output_subtitles) == len(source_subtitles):
        for index, (expected, actual) in enumerate(zip(source_subtitles, output_subtitles, strict=True)):
            for field in ("codec", "language"):
                expected_value = expected.get(field)
                if expected_value is not None:
                    record(
                        f"subtitle_{index}_{field}",
                        actual.get(field) == expected_value,
                        expected_value,
                        actual.get(field),
                        warning=True,
                    )

    source_chapters = int(plan.get("source_chapter_count") or 0)
    record("chapter_count", probe.get("chapter_count") == source_chapters, source_chapters, probe.get("chapter_count"))

    failed = [check["name"] for check in checks if check["outcome"] == "FAIL"]
    warnings = [check["name"] for check in checks if check["outcome"] == "WARNING / REVIEW REQUIRED"]
    if failed:
        outcome = "FAIL"
        reasons = [f"Required validation checks failed: {', '.join(failed)}."]
    elif warnings:
        outcome = "WARNING / REVIEW REQUIRED"
        reasons = [f"Non-destructive discrepancies require review: {', '.join(warnings)}."]
    else:
        outcome = "PASS"
        reasons = ["All required preparation validation checks passed."]
    return {"outcome": outcome, "checks": checks, "reasons": reasons, "probe": probe}


def promote_validated_output(partial_path: Path, final_path: Path) -> None:
    if final_path.exists():
        raise FileExistsError("Final prepared output already exists.")
    os.link(partial_path, final_path)
    partial_path.unlink()


def acquire_execution_marker(preparation_directory: Path) -> Path:
    marker_path = preparation_directory / "execution.started"
    try:
        descriptor = os.open(marker_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise FileExistsError("Preparation execution has already started for this plan.") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as marker:
        marker.write("started\n")
    return marker_path


def execute_preparation(
    preparation_id: str,
    *,
    work_root: str | Path | None = None,
    verify_runtime: bool = True,
) -> dict[str, Any]:
    resolved_work_root = _resolve_work_root(work_root)
    plan = load_preparation_plan(preparation_id, work_root=resolved_work_root)
    source_root = plan.get("source_root") or settings.dvd_source_root
    decision = str(plan.get("selected_preparation_decision"))
    target = plan.get("target_prepared_geometry", {})
    expected_filter = build_video_filter(
        decision,
        int(target.get("width") or 0),
        int(target.get("height") or 0),
    )
    if plan.get("video_filter") != expected_filter:
        raise ValueError("Stored preparation filter does not match the approved decision and geometry.")
    if plan.get("video_encoder") != "h264_nvenc" or plan.get("pixel_format") != "yuv420p":
        raise ValueError("Stored preparation encoder settings do not match the approved NVENC baseline.")

    eligibility = assess_preparation_eligibility(
        plan["source_relative_path"],
        root=source_root,
        verify_read_only_mount=verify_runtime,
    )
    if not eligibility["eligible"]:
        raise ValueError(eligibility["reason"])
    if verify_runtime and not work_root_is_local(resolved_work_root):
        raise ValueError("Preparation work root is not verified server-local storage.")

    source_path = validate_candidate_relative_path(
        plan["source_relative_path"],
        root=source_root,
    )
    source_stat = source_path.stat()
    if (
        source_stat.st_size != plan.get("source_size_bytes")
        or source_stat.st_mtime_ns != plan.get("source_mtime_ns")
    ):
        raise ValueError("Source changed after the preparation plan was created.")

    space = check_available_space(resolved_work_root, source_stat.st_size)
    if not space["sufficient"]:
        raise ValueError("Insufficient local free space for the preparation artifact.")

    preparation_directory = _validated_preparation_directory(preparation_id, resolved_work_root)
    partial_path = preparation_directory / "prepared.partial.mkv"
    final_path = preparation_directory / "prepared.mkv"
    acquire_execution_marker(preparation_directory)
    if partial_path.exists() or final_path.exists():
        raise FileExistsError("Preparation output already exists; overwrite is not allowed.")

    plan["source_absolute_path"] = str(source_path)
    plan["temporary_output_path"] = str(partial_path)
    command = build_ffmpeg_command(plan)
    try:
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=int(plan["timeout_seconds"]),
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "failed",
            "preparation_id": preparation_id,
            "reason": f"FFmpeg exceeded the bounded {plan['timeout_seconds']}-second timeout: {exc}",
            "promoted": False,
        }
    except OSError as exc:
        return {
            "status": "failed",
            "preparation_id": preparation_id,
            "reason": f"FFmpeg could not be started: {exc}",
            "promoted": False,
        }

    if process.returncode != 0:
        return {
            "status": "failed",
            "preparation_id": preparation_id,
            "reason": "FFmpeg preparation exited unsuccessfully.",
            "ffmpeg_returncode": process.returncode,
            "stderr_preview": (process.stderr or "")[-1000:],
            "promoted": False,
        }

    validation = validate_prepared_output(partial_path, plan)
    if validation["outcome"] != "PASS":
        return {
            "status": "review_required" if validation["outcome"] == "WARNING / REVIEW REQUIRED" else "failed",
            "preparation_id": preparation_id,
            "validation": validation,
            "promoted": False,
            "partial_artifact": str(partial_path) if partial_path.exists() else None,
        }

    try:
        promote_validated_output(partial_path, final_path)
    except OSError as exc:
        return {
            "status": "failed",
            "preparation_id": preparation_id,
            "reason": f"Validated output could not be safely promoted: {exc}",
            "validation": validation,
            "promoted": False,
            "partial_artifact": str(partial_path) if partial_path.exists() else None,
        }
    return {
        "status": "completed",
        "preparation_id": preparation_id,
        "selected_preparation_decision": plan["selected_preparation_decision"],
        "prepared_geometry": plan["target_prepared_geometry"],
        "video_encoder": plan["video_encoder"],
        "pixel_format": plan["pixel_format"],
        "frame_rate": plan["frame_rate"],
        "stream_preservation": {
            "audio": plan["audio_policy"],
            "subtitles": plan["subtitle_policy"],
            "chapters": plan["chapter_policy"],
            "metadata": plan["metadata_policy"],
        },
        "validation": validation,
        "promoted": True,
        "prepared_artifact": str(final_path),
    }
