from __future__ import annotations

import ctypes
import errno
import json
import os
import re
import shutil
import sqlite3
import subprocess
import uuid
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable

from app.config import settings
from app.services.media_analysis import probe_media
from app.services.media_discovery import validate_candidate_relative_path
from app.services.media_preparation import (
    NETWORK_FILESYSTEMS,
    assess_preparation_eligibility,
    load_preparation_plan,
    promote_validated_output,
    validate_prepared_output,
    work_root_is_local,
)
from app.services.rve_jobs import JOB_ID_PATTERN, locked_profile, validate_rve_output

OUTPUT_SUFFIX = "DVD RVE Nomos8k Medium 2x"
FINALIZATION_STATES = {
    "created",
    "finalizing",
    "finalized",
    "publishing",
    "published",
    "failed",
}
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}
UNSAFE_TITLE_PATTERN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def validate_movie_title(value: str) -> str:
    title = str(value or "").strip()
    if not title or title in {".", ".."}:
        raise ValueError("Movie title must be a non-empty filename component.")
    if UNSAFE_TITLE_PATTERN.search(title):
        raise ValueError("Movie title contains an unsafe filename character or path separator.")
    if title.endswith((".", " ")):
        raise ValueError("Movie title may not end with a dot or space.")
    if title.upper() in WINDOWS_RESERVED_NAMES:
        raise ValueError("Movie title is a reserved filename.")
    filename = f"{title} - {OUTPUT_SUFFIX}.mkv"
    if len(filename.encode("utf-8")) > 240:
        raise ValueError("Generated movie filename is too long.")
    return title


def generated_filename(movie_title: str) -> str:
    return f"{validate_movie_title(movie_title)} - {OUTPUT_SUFFIX}.mkv"


def suggest_movie_title(source_relative_path: str) -> str:
    source = Path(str(source_relative_path or ""))
    stem = source.stem.strip()
    recognized = re.fullmatch(r"(.+?)\s+-\s+DVD Original", stem, flags=re.IGNORECASE)
    if recognized:
        return validate_movie_title(recognized.group(1))
    if source.parent != Path(".") and source.parent.name.strip():
        return validate_movie_title(source.parent.name)
    return validate_movie_title(stem)


def build_final_remux_command(input_path: Path, output_path: Path) -> list[str]:
    return [
        "ffmpeg",
        "-v",
        "info",
        "-nostdin",
        "-n",
        "-i",
        str(input_path),
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
        "-c",
        "copy",
        str(output_path),
    ]


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


def validate_final_output(
    output_path: Path,
    expected: dict[str, Any],
    *,
    expected_size: int | None = None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def record(name: str, passed: bool, wanted: Any, actual: Any) -> None:
        checks.append(
            {
                "name": name,
                "outcome": "PASS" if passed else "FAIL",
                "expected": wanted,
                "actual": actual,
            }
        )

    exists = output_path.is_file() and not output_path.is_symlink()
    record("file_exists", exists, True, exists)
    if not exists:
        return {"outcome": "FAIL", "checks": checks, "reasons": ["Final MKV is missing."]}
    size = output_path.stat().st_size
    record("file_non_zero", size > 0, "> 0 bytes", size)
    if expected_size is not None:
        record("file_size", size == expected_size, expected_size, size)
    if size <= 0:
        return {"outcome": "FAIL", "checks": checks, "reasons": ["Final MKV is empty."]}

    probe = probe_media(output_path)
    probe_ok = probe.get("status") == "ok"
    record("ffprobe_readable", probe_ok, "ok", probe.get("status"))
    if not probe_ok:
        return {
            "outcome": "FAIL",
            "checks": checks,
            "reasons": [probe.get("error", "Final MKV is not ffprobe-readable.")],
        }

    video = probe.get("video_stream", {})
    expected_video = expected["video_stream"]
    record("video_stream", bool(video), "present", "present" if video else "missing")
    for field in ("codec", "width", "height", "pixel_format", "field_order"):
        record(
            f"video_{field}",
            video.get(field) == expected_video.get(field),
            expected_video.get(field),
            video.get(field),
        )
    expected_sar = _ratio(expected_video.get("sample_aspect_ratio"))
    actual_sar = _ratio(video.get("sample_aspect_ratio"))
    record(
        "sample_aspect_ratio",
        expected_sar is not None
        and actual_sar is not None
        and abs(expected_sar - actual_sar) < 0.0001,
        expected_video.get("sample_aspect_ratio"),
        video.get("sample_aspect_ratio"),
    )
    expected_rate_text = expected_video.get("avg_frame_rate") or expected_video.get("r_frame_rate")
    actual_rate_text = video.get("avg_frame_rate") or video.get("r_frame_rate")
    expected_rate = _ratio(expected_rate_text)
    actual_rate = _ratio(actual_rate_text)
    record(
        "frame_rate",
        expected_rate is not None
        and expected_rate > 0
        and actual_rate is not None
        and abs(actual_rate - expected_rate) / expected_rate <= 0.001,
        expected_rate_text,
        actual_rate_text,
    )
    expected_duration = float(expected.get("duration_seconds") or 0.0)
    actual_duration = float(probe.get("duration_seconds") or 0.0)
    tolerance = max(0.5, expected_duration * 0.005)
    record(
        "duration",
        expected_duration > 0 and abs(actual_duration - expected_duration) <= tolerance,
        f"{expected_duration}s +/- {tolerance}s",
        actual_duration,
    )
    stream_identity_fields = {
        "audio_streams": ("codec", "channels", "channel_layout", "language", "title"),
        "subtitle_streams": ("codec", "language", "title"),
        "attachment_streams": ("codec", "filename", "mimetype"),
    }
    for key, identity_fields in stream_identity_fields.items():
        expected_streams = expected.get(key, [])
        actual_streams = probe.get(key, [])
        record(
            f"{key.removesuffix('_streams')}_stream_count",
            len(actual_streams) == len(expected_streams),
            len(expected_streams),
            len(actual_streams),
        )
        expected_inventory = [
            {field: stream.get(field) for field in identity_fields}
            for stream in expected_streams
        ]
        actual_inventory = [
            {field: stream.get(field) for field in identity_fields}
            for stream in actual_streams
        ]
        record(
            f"{key.removesuffix('_streams')}_stream_inventory",
            actual_inventory == expected_inventory,
            expected_inventory,
            actual_inventory,
        )
    record(
        "chapter_count",
        int(probe.get("chapter_count") or 0) == int(expected.get("chapter_count") or 0),
        int(expected.get("chapter_count") or 0),
        int(probe.get("chapter_count") or 0),
    )
    expected_chapter_titles = [
        chapter.get("title") for chapter in expected.get("chapters", [])
    ]
    if any(title is not None for title in expected_chapter_titles):
        actual_chapter_titles = [
            chapter.get("title") for chapter in probe.get("chapters", [])
        ]
        record(
            "chapter_title_order",
            actual_chapter_titles == expected_chapter_titles,
            expected_chapter_titles,
            actual_chapter_titles,
        )
    failures = [check["name"] for check in checks if check["outcome"] == "FAIL"]
    return {
        "outcome": "FAIL" if failures else "PASS",
        "checks": checks,
        "reasons": (
            [f"Required final MKV checks failed: {', '.join(failures)}."]
            if failures
            else ["All required final MKV checks passed."]
        ),
        "probe": probe,
    }


class FinalizationStore:
    def __init__(self, database_path: str | Path | None = None):
        self.database_path = Path(database_path or settings.rve_state_database).expanduser().resolve()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def initialize(self) -> None:
        self.database_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS finalizations (
                    finalization_id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL UNIQUE,
                    preparation_id TEXT NOT NULL,
                    rve_job_id TEXT NOT NULL,
                    profile_name TEXT NOT NULL,
                    movie_title TEXT NOT NULL,
                    final_filename TEXT NOT NULL,
                    destination_location_id TEXT NOT NULL,
                    destination_location_name TEXT NOT NULL,
                    local_partial_path TEXT NOT NULL,
                    local_final_path TEXT NOT NULL,
                    log_path TEXT NOT NULL,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    finalization_started_at TEXT,
                    finalized_at TEXT,
                    publication_started_at TEXT,
                    published_at TEXT,
                    remux_command_json TEXT,
                    final_validation_status TEXT,
                    final_validation_json TEXT,
                    publication_validation_status TEXT,
                    publication_validation_json TEXT,
                    published_path_identity TEXT,
                    failure_reason TEXT
                );
                CREATE INDEX IF NOT EXISTS finalizations_created
                    ON finalizations (created_at DESC);
                """
            )
        os.chmod(self.database_path, 0o600)

    def insert(self, record: dict[str, Any]) -> None:
        columns = ", ".join(record)
        placeholders = ", ".join("?" for _ in record)
        try:
            with self._connect() as connection:
                connection.execute(
                    f"INSERT INTO finalizations ({columns}) VALUES ({placeholders})",
                    tuple(record.values()),
                )
        except sqlite3.IntegrityError as exc:
            raise FileExistsError("This workflow already has a finalization record.") from exc

    def get(self, finalization_id: str) -> dict[str, Any]:
        if not JOB_ID_PATTERN.fullmatch(str(finalization_id)):
            raise ValueError("Invalid finalization identifier.")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM finalizations WHERE finalization_id = ?",
                (finalization_id,),
            ).fetchone()
        if row is None:
            raise FileNotFoundError("Finalization was not found.")
        return dict(row)

    def find_by_workflow(self, workflow_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM finalizations WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchone()
        return dict(row) if row else None

    def reconcile_interrupted(self) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE finalizations
                SET state = 'failed',
                    failure_reason = ?
                WHERE state IN ('finalizing', 'publishing')
                """,
                (
                    "Application restarted during finalization or publication; "
                    "automatic retry and publication are disabled.",
                ),
            )
            return cursor.rowcount

    def transition(
        self,
        finalization_id: str,
        expected: set[str],
        new_state: str,
        **updates: Any,
    ) -> dict[str, Any]:
        if new_state not in FINALIZATION_STATES:
            raise ValueError("Invalid finalization state.")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT state FROM finalizations WHERE finalization_id = ?",
                (finalization_id,),
            ).fetchone()
            if row is None:
                raise FileNotFoundError("Finalization was not found.")
            if row["state"] not in expected:
                raise ValueError(
                    f"Finalization cannot transition from state {row['state']!r}."
                )
            fields = {"state": new_state, **updates}
            assignments = ", ".join(f"{name} = ?" for name in fields)
            connection.execute(
                f"UPDATE finalizations SET {assignments} WHERE finalization_id = ?",
                (*fields.values(), finalization_id),
            )
        return self.get(finalization_id)


def publication_root_status(
    *,
    root: str | Path | None = None,
    movies_root: str | Path | None = None,
    runner: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    configured = Path(root or settings.publication_root).expanduser()
    broad = Path(movies_root or settings.trusted_nas_movies_root).expanduser().resolve()
    result = {
        "available": False,
        "reason": "",
        "boundary": "separate narrow publication mount",
    }
    if not configured.is_absolute():
        result["reason"] = "Publication root must be an absolute server-owned path."
        return result
    if not configured.exists():
        result["reason"] = "The narrow publication mount is absent."
        return result
    if configured.is_symlink() or not configured.is_dir():
        result["reason"] = "Publication root must be a real directory, not a symlink."
        return result
    resolved = configured.resolve()
    if (
        resolved == broad
        or broad in resolved.parents
        or resolved in broad.parents
    ):
        result["reason"] = "Publication root must be distinct from the broad Movies hierarchy."
        return result

    def findmnt(column: str) -> str | None:
        try:
            process = runner(
                ["findmnt", "-n", "-T", str(resolved), "-o", column],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        value = (process.stdout or "").strip()
        return value if process.returncode == 0 and value else None

    target = findmnt("TARGET")
    source = findmnt("SOURCE")
    filesystem = findmnt("FSTYPE")
    options = findmnt("OPTIONS")
    if target is None or Path(target).resolve() != resolved:
        result["reason"] = "Publication root is not a distinct narrow mount point."
        return result
    if filesystem is None or filesystem.lower() not in NETWORK_FILESYSTEMS:
        result["reason"] = "Publication root is not a verified NAS filesystem."
        return result
    mount_evidence = f"{source or ''} {options or ''}".replace("\\040", " ")
    if settings.publication_mount_identity.lower() not in mount_evidence.lower():
        result["reason"] = (
            "Publication mount does not identify the approved narrow destination."
        )
        return result
    option_set = {option.strip().lower() for option in (options or "").split(",")}
    if "ro" in option_set or "rw" not in option_set or not os.access(resolved, os.W_OK):
        result["reason"] = "The narrow publication mount is not writable."
        return result
    return {
        **result,
        "available": True,
        "reason": "Narrow publication mount is present and writable.",
        "filesystem": filesystem,
    }


def _atomic_rename_noreplace(source: Path, destination: Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise OSError(errno.ENOTSUP, "Atomic no-replace rename is unavailable.")
    renameat2.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        -100,
        os.fsencode(source),
        -100,
        os.fsencode(destination),
        1,
    )
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(destination))


def public_finalization(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "finalization_id": record["finalization_id"],
        "workflow_id": record["workflow_id"],
        "preparation_id": record["preparation_id"],
        "rve_job_id": record["rve_job_id"],
        "profile_name": record["profile_name"],
        "movie_title": record["movie_title"],
        "final_filename": record["final_filename"],
        "destination_location_id": record["destination_location_id"],
        "destination_location_name": record["destination_location_name"],
        "state": record["state"],
        "created_at": record["created_at"],
        "finalization_started_at": record["finalization_started_at"],
        "finalized_at": record["finalized_at"],
        "publication_started_at": record["publication_started_at"],
        "published_at": record["published_at"],
        "final_validation_status": record["final_validation_status"],
        "final_validation": (
            json.loads(record["final_validation_json"])
            if record.get("final_validation_json")
            else None
        ),
        "publication_validation_status": record["publication_validation_status"],
        "publication_validation": (
            json.loads(record["publication_validation_json"])
            if record.get("publication_validation_json")
            else None
        ),
        "local_artifact_identity": (
            f"{record['preparation_id']}/finalizations/{record['finalization_id']}/final.mkv"
            if record["state"] in {"finalized", "publishing", "published", "failed"}
            and Path(record["local_final_path"]).is_file()
            else None
        ),
        "published_path_identity": record["published_path_identity"],
        "failure_reason": record["failure_reason"],
    }


class FinalizationService:
    def __init__(
        self,
        finalization_store: FinalizationStore,
        operator_store: Any,
        rve_store: Any,
        *,
        work_root: str | Path | None = None,
        runner: Callable[..., Any] = subprocess.run,
        prepared_validator: Callable[[Path, dict[str, Any]], dict[str, Any]] = validate_prepared_output,
        rve_validator: Callable[[Path, dict[str, Any]], dict[str, Any]] = validate_rve_output,
        final_validator: Callable[..., dict[str, Any]] = validate_final_output,
        publication_checker: Callable[..., dict[str, Any]] = publication_root_status,
        copy_function: Callable[..., Any] = shutil.copyfileobj,
        promoter: Callable[[Path, Path], None] = _atomic_rename_noreplace,
        verify_runtime: bool = True,
    ):
        self.store = finalization_store
        self.operator_store = operator_store
        self.rve_store = rve_store
        self.work_root = Path(work_root or settings.preparation_work_root).expanduser().resolve()
        self.runner = runner
        self.prepared_validator = prepared_validator
        self.rve_validator = rve_validator
        self.final_validator = final_validator
        self.publication_checker = publication_checker
        self.copy_function = copy_function
        self.promoter = promoter
        self.verify_runtime = verify_runtime

    def _destination(self, workflow: dict[str, Any]) -> dict[str, Any]:
        destination_id = workflow.get("destination_location_id")
        if not destination_id:
            raise ValueError("Select a Finished Movie Destination before finalization.")
        destination = self.operator_store.get_location(
            destination_id,
            role="FINISHED_DESTINATION",
            require_enabled=True,
        )
        expected_root = (
            Path(settings.trusted_nas_movies_root)
            / settings.publication_destination_folder
        ).expanduser().resolve()
        if (
            destination["relative_folder"] != settings.publication_destination_folder
            or Path(destination["server_root"]).resolve() != expected_root
        ):
            raise ValueError(
                "Selected destination is not the approved narrow publication destination."
            )
        return destination

    def adopt_historical_workflow(
        self,
        *,
        source_location_id: str,
        source_relative_path: str,
        destination_location_id: str,
        preparation_id: str,
        rve_job_id: str,
    ) -> dict[str, Any]:
        if (
            self.operator_store.find_workflow_by_preparation(preparation_id)
            or self.operator_store.find_workflow_by_job(rve_job_id)
        ):
            raise ValueError("Historical evidence is already associated with a workflow.")
        source_location = self.operator_store.get_location(
            source_location_id,
            role="ORIGINAL_SOURCE",
            require_enabled=True,
        )
        destination = self.operator_store.get_location(
            destination_location_id,
            role="FINISHED_DESTINATION",
            require_enabled=True,
        )
        expected_destination = (
            Path(settings.trusted_nas_movies_root)
            / settings.publication_destination_folder
        ).expanduser().resolve()
        if (
            destination["relative_folder"] != settings.publication_destination_folder
            or Path(destination["server_root"]).resolve() != expected_destination
        ):
            raise ValueError("Historical adoption requires the approved DVD Upscaled destination.")
        eligibility = assess_preparation_eligibility(
            source_relative_path,
            root=source_location["server_root"],
            verify_read_only_mount=self.verify_runtime,
        )
        if not eligibility["eligible"]:
            raise ValueError(eligibility["reason"])
        source_path = validate_candidate_relative_path(
            source_relative_path,
            root=source_location["server_root"],
        )
        source_stat = source_path.stat()

        plan = load_preparation_plan(preparation_id, work_root=self.work_root)
        if plan.get("preparation_id") != preparation_id:
            raise ValueError("Historical preparation identity does not match its plan.")
        if (
            source_stat.st_size != plan.get("source_size_bytes")
            or source_stat.st_mtime_ns != plan.get("source_mtime_ns")
        ):
            raise ValueError("Relocated source identity does not match historical evidence.")
        historical_absolute = str(plan.get("source_absolute_path") or "")
        historical_relative = str(plan.get("source_relative_path") or "")
        if not historical_absolute or not historical_relative:
            raise ValueError("Historical preparation lacks recorded source identity.")
        prepared_path = (self.work_root / preparation_id / "prepared.mkv").resolve()
        if Path(plan.get("final_prepared_output_path", "")).resolve() != prepared_path:
            raise ValueError("Prepared artifact path does not match the historical plan.")
        if self.prepared_validator(prepared_path, plan).get("outcome") != "PASS":
            raise ValueError("Historical preparation must retain a current validator PASS.")

        job = self.rve_store.get(rve_job_id)
        expected_output = (
            self.work_root / preparation_id / "rve" / rve_job_id / "enhanced.mkv"
        ).resolve()
        if (
            job.get("preparation_id") != preparation_id
            or job.get("state") != "completed"
            or job.get("output_validation_status") != "PASS"
            or Path(job.get("output_path", "")).resolve() != expected_output
            or json.loads(job.get("profile_json") or "{}") != locked_profile()
        ):
            raise ValueError("Historical RVE job does not retain completed/PASS authority.")
        if self.rve_validator(expected_output, job).get("outcome") != "PASS":
            raise ValueError("Historical RVE output must retain a current validator PASS.")

        return self.operator_store.create_historical_workflow_adoption(
            source_location_id=source_location_id,
            source_relative_path=source_relative_path,
            destination_location_id=destination_location_id,
            preparation_id=preparation_id,
            rve_job_id=rve_job_id,
            historical_source_absolute_path=historical_absolute,
            historical_source_relative_path=historical_relative,
            source_size_bytes=source_stat.st_size,
            source_mtime_ns=source_stat.st_mtime_ns,
        )

    def _authoritative_context(self, workflow_id: str) -> dict[str, Any]:
        workflow = self.operator_store.get_workflow(workflow_id)
        source_location = self.operator_store.get_location(
            workflow["source_location_id"],
            role="ORIGINAL_SOURCE",
            require_enabled=True,
        )
        destination = self._destination(workflow)
        preparation_id = workflow.get("preparation_id")
        if not preparation_id:
            raise ValueError("Workflow has no authoritative preparation.")
        plan = load_preparation_plan(preparation_id, work_root=self.work_root)
        plan_mismatches_workflow = (
            plan.get("workflow_id") != workflow["workflow_id"]
            or plan.get("source_location_id") != workflow["source_location_id"]
            or plan.get("source_relative_path") != workflow["source_relative_path"]
            or plan.get("destination_location_id") != workflow["destination_location_id"]
            or Path(plan.get("source_root", "")).resolve()
            != Path(source_location["server_root"]).resolve()
        )
        if plan_mismatches_workflow:
            adoption = self.operator_store.get_historical_workflow_adoption(
                workflow["workflow_id"]
            )
            if (
                adoption is None
                or adoption["preparation_id"] != preparation_id
                or adoption["rve_job_id"] != workflow.get("rve_job_id")
                or adoption["historical_source_absolute_path"]
                != str(plan.get("source_absolute_path") or "")
                or adoption["historical_source_relative_path"]
                != str(plan.get("source_relative_path") or "")
                or adoption["adopted_source_size_bytes"]
                != plan.get("source_size_bytes")
                or adoption["adopted_source_mtime_ns"]
                != plan.get("source_mtime_ns")
            ):
                raise ValueError("Preparation plan does not match the authoritative workflow.")
        source_path = validate_candidate_relative_path(
            workflow["source_relative_path"],
            root=source_location["server_root"],
        )
        source_stat = source_path.stat()
        if (
            source_stat.st_size != plan.get("source_size_bytes")
            or source_stat.st_mtime_ns != plan.get("source_mtime_ns")
        ):
            raise ValueError("Authoritative source identity no longer matches the preparation plan.")
        prepared_path = (self.work_root / preparation_id / "prepared.mkv").resolve()
        if Path(plan.get("final_prepared_output_path", "")).resolve() != prepared_path:
            raise ValueError("Prepared artifact path does not match the server-owned plan.")
        prepared_validation = self.prepared_validator(prepared_path, plan)
        if prepared_validation.get("outcome") != "PASS":
            raise ValueError("Prepared artifact must have a current validator PASS.")

        job_id = workflow.get("rve_job_id")
        if not job_id:
            raise ValueError("Workflow has no authoritative RVE job.")
        job = self.rve_store.get(job_id)
        expected_output = (
            self.work_root / preparation_id / "rve" / job_id / "enhanced.mkv"
        ).resolve()
        if (
            job.get("preparation_id") != preparation_id
            or job.get("state") != "completed"
            or job.get("output_validation_status") != "PASS"
            or Path(job.get("output_path", "")).resolve() != expected_output
            or json.loads(job.get("profile_json") or "{}") != locked_profile()
        ):
            raise ValueError("RVE job does not satisfy the completed locked-profile PASS contract.")
        rve_validation = self.rve_validator(expected_output, job)
        if rve_validation.get("outcome") != "PASS":
            raise ValueError("RVE output must have a current validator PASS.")
        expected_probe = rve_validation.get("probe") or probe_media(expected_output)
        if expected_probe.get("status") != "ok":
            raise ValueError("RVE output lacks authoritative stream evidence.")
        expected_probe = {
            **expected_probe,
            "duration_seconds": float(job["input_duration_seconds"]),
            "video_stream": {
                **expected_probe.get("video_stream", {}),
                "codec": "h264",
                "width": int(job["input_width"]) * 2,
                "height": int(job["input_height"]) * 2,
                "sample_aspect_ratio": "1:1",
                "pixel_format": locked_profile()["pixel_format"],
                "field_order": "progressive",
                "avg_frame_rate": job["input_frame_rate"],
            },
        }
        return {
            "workflow": workflow,
            "destination": destination,
            "plan": plan,
            "job": job,
            "enhanced_path": expected_output,
            "expected_probe": expected_probe,
        }

    def preview(self, workflow_id: str) -> dict[str, Any]:
        existing = self.store.find_by_workflow(workflow_id)
        if existing:
            return {"finalization": public_finalization(existing)}
        context = self._authoritative_context(workflow_id)
        title = suggest_movie_title(context["workflow"]["source_relative_path"])
        return {
            "finalization": None,
            "ready": True,
            "movie_title_suggestion": title,
            "generated_filename": generated_filename(title),
            "destination_location_id": context["destination"]["location_id"],
            "destination_location_name": context["destination"]["display_name"],
            "publication": self.publication_checker(),
        }

    def create(self, workflow_id: str, movie_title: str) -> dict[str, Any]:
        if self.store.find_by_workflow(workflow_id):
            raise FileExistsError("This workflow already has a finalization record.")
        context = self._authoritative_context(workflow_id)
        title = validate_movie_title(movie_title)
        finalization_id = uuid.uuid4().hex
        directory = (
            self.work_root
            / context["workflow"]["preparation_id"]
            / "finalizations"
            / finalization_id
        ).resolve()
        if self.work_root not in directory.parents:
            raise ValueError("Finalization directory escapes the local work root.")
        if self.verify_runtime and not work_root_is_local(self.work_root):
            raise ValueError("Finalization work root is not verified server-local storage.")
        directory.mkdir(mode=0o700, parents=True, exist_ok=False)
        log_path = directory / "finalization.log"
        log_path.touch(mode=0o600, exist_ok=False)
        record = {
            "finalization_id": finalization_id,
            "workflow_id": workflow_id,
            "preparation_id": context["workflow"]["preparation_id"],
            "rve_job_id": context["workflow"]["rve_job_id"],
            "profile_name": context["job"]["profile_name"],
            "movie_title": title,
            "final_filename": generated_filename(title),
            "destination_location_id": context["destination"]["location_id"],
            "destination_location_name": context["destination"]["display_name"],
            "local_partial_path": str(directory / "final.partial.mkv"),
            "local_final_path": str(directory / "final.mkv"),
            "log_path": str(log_path),
            "state": "created",
            "created_at": utc_now(),
            "finalization_started_at": None,
            "finalized_at": None,
            "publication_started_at": None,
            "published_at": None,
            "remux_command_json": None,
            "final_validation_status": None,
            "final_validation_json": None,
            "publication_validation_status": None,
            "publication_validation_json": None,
            "published_path_identity": None,
            "failure_reason": None,
        }
        try:
            self.store.insert(record)
        except Exception:
            log_path.unlink(missing_ok=True)
            directory.rmdir()
            raise
        with log_path.open("a", encoding="utf-8") as log:
            log.write(
                f"{utc_now()} finalization created: "
                f"{json.dumps({'movie_title': title, 'final_filename': record['final_filename']})}\n"
            )
        return self.store.get(finalization_id)

    def finalize(self, finalization_id: str) -> dict[str, Any]:
        record = self.store.get(finalization_id)
        context = self._authoritative_context(record["workflow_id"])
        if (
            record["preparation_id"] != context["workflow"]["preparation_id"]
            or record["rve_job_id"] != context["workflow"]["rve_job_id"]
            or record["destination_location_id"] != context["destination"]["location_id"]
        ):
            raise ValueError("Finalization record no longer matches the authoritative workflow.")
        partial = Path(record["local_partial_path"])
        final = Path(record["local_final_path"])
        if partial.exists() or final.exists():
            raise FileExistsError("Finalization artifact already exists; overwrite is not allowed.")
        command = build_final_remux_command(context["enhanced_path"], partial)
        self.store.transition(
            finalization_id,
            {"created"},
            "finalizing",
            finalization_started_at=utc_now(),
            remux_command_json=json.dumps(command),
        )
        try:
            process = self.runner(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=int(settings.finalization_timeout_seconds),
            )
            with Path(record["log_path"]).open("a", encoding="utf-8") as log:
                log.write(f"{utc_now()} remux command: {json.dumps(command)}\n")
                log.write(process.stdout or "")
                log.write(process.stderr or "")
            if process.returncode != 0:
                raise RuntimeError(
                    f"FFmpeg final remux exited unsuccessfully with code {process.returncode}."
                )
            validation = self.final_validator(partial, context["expected_probe"])
            validation_json = json.dumps(validation)
            with Path(record["log_path"]).open("a", encoding="utf-8") as log:
                log.write(f"{utc_now()} local final validation: {validation_json}\n")
            if validation.get("outcome") != "PASS":
                return self.store.transition(
                    finalization_id,
                    {"finalizing"},
                    "failed",
                    failure_reason="The local final MKV did not pass validation.",
                    final_validation_status=validation.get("outcome"),
                    final_validation_json=validation_json,
                )
            promote_validated_output(partial, final)
            return self.store.transition(
                finalization_id,
                {"finalizing"},
                "finalized",
                finalized_at=utc_now(),
                final_validation_status="PASS",
                final_validation_json=validation_json,
            )
        except Exception as exc:
            current = self.store.get(finalization_id)
            if current["state"] == "finalizing":
                return self.store.transition(
                    finalization_id,
                    {"finalizing"},
                    "failed",
                    failure_reason=f"Finalization failed: {exc}",
                )
            raise

    def publication_readiness(self, finalization_id: str) -> dict[str, Any]:
        record = self.store.get(finalization_id)
        status = self.publication_checker()
        collision = None
        if status.get("available"):
            collision = (
                Path(settings.publication_root) / record["final_filename"]
            ).exists()
        return {**status, "collision": collision}

    def publish(self, finalization_id: str) -> dict[str, Any]:
        record = self.store.get(finalization_id)
        if record["state"] != "finalized":
            raise ValueError("Only a locally finalized PASS artifact may be published.")
        context = self._authoritative_context(record["workflow_id"])
        if context["destination"]["location_id"] != record["destination_location_id"]:
            raise ValueError("Selected destination changed after finalization.")
        status = self.publication_checker()
        if not status.get("available"):
            raise RuntimeError(f"Publication unavailable. {status.get('reason', '')}".strip())
        root = Path(settings.publication_root).resolve()
        final_target = root / record["final_filename"]
        candidate = root / f".{record['final_filename']}.{finalization_id}.partial.mkv"
        if final_target.exists():
            raise FileExistsError(
                f"Publication blocked. {record['final_filename']} already exists."
            )
        if candidate.exists():
            raise FileExistsError("Application-owned publication candidate already exists.")

        self.store.transition(
            finalization_id,
            {"finalized"},
            "publishing",
            publication_started_at=utc_now(),
        )
        with Path(record["log_path"]).open("a", encoding="utf-8") as log:
            log.write(
                f"{utc_now()} publication started: "
                f"{json.dumps({'destination_location_id': record['destination_location_id'], 'filename': record['final_filename']})}\n"
            )
        candidate_created = False
        promoted_here = False
        last_validation: dict[str, Any] | None = None
        try:
            local_final = Path(record["local_final_path"])
            expected_size = local_final.stat().st_size
            with local_final.open("rb") as source, candidate.open("xb") as target:
                candidate_created = True
                self.copy_function(source, target)
                target.flush()
                os.fsync(target.fileno())
            candidate_validation = self.final_validator(
                candidate,
                context["expected_probe"],
                expected_size=expected_size,
            )
            last_validation = candidate_validation
            if candidate_validation.get("outcome") != "PASS":
                raise RuntimeError("The staged publication candidate did not pass validation.")
            self.promoter(candidate, final_target)
            candidate_created = False
            promoted_here = True
            published_validation = self.final_validator(
                final_target,
                context["expected_probe"],
                expected_size=expected_size,
            )
            last_validation = published_validation
            if published_validation.get("outcome") != "PASS":
                raise RuntimeError("The promoted publication did not pass final validation.")
            with Path(record["log_path"]).open("a", encoding="utf-8") as log:
                log.write(
                    f"{utc_now()} publication validation: "
                    f"{json.dumps(published_validation)}\n"
                )
            return self.store.transition(
                finalization_id,
                {"publishing"},
                "published",
                published_at=utc_now(),
                publication_validation_status="PASS",
                publication_validation_json=json.dumps(published_validation),
                published_path_identity=record["final_filename"],
            )
        except Exception as exc:
            cleanup_failures: list[str] = []
            cleanup_targets = (
                ("publication candidate", candidate, candidate_created),
                ("promoted publication", final_target, promoted_here),
            )
            for label, path, owned in cleanup_targets:
                if not owned or not path.is_file() or path.is_symlink():
                    continue
                try:
                    path.unlink()
                except OSError as cleanup_exc:
                    cleanup_failures.append(f"{label} cleanup failed: {cleanup_exc}")
            cleanup_note = (
                f" {'; '.join(cleanup_failures)}"
                if cleanup_failures
                else ""
            )
            with Path(record["log_path"]).open("a", encoding="utf-8") as log:
                log.write(f"{utc_now()} publication failed: {exc}{cleanup_note}\n")
            return self.store.transition(
                finalization_id,
                {"publishing"},
                "failed",
                publication_validation_status=(
                    last_validation.get("outcome") if last_validation else None
                ),
                publication_validation_json=(
                    json.dumps(last_validation) if last_validation else None
                ),
                failure_reason=(
                    "Publication failed; the validated local final MKV remains safe. "
                    f"{exc}{cleanup_note}"
                ),
            )
