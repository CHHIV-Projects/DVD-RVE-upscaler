from __future__ import annotations

import json
import math
import re
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any

from app.services.media_discovery import validate_candidate_relative_path


MIN_DETERMINED_FRAMES = 100
PROGRESSIVE_RATIO_THRESHOLD = 0.95
INTERLACED_RATIO_THRESHOLD = 0.90
MAX_CONFLICTING_RATIO = 0.25
REPEATED_FIELD_RATIO_THRESHOLD = 0.10


def _parse_ratio(value: Any) -> float | None:
    if value is None:
        return None

    if isinstance(value, (int, float)):
        if value == 0:
            return None
        return float(value)

    text = str(value).strip()
    if not text or text.lower() in {"unknown", "nan", "n/a", "null"}:
        return None

    if ":" in text:
        try:
            numerator, denominator = text.split(":", 1)
            numerator_fraction = Fraction(str(numerator.strip()))
            denominator_fraction = Fraction(str(denominator.strip()))
            if denominator_fraction == 0:
                return None
            return float(numerator_fraction / denominator_fraction)
        except (TypeError, ValueError, ZeroDivisionError):
            return None

    if "/" in text:
        try:
            numerator, denominator = text.split("/", 1)
            numerator_fraction = Fraction(str(numerator.strip()))
            denominator_fraction = Fraction(str(denominator.strip()))
            if denominator_fraction == 0:
                return None
            return float(numerator_fraction / denominator_fraction)
        except (TypeError, ValueError, ZeroDivisionError):
            return None

    try:
        parsed = float(text)
    except ValueError:
        return None

    return parsed if parsed > 0 else None


def _nearest_even(value: float) -> int:
    return int(math.floor(value / 2.0 + 0.5) * 2)


def compute_square_pixel_geometry(video_stream: dict[str, Any]) -> dict[str, Any]:
    coded_width = int(video_stream.get("width") or 0)
    coded_height = int(video_stream.get("height") or 0)
    sar_ratio = _parse_ratio(video_stream.get("sample_aspect_ratio"))

    if coded_width <= 0 or coded_height <= 0:
        return {
            "status": "review_required",
            "reason": "Missing or invalid coded video dimensions.",
            "coded_width": coded_width,
            "coded_height": coded_height,
        }

    if sar_ratio is None:
        return {
            "status": "review_required",
            "reason": "SAR is missing or invalid; square-pixel geometry cannot be derived safely.",
            "coded_width": coded_width,
            "coded_height": coded_height,
        }

    display_width = round(coded_width * sar_ratio)
    display_height = coded_height
    prepared_width = _nearest_even(display_width)
    prepared_height = _nearest_even(display_height)

    dar_ratio = _parse_ratio(video_stream.get("display_aspect_ratio"))
    ratio_delta = 0.0
    if dar_ratio is not None:
        in_band = display_width / max(display_height, 1)
        ratio_delta = abs(in_band - dar_ratio) / max(max(in_band, dar_ratio), 1e-9)

    geometry_status = "ok"
    geometry_reason = "SAR-derived geometry is consistent with DAR within tolerance."
    if dar_ratio is not None and ratio_delta > 0.02:
        geometry_status = "review_required"
        geometry_reason = "DAR and SAR-derived display ratio differ by more than the v1 tolerance."

    return {
        "status": geometry_status,
        "reason": geometry_reason,
        "coded_width": coded_width,
        "coded_height": coded_height,
        "sar": video_stream.get("sample_aspect_ratio"),
        "dar": video_stream.get("display_aspect_ratio"),
        "display_width": display_width,
        "display_height": display_height,
        "prepared_width": prepared_width,
        "prepared_height": prepared_height,
        "ratio_delta": round(ratio_delta, 4),
    }


def probe_media(source_path: Path) -> dict[str, Any]:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        "-show_chapters",
        str(source_path),
    ]
    try:
        process = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "probe_failed", "error": f"ffprobe could not inspect the media: {exc}"}

    if process.returncode != 0:
        stderr = (process.stderr or "").strip() or "ffprobe exited unsuccessfully."
        return {"status": "probe_failed", "error": stderr}

    try:
        payload = json.loads(process.stdout or "{}")
    except json.JSONDecodeError:
        return {"status": "probe_failed", "error": "ffprobe output was not valid JSON."}

    streams = payload.get("streams", []) or []
    video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
    subtitle_streams = [stream for stream in streams if stream.get("codec_type") == "subtitle"]

    duration = payload.get("format", {}).get("duration")
    if duration is None:
        duration = video_stream.get("duration")

    try:
        duration_value = float(duration) if duration is not None else 0.0
    except (TypeError, ValueError):
        duration_value = 0.0

    audio = [
        {
            "index": stream.get("index"),
            "codec": stream.get("codec_name"),
            "channels": stream.get("channels"),
            "channel_layout": stream.get("channel_layout"),
            "language": stream.get("tags", {}).get("language"),
            "title": stream.get("tags", {}).get("title"),
        }
        for stream in audio_streams
    ]

    subtitles = [
        {
            "index": stream.get("index"),
            "codec": stream.get("codec_name"),
            "language": stream.get("tags", {}).get("language"),
            "title": stream.get("tags", {}).get("title"),
        }
        for stream in subtitle_streams
    ]

    chapter_count = len(payload.get("chapters", []) or [])

    return {
        "status": "ok",
        "relative_source": str(source_path.relative_to(source_path.parents[0])) if source_path.parent else source_path.name,
        "duration_seconds": duration_value,
        "container_name": payload.get("format", {}).get("format_name"),
        "size_bytes": payload.get("format", {}).get("size"),
        "video_stream": {
            "codec": video_stream.get("codec_name"),
            "width": video_stream.get("width"),
            "height": video_stream.get("height"),
            "sample_aspect_ratio": video_stream.get("sample_aspect_ratio"),
            "display_aspect_ratio": video_stream.get("display_aspect_ratio"),
            "pixel_format": video_stream.get("pix_fmt"),
            "field_order": video_stream.get("field_order"),
            "avg_frame_rate": video_stream.get("avg_frame_rate"),
            "r_frame_rate": video_stream.get("r_frame_rate"),
        },
        "audio_streams": audio,
        "subtitle_streams": subtitles,
        "chapter_count": chapter_count,
        "geometry": compute_square_pixel_geometry(video_stream),
    }


def parse_idet_summary(output: str) -> dict[str, int]:
    summary = {
        "tff": 0,
        "bff": 0,
        "progressive": 0,
        "undetermined": 0,
        "single_tff": 0,
        "single_bff": 0,
        "single_progressive": 0,
        "single_undetermined": 0,
        "repeated_neither": 0,
        "repeated_top": 0,
        "repeated_bottom": 0,
    }

    repeated_matches = list(
        re.finditer(
            r"Repeated Fields:\s*Neither:\s*(\d+)\s+Top:\s*(\d+)\s+Bottom:\s*(\d+)",
            output,
            re.IGNORECASE,
        )
    )
    if repeated_matches:
        match = repeated_matches[-1]
        summary["repeated_neither"] = int(match.group(1))
        summary["repeated_top"] = int(match.group(2))
        summary["repeated_bottom"] = int(match.group(3))

    single_matches = list(
        re.finditer(
            r"Single frame detection:\s*TFF:\s*(\d+)\s+BFF:\s*(\d+)\s+Progressive:\s*(\d+)\s+Undetermined:\s*(\d+)",
            output,
            re.IGNORECASE,
        )
    )
    if single_matches:
        single_match = single_matches[-1]
        summary["single_tff"] = int(single_match.group(1))
        summary["single_bff"] = int(single_match.group(2))
        summary["single_progressive"] = int(single_match.group(3))
        summary["single_undetermined"] = int(single_match.group(4))

    multi_matches = list(
        re.finditer(
            r"Multi frame detection:\s*TFF:\s*(\d+)\s+BFF:\s*(\d+)\s+Progressive:\s*(\d+)\s+Undetermined:\s*(\d+)",
            output,
            re.IGNORECASE,
        )
    )
    if multi_matches:
        multi_match = multi_matches[-1]
        summary["tff"] = int(multi_match.group(1))
        summary["bff"] = int(multi_match.group(2))
        summary["progressive"] = int(multi_match.group(3))
        summary["undetermined"] = int(multi_match.group(4))

    return summary


def _parse_idet_count(output: str, key: str) -> int:
    pattern = re.compile(rf"{re.escape(key)}\s*:\s*(\d+)", re.IGNORECASE)
    match = pattern.search(output)
    if match:
        return int(match.group(1))
    return 0


def run_idet_sample(source_path: Path, sample_time: float, frames_per_sample: int = 1000) -> dict[str, Any]:
    cmd = [
        "ffmpeg",
        "-v",
        "info",
        "-nostdin",
        "-ss",
        str(sample_time),
        "-i",
        str(source_path),
        "-map",
        "0:v:0",
        "-vf",
        "idet",
        "-frames:v",
        str(frames_per_sample),
        "-an",
        "-sn",
        "-dn",
        "-f",
        "null",
        "-",
    ]

    try:
        process = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=90)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "sample_time": round(sample_time, 2),
            "status": "failed",
            "error": f"idet sample failed: {exc}",
        }

    stderr = (process.stderr or "") + "\n" + (process.stdout or "")
    parsed = parse_idet_summary(stderr)
    tff = parsed["tff"]
    bff = parsed["bff"]
    progressive = parsed["progressive"]
    undetermined = parsed["undetermined"]
    repeated_top = parsed["repeated_top"]
    repeated_bottom = parsed["repeated_bottom"]
    repeated_neither = parsed["repeated_neither"]

    total_determined = tff + bff + progressive
    progressive_ratio = (progressive / total_determined) if total_determined else 0.0
    tff_ratio = (tff / total_determined) if total_determined else 0.0
    bff_ratio = (bff / total_determined) if total_determined else 0.0
    repeated_total = repeated_neither + repeated_top + repeated_bottom
    repeated_field_ratio = ((repeated_top + repeated_bottom) / repeated_total) if repeated_total else 0.0

    status = "usable"
    if process.returncode != 0:
        status = "failed"
    elif total_determined < MIN_DETERMINED_FRAMES:
        status = "insufficient"

    return {
        "sample_time": round(sample_time, 2),
        "status": status,
        "returncode": process.returncode,
        "tff": tff,
        "bff": bff,
        "progressive": progressive,
        "undetermined": undetermined,
        "single_tff": parsed["single_tff"],
        "single_bff": parsed["single_bff"],
        "single_progressive": parsed["single_progressive"],
        "single_undetermined": parsed["single_undetermined"],
        "repeated_neither": repeated_neither,
        "repeated_top": repeated_top,
        "repeated_bottom": repeated_bottom,
        "total_determined": total_determined,
        "progressive_ratio": round(progressive_ratio, 4),
        "tff_ratio": round(tff_ratio, 4),
        "bff_ratio": round(bff_ratio, 4),
        "repeated_field_ratio": round(repeated_field_ratio, 4),
        "stderr_preview": stderr[-500:] if stderr else "",
    }


def _classify_samples(samples: list[dict[str, Any]]) -> dict[str, Any]:
    usable = [sample for sample in samples if sample.get("status") == "usable"]
    if not usable:
        return {
            "content_classification": "unsupported",
            "final_classification": "unsupported",
            "classification_reasons": ["No usable idet sample data was available."],
        }

    sample_progressive = [sample["progressive_ratio"] for sample in usable]
    sample_tff = [sample["tff_ratio"] for sample in usable]
    sample_bff = [sample["bff_ratio"] for sample in usable]
    repeated_signal = any(sample["repeated_field_ratio"] > REPEATED_FIELD_RATIO_THRESHOLD for sample in usable)

    if repeated_signal:
        classification = "telecine_suspected"
        reasons = ["Repeated-field or cadence-like evidence suggests telecine or cadence-sensitive content."]
    elif (
        all(r >= PROGRESSIVE_RATIO_THRESHOLD for r in sample_progressive)
        and all(t < MAX_CONFLICTING_RATIO for t in sample_tff)
        and all(b < MAX_CONFLICTING_RATIO for b in sample_bff)
    ):
        classification = "progressive"
        reasons = ["Distributed samples consistently show strong progressive evidence."]
    elif (
        all(r >= INTERLACED_RATIO_THRESHOLD for r in sample_tff)
        and all(p < MAX_CONFLICTING_RATIO for p in sample_progressive)
        and all(b < MAX_CONFLICTING_RATIO for b in sample_bff)
    ):
        classification = "interlaced_tff"
        reasons = ["Distributed samples consistently show strong TFF evidence."]
    elif (
        all(r >= INTERLACED_RATIO_THRESHOLD for r in sample_bff)
        and all(p < MAX_CONFLICTING_RATIO for p in sample_progressive)
        and all(t < MAX_CONFLICTING_RATIO for t in sample_tff)
    ):
        classification = "interlaced_bff"
        reasons = ["Distributed samples consistently show strong BFF evidence."]
    else:
        classification = "ambiguous"
        reasons = ["The distributed evidence is materially mixed or insufficient for a safe automatic decision."]

    return {
        "content_classification": classification,
        "classification_reasons": reasons,
    }


def _metadata_conflicts_with_content(field_order: Any, content_classification: str) -> bool:
    normalized = str(field_order or "").strip().lower()
    if normalized in {"", "unknown", "unspecified"}:
        return False

    interlaced_orders = {"tt", "bb", "tb", "bt"}
    if content_classification == "progressive":
        return normalized in interlaced_orders
    if content_classification == "interlaced_tff":
        return normalized == "progressive" or normalized.startswith("b")
    if content_classification == "interlaced_bff":
        return normalized == "progressive" or normalized.startswith("t")
    return False


def analyze_candidate(
    relative_path: str | None,
    *,
    root: str | Path | None = None,
) -> dict[str, Any]:
    source_path = (
        validate_candidate_relative_path(relative_path, root=root)
        if root is not None
        else validate_candidate_relative_path(relative_path)
    )
    probe_result = probe_media(source_path)
    if probe_result.get("status") != "ok":
        return {
            "status": "unsupported",
            "relative_source": relative_path,
            "classification": "unsupported",
            "reasons": [probe_result.get("error", "ffprobe could not inspect the file.")],
        }

    duration = float(probe_result.get("duration_seconds") or 0.0)
    if duration <= 0:
        return {
            "status": "unsupported",
            "relative_source": relative_path,
            "classification": "unsupported",
            "reasons": ["Duration was missing or invalid; idet sampling cannot be safely planned."],
        }

    sample_positions = [duration * 0.20, duration * 0.50, duration * 0.80]
    samples = [run_idet_sample(source_path, max(0.0, min(duration, position)), frames_per_sample=1000) for position in sample_positions]
    sample_summary = _classify_samples(samples)

    geometry = probe_result.get("geometry", {})
    final_classification = sample_summary["content_classification"]
    reasons = list(sample_summary["classification_reasons"])

    if geometry.get("status") == "review_required":
        final_classification = "ambiguous"
        reasons.append(geometry.get("reason", "Geometry evidence is inconsistent and requires review."))

    video_stream = probe_result.get("video_stream", {})
    metadata_field_order = video_stream.get("field_order")
    if _metadata_conflicts_with_content(metadata_field_order, sample_summary["content_classification"]):
        final_classification = "ambiguous"
        reasons.append(
            f"Metadata field_order {metadata_field_order!r} materially conflicts with "
            f"content classification {sample_summary['content_classification']!r}; review is required."
        )
    if metadata_field_order:
        reasons.append(f"Metadata field_order: {metadata_field_order}.")

    return {
        "status": "ok",
        "relative_source": relative_path,
        "duration_seconds": duration,
        "container_name": probe_result.get("container_name"),
        "size_bytes": probe_result.get("size_bytes"),
        "video_stream": video_stream,
        "audio_streams": probe_result.get("audio_streams", []),
        "subtitle_streams": probe_result.get("subtitle_streams", []),
        "chapter_count": probe_result.get("chapter_count", 0),
        "geometry": geometry,
        "idet_samples": samples,
        "metadata_field_order": metadata_field_order,
        "content_classification": sample_summary["content_classification"],
        "final_classification": final_classification,
        "classification_reasons": reasons,
        "analysis_status": "review_required" if final_classification == "ambiguous" else "ok",
    }
