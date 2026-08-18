from __future__ import annotations

import json
import os
import re
import signal
import sqlite3
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable

from app.config import settings
from app.services.media_analysis import probe_media
from app.services.media_preparation import (
    load_preparation_plan,
    preparation_execution_state,
    promote_validated_output,
    validate_prepared_output,
    work_root_is_local,
)

PROFILE_NAME = "DVD RVE Medium 2x"
ACTIVE_STATES = {"running", "cancel_requested"}
TERMINAL_STATES = {"cancelled", "completed", "failed", "interrupted"}
JOB_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
PROGRESS_PATTERN = re.compile(
    r"FPS:\s*(?P<fps>\d+)\s+Current Frame:\s*(?P<frame>\d+)\s+"
    r"ETA:\s*(?P<eta>\d+:\d{2}:\d{2})"
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def locked_profile() -> dict[str, Any]:
    return {
        "profile_name": PROFILE_NAME,
        "backend": "tensorrt",
        "model_family": "Nomos8k Realistic Medium",
        "model_path": str(Path(settings.rve_model).resolve()),
        "scale": 2,
        "precision": "float16",
        "tensorrt_opt_profile": 3,
        "interpolation": False,
        "decompression": False,
        "denoise": False,
        "video_encoder": "x264_nvenc",
        "pixel_format": "yuv420p",
        "audio": "copy_audio",
        "subtitles": "copy_subtitle",
    }


def verify_rve_runtime() -> dict[str, Any]:
    required = {
        "bundled_python": Path(settings.rve_python),
        "backend_script": Path(settings.rve_backend),
        "ffmpeg": Path(settings.rve_ffmpeg),
        "model": Path(settings.rve_model),
        "runtime_root": Path(settings.rve_root),
    }
    missing = [name for name, path in required.items() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Required RVE runtime component is missing: {', '.join(missing)}.")
    if not required["bundled_python"].is_file() or not os.access(required["bundled_python"], os.X_OK):
        raise ValueError("Bundled RVE Python is not executable.")
    if not required["ffmpeg"].is_file() or not os.access(required["ffmpeg"], os.X_OK):
        raise ValueError("Bundled RVE FFmpeg is not executable.")
    for name in ("backend_script", "model"):
        if not required[name].is_file():
            raise ValueError(f"RVE {name.replace('_', ' ')} is not a regular file.")
    return {name: str(path.resolve()) for name, path in required.items()}


def build_rve_command(job: dict[str, Any]) -> list[str]:
    profile = json.loads(job["profile_json"])
    if profile != locked_profile():
        raise ValueError("Stored RVE profile does not match the locked enhancement contract.")
    return [
        str(Path(settings.rve_python).resolve()),
        str(Path(settings.rve_backend).resolve()),
        "-i",
        job["input_path"],
        "-o",
        job["partial_output_path"],
        "--ffmpeg_path",
        str(Path(settings.rve_ffmpeg).resolve()),
        "--backend",
        "tensorrt",
        "--upscale_model",
        profile["model_path"],
        "--override_upscale_scale",
        "2",
        "--interpolate_factor",
        "1",
        "--precision",
        "float16",
        "--tensorrt_opt_profile",
        "3",
        "--video_encoder_preset",
        "x264_nvenc",
        "--video_pixel_format",
        "yuv420p",
        "--audio_encoder_preset",
        "copy_audio",
        "--subtitle_encoder_preset",
        "copy_subtitle",
        "--cwd",
        job["job_directory"],
    ]


def _ratio(value: Any) -> float | None:
    text = str(value or "").strip()
    try:
        if "/" in text:
            numerator, denominator = text.split("/", 1)
            if Fraction(denominator) == 0:
                return None
            return float(Fraction(numerator) / Fraction(denominator))
        return float(text)
    except (ValueError, ZeroDivisionError):
        return None


def validate_rve_output(output_path: Path, job: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def record(name: str, passed: bool, expected: Any, actual: Any) -> None:
        checks.append(
            {
                "name": name,
                "outcome": "PASS" if passed else "FAIL",
                "expected": expected,
                "actual": actual,
            }
        )

    exists = output_path.is_file()
    record("file_exists", exists, True, exists)
    if not exists:
        return {"outcome": "FAIL", "checks": checks, "reasons": ["RVE output file is missing."]}
    size = output_path.stat().st_size
    record("file_non_zero", size > 0, "> 0 bytes", size)
    if size <= 0:
        return {"outcome": "FAIL", "checks": checks, "reasons": ["RVE output file is empty."]}

    probe = probe_media(output_path)
    probe_ok = probe.get("status") == "ok"
    record("ffprobe_readable", probe_ok, "ok", probe.get("status"))
    if not probe_ok:
        return {
            "outcome": "FAIL",
            "checks": checks,
            "reasons": [probe.get("error", "RVE output is not ffprobe-readable.")],
        }

    video = probe.get("video_stream", {})
    expected_width = int(job["input_width"]) * 2
    expected_height = int(job["input_height"]) * 2
    record("video_stream", bool(video), "present", "present" if video else "missing")
    record("video_width", video.get("width") == expected_width, expected_width, video.get("width"))
    record("video_height", video.get("height") == expected_height, expected_height, video.get("height"))

    expected_rate = _ratio(job["input_frame_rate"])
    actual_rate = _ratio(video.get("avg_frame_rate") or video.get("r_frame_rate"))
    rate_matches = (
        expected_rate is not None
        and expected_rate > 0
        and actual_rate is not None
        and abs(actual_rate - expected_rate) / expected_rate <= 0.001
    )
    record(
        "frame_rate",
        rate_matches,
        job["input_frame_rate"],
        video.get("avg_frame_rate") or video.get("r_frame_rate"),
    )

    input_duration = float(job["input_duration_seconds"])
    output_duration = float(probe.get("duration_seconds") or 0.0)
    tolerance = max(0.5, input_duration * 0.005)
    record(
        "duration",
        input_duration > 0 and abs(output_duration - input_duration) <= tolerance,
        f"{input_duration}s +/- {tolerance}s",
        output_duration,
    )

    failures = [check["name"] for check in checks if check["outcome"] == "FAIL"]
    return {
        "outcome": "FAIL" if failures else "PASS",
        "checks": checks,
        "reasons": (
            [f"Required RVE validation checks failed: {', '.join(failures)}."]
            if failures
            else ["All required bounded RVE validation checks passed."]
        ),
        "probe": probe,
    }


class RVEJobStore:
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
        if not work_root_is_local(self.database_path.parent):
            raise ValueError("RVE job database is not on verified server-local storage.")
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS rve_jobs (
                    job_id TEXT PRIMARY KEY,
                    preparation_id TEXT NOT NULL,
                    profile_name TEXT NOT NULL,
                    resolved_backend TEXT NOT NULL,
                    resolved_model TEXT NOT NULL,
                    resolved_scale INTEGER NOT NULL,
                    profile_json TEXT NOT NULL,
                    input_path TEXT NOT NULL,
                    output_path TEXT NOT NULL,
                    partial_output_path TEXT NOT NULL,
                    job_directory TEXT NOT NULL,
                    input_width INTEGER NOT NULL,
                    input_height INTEGER NOT NULL,
                    input_frame_rate TEXT NOT NULL,
                    input_duration_seconds REAL NOT NULL,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    pid INTEGER,
                    pgid INTEGER,
                    exit_code INTEGER,
                    progress_percent REAL,
                    progress_message TEXT,
                    failure_reason TEXT,
                    cancellation_reason TEXT,
                    log_path TEXT NOT NULL,
                    output_validation_status TEXT,
                    output_validation_json TEXT
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_rve_job
                    ON rve_jobs ((1))
                    WHERE state IN ('running', 'cancel_requested');
                """
            )
        os.chmod(self.database_path, 0o600)

    def insert(self, job: dict[str, Any]) -> None:
        columns = ", ".join(job)
        placeholders = ", ".join("?" for _ in job)
        with self._connect() as connection:
            connection.execute(
                f"INSERT INTO rve_jobs ({columns}) VALUES ({placeholders})",
                tuple(job.values()),
            )

    def get(self, job_id: str) -> dict[str, Any]:
        if not JOB_ID_PATTERN.fullmatch(job_id):
            raise ValueError("Invalid RVE job identifier.")
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM rve_jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            raise FileNotFoundError("RVE job was not found.")
        return dict(row)

    def list_recent(self, limit: int = 10) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(int(limit), 50))
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM rve_jobs "
                "ORDER BY created_at DESC, job_id DESC LIMIT ?",
                (bounded_limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def claim(self, job_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT state FROM rve_jobs WHERE job_id = ?", (job_id,)).fetchone()
            if row is None:
                raise FileNotFoundError("RVE job was not found.")
            if row["state"] != "created":
                raise ValueError(f"RVE job cannot start from state {row['state']!r}.")
            active = connection.execute(
                "SELECT job_id FROM rve_jobs WHERE state IN ('running', 'cancel_requested')"
            ).fetchone()
            if active is not None:
                raise RuntimeError("Another RVE enhancement job is already running.")
            connection.execute(
                """
                UPDATE rve_jobs
                SET state = 'running', started_at = ?, progress_message = ?
                WHERE job_id = ? AND state = 'created'
                """,
                (utc_now(), "Starting RVE backend.", job_id),
            )
        return self.get(job_id)

    def transition(
        self,
        job_id: str,
        expected: set[str],
        new_state: str,
        **updates: Any,
    ) -> dict[str, Any]:
        if new_state not in {
            "created",
            "running",
            "cancel_requested",
            "cancelled",
            "completed",
            "failed",
            "interrupted",
        }:
            raise ValueError("Invalid RVE job state.")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT state FROM rve_jobs WHERE job_id = ?", (job_id,)).fetchone()
            if row is None:
                raise FileNotFoundError("RVE job was not found.")
            if row["state"] not in expected:
                raise ValueError(f"RVE job cannot transition from state {row['state']!r}.")
            fields = {"state": new_state, **updates}
            if new_state in TERMINAL_STATES:
                fields.setdefault("finished_at", utc_now())
                fields.setdefault("pid", None)
                fields.setdefault("pgid", None)
            assignments = ", ".join(f"{name} = ?" for name in fields)
            connection.execute(
                f"UPDATE rve_jobs SET {assignments} WHERE job_id = ?",
                (*fields.values(), job_id),
            )
        return self.get(job_id)

    def update(self, job_id: str, **updates: Any) -> None:
        if not updates:
            return
        assignments = ", ".join(f"{name} = ?" for name in updates)
        with self._connect() as connection:
            connection.execute(
                f"UPDATE rve_jobs SET {assignments} WHERE job_id = ?",
                (*updates.values(), job_id),
            )

    def reconcile_interrupted(self) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE rve_jobs
                SET state = 'interrupted',
                    finished_at = ?,
                    pid = NULL,
                    pgid = NULL,
                    failure_reason = ?
                WHERE state IN ('running', 'cancel_requested')
                """,
                (
                    utc_now(),
                    "Application restarted while job was active; automatic process reattachment is not supported in v1.",
                ),
            )
            return cursor.rowcount


def public_job(job: dict[str, Any]) -> dict[str, Any]:
    profile = json.loads(job["profile_json"])
    validation = json.loads(job["output_validation_json"]) if job.get("output_validation_json") else None
    progress_match = PROGRESS_PATTERN.search(job.get("progress_message") or "")
    return {
        "job_id": job["job_id"],
        "preparation_id": job["preparation_id"],
        "profile": {
            "name": profile["profile_name"],
            "backend": profile["backend"],
            "model_family": profile["model_family"],
            "scale": profile["scale"],
            "interpolation": profile["interpolation"],
            "decompression": profile["decompression"],
            "denoise": profile["denoise"],
        },
        "state": job["state"],
        "created_at": job["created_at"],
        "started_at": job["started_at"],
        "finished_at": job["finished_at"],
        "exit_code": job["exit_code"],
        "progress_percent": job["progress_percent"],
        "progress_message": job["progress_message"],
        "progress_fps": int(progress_match.group("fps")) if progress_match else None,
        "progress_eta": progress_match.group("eta") if progress_match else None,
        "failure_reason": job["failure_reason"],
        "cancellation_reason": job["cancellation_reason"],
        "output_validation_status": job["output_validation_status"],
        "output_validation": validation,
        "local_artifact_identity": (
            f"{job['preparation_id']}/rve/{job['job_id']}/enhanced.mkv"
            if job["state"] == "completed"
            else None
        ),
    }


def create_rve_job(
    preparation_id: str,
    store: RVEJobStore,
    *,
    work_root: str | Path | None = None,
    verify_runtime: bool = True,
    validator: Callable[[Path, dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    root = Path(work_root or settings.preparation_work_root).expanduser().resolve()
    if verify_runtime:
        verify_rve_runtime()
        if not work_root_is_local(root):
            raise ValueError("RVE work root is not verified server-local storage.")
    plan = load_preparation_plan(preparation_id, work_root=root)
    prepared_path = (root / preparation_id / "prepared.mkv").resolve()
    if prepared_path != Path(plan.get("final_prepared_output_path", "")).resolve():
        raise ValueError("Prepared artifact path does not match the server-owned preparation plan.")
    validation = (validator or validate_prepared_output)(prepared_path, plan)
    if validation.get("outcome") != "PASS":
        raise ValueError("Prepared artifact must pass the accepted preparation validator.")

    target = plan.get("target_prepared_geometry", {})
    width = int(target.get("width") or 0)
    height = int(target.get("height") or 0)
    duration = float(plan.get("source_duration_seconds") or 0.0)
    frame_rate = str(plan.get("frame_rate") or "")
    if width <= 0 or height <= 0 or duration <= 0 or _ratio(frame_rate) in (None, 0):
        raise ValueError("Prepared artifact plan lacks required geometry, duration, or frame-rate evidence.")

    job_id = uuid.uuid4().hex
    job_directory = (root / preparation_id / "rve" / job_id).resolve()
    if root not in job_directory.parents:
        raise ValueError("RVE job directory escapes the local work root.")
    job_directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    partial_output = job_directory / "enhanced.partial.mkv"
    output = job_directory / "enhanced.mkv"
    log_path = job_directory / "job.log"
    log_path.touch(mode=0o600, exist_ok=False)
    profile = locked_profile()
    record = {
        "job_id": job_id,
        "preparation_id": preparation_id,
        "profile_name": PROFILE_NAME,
        "resolved_backend": profile["backend"],
        "resolved_model": profile["model_path"],
        "resolved_scale": profile["scale"],
        "profile_json": json.dumps(profile, sort_keys=True),
        "input_path": str(prepared_path),
        "output_path": str(output),
        "partial_output_path": str(partial_output),
        "job_directory": str(job_directory),
        "input_width": width,
        "input_height": height,
        "input_frame_rate": frame_rate,
        "input_duration_seconds": duration,
        "state": "created",
        "created_at": utc_now(),
        "started_at": None,
        "finished_at": None,
        "pid": None,
        "pgid": None,
        "exit_code": None,
        "progress_percent": None,
        "progress_message": "RVE job created; explicit start is required.",
        "failure_reason": None,
        "cancellation_reason": None,
        "log_path": str(log_path),
        "output_validation_status": None,
        "output_validation_json": None,
    }
    store.insert(record)
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"{utc_now()} job created\n")
        log.write(f"{utc_now()} locked profile: {json.dumps(profile, sort_keys=True)}\n")
    return store.get(job_id)


def list_local_preparations(
    *,
    work_root: str | Path | None = None,
    validator: Callable[[Path, dict[str, Any]], dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    root = Path(work_root or settings.preparation_work_root).expanduser().resolve()
    if not root.is_dir():
        return []
    results: list[dict[str, Any]] = []
    for directory in sorted(root.iterdir(), key=lambda path: path.name):
        if (
            directory.is_symlink()
            or not directory.is_dir()
            or not JOB_ID_PATTERN.fullmatch(directory.name)
        ):
            continue
        try:
            plan = load_preparation_plan(directory.name, work_root=root)
            prepared_path = (directory / "prepared.mkv").resolve()
            execution = preparation_execution_state(plan)
            if execution["preparation_status"] == "plan_ready":
                validation = {
                    "outcome": "NOT RUN",
                    "reasons": ["Preparation plan ready."],
                }
            else:
                validation = (validator or validate_prepared_output)(prepared_path, plan)
            results.append(
                {
                    "preparation_id": directory.name,
                    "source_relative_path": plan.get("source_relative_path"),
                    "prepared_geometry": plan.get("target_prepared_geometry"),
                    "selected_preparation_decision": plan.get(
                        "selected_preparation_decision"
                    ),
                    "pixel_format": plan.get("pixel_format"),
                    **execution,
                    "validation_status": validation.get("outcome"),
                    "available_for_rve": validation.get("outcome") == "PASS",
                    "reason": " ".join(validation.get("reasons", [])),
                }
            )
        except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
            results.append(
                {
                    "preparation_id": directory.name,
                    "source_relative_path": None,
                    "prepared_geometry": None,
                    "validation_status": "ERROR",
                    "available_for_rve": False,
                    "reason": f"Preparation could not be validated: {exc}",
                }
            )
    return results


@dataclass
class OwnedProcess:
    process: Any
    pgid: int
    thread: threading.Thread


class RVEJobManager:
    def __init__(
        self,
        store: RVEJobStore,
        *,
        popen_factory: Callable[..., Any] = subprocess.Popen,
        pgid_resolver: Callable[[int], int] = os.getpgid,
        group_signaler: Callable[[int, int], None] = os.killpg,
        cancel_grace_seconds: float | None = None,
        output_validator: Callable[[Path, dict[str, Any]], dict[str, Any]] = validate_rve_output,
    ):
        self.store = store
        self.popen_factory = popen_factory
        self.pgid_resolver = pgid_resolver
        self.group_signaler = group_signaler
        self.cancel_grace_seconds = float(
            settings.rve_cancel_grace_seconds if cancel_grace_seconds is None else cancel_grace_seconds
        )
        self.output_validator = output_validator
        self._owned: dict[str, OwnedProcess] = {}
        self._lock = threading.Lock()

    def start(self, job_id: str) -> dict[str, Any]:
        self.store.claim(job_id)
        launch_ready = threading.Event()
        thread = threading.Thread(
            target=self._run,
            args=(job_id, launch_ready),
            name=f"rve-{job_id}",
            daemon=False,
        )
        try:
            thread.start()
        except RuntimeError as exc:
            return self.store.transition(
                job_id,
                {"running"},
                "failed",
                failure_reason=f"RVE supervision thread could not start: {exc}",
            )
        if not launch_ready.wait(timeout=10):
            return self.store.transition(
                job_id,
                {"running"},
                "interrupted",
                failure_reason="RVE process ownership was not established within the launch timeout.",
            )
        return self.store.get(job_id)

    def _log_and_parse(self, job: dict[str, Any], text: str) -> None:
        if not text:
            return
        with Path(job["log_path"]).open("a", encoding="utf-8") as log:
            log.write(text)
        for match in PROGRESS_PATTERN.finditer(text):
            frame = int(match.group("frame"))
            expected_rate = _ratio(job["input_frame_rate"]) or 0.0
            total_frames = max(1, round(float(job["input_duration_seconds"]) * expected_rate))
            percent = min(100.0, round(frame * 100.0 / total_frames, 2))
            message = (
                f"FPS: {match.group('fps')} Current Frame: {frame} "
                f"ETA: {match.group('eta')}"
            )
            self.store.update(job["job_id"], progress_percent=percent, progress_message=message)

    def _run(self, job_id: str, launch_ready: threading.Event) -> None:
        job = self.store.get(job_id)
        command = build_rve_command(job)
        with Path(job["log_path"]).open("a", encoding="utf-8") as log:
            log.write(f"{utc_now()} process launch: {json.dumps(command)}\n")
        try:
            process = self.popen_factory(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                shell=False,
                start_new_session=True,
                cwd=str(Path(settings.rve_root).resolve()),
                bufsize=0,
            )
            pgid = self.pgid_resolver(process.pid)
            thread = threading.current_thread()
            with self._lock:
                self._owned[job_id] = OwnedProcess(process=process, pgid=pgid, thread=thread)
            self.store.update(job_id, pid=process.pid, pgid=pgid)
            launch_ready.set()

            current = self.store.get(job_id)
            if current["state"] == "cancel_requested":
                self._signal_owned(job_id)
            elif current["state"] != "running":
                self._signal_owned(job_id)

            pending = ""
            while True:
                chunk = process.stdout.read(1) if process.stdout is not None else b""
                if chunk:
                    text = chunk.decode("utf-8", errors="replace") if isinstance(chunk, bytes) else chunk
                    pending += text
                    if text in {"\r", "\n"}:
                        self._log_and_parse(job, pending)
                        pending = ""
                    continue
                if process.poll() is not None:
                    break
                time.sleep(0.05)
            self._log_and_parse(job, pending)
            exit_code = process.wait()
            self.store.update(job_id, exit_code=exit_code)
            current = self.store.get(job_id)
            if current["state"] == "cancel_requested":
                self.store.transition(
                    job_id,
                    {"cancel_requested"},
                    "cancelled",
                    cancellation_reason=current["cancellation_reason"] or "Cancelled by Product Owner.",
                    progress_message="RVE enhancement cancelled.",
                )
                return
            if current["state"] in {"cancelled", "interrupted"}:
                return
            if exit_code != 0:
                self.store.transition(
                    job_id,
                    {"running"},
                    "failed",
                    failure_reason=f"RVE backend exited with code {exit_code}.",
                    progress_message="RVE backend failed.",
                )
                return

            validation = self.output_validator(Path(job["partial_output_path"]), job)
            validation_json = json.dumps(validation)
            if validation.get("outcome") != "PASS":
                self.store.transition(
                    job_id,
                    {"running"},
                    "failed",
                    failure_reason="RVE output failed bounded sanity validation.",
                    output_validation_status=validation.get("outcome"),
                    output_validation_json=validation_json,
                    progress_message="RVE output validation failed.",
                )
                return
            promote_validated_output(Path(job["partial_output_path"]), Path(job["output_path"]))
            self.store.transition(
                job_id,
                {"running"},
                "completed",
                output_validation_status="PASS",
                output_validation_json=validation_json,
                progress_percent=100.0,
                progress_message="RVE enhancement completed and passed validation.",
            )
        except Exception as exc:
            current = self.store.get(job_id)
            if current["state"] in ACTIVE_STATES:
                target = "cancelled" if current["state"] == "cancel_requested" else "failed"
                updates = (
                    {"cancellation_reason": f"Cancellation completed after backend error: {exc}"}
                    if target == "cancelled"
                    else {"failure_reason": f"RVE process supervision failed: {exc}"}
                )
                self.store.transition(job_id, {current["state"]}, target, **updates)
        finally:
            launch_ready.set()
            with self._lock:
                self._owned.pop(job_id, None)

    def cancel(self, job_id: str, reason: str = "Cancelled by Product Owner.") -> dict[str, Any]:
        current = self.store.get(job_id)
        if current["state"] != "running":
            raise ValueError(f"RVE job cannot be cancelled from state {current['state']!r}.")
        with self._lock:
            owned = self._owned.get(job_id)
        if owned is None:
            return self.store.transition(
                job_id,
                {"running"},
                "interrupted",
                failure_reason="Live process ownership could not be proven; no persisted PID/PGID was signaled.",
            )
        if owned.process.poll() is not None:
            raise ValueError("RVE backend has exited; completion is being finalized.")
        self.store.transition(
            job_id,
            {"running"},
            "cancel_requested",
            cancellation_reason=reason,
            progress_message="Cancellation requested.",
        )
        threading.Thread(target=self._signal_owned, args=(job_id,), daemon=False).start()
        return self.store.get(job_id)

    def _signal_owned(self, job_id: str) -> None:
        with self._lock:
            owned = self._owned.get(job_id)
        if owned is None or owned.process.poll() is not None:
            return
        self.group_signaler(owned.pgid, signal.SIGTERM)
        deadline = time.monotonic() + self.cancel_grace_seconds
        while owned.process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        if owned.process.poll() is None:
            self.group_signaler(owned.pgid, signal.SIGKILL)

    def shutdown(self) -> None:
        with self._lock:
            owned_jobs = list(self._owned.items())
        for job_id, owned in owned_jobs:
            current = self.store.get(job_id)
            if current["state"] in ACTIVE_STATES:
                try:
                    self.store.transition(
                        job_id,
                        {current["state"]},
                        "interrupted",
                        failure_reason="Application shutdown interrupted the active RVE job.",
                        progress_message="Interrupted during application shutdown.",
                    )
                except ValueError:
                    pass
            if owned.process.poll() is None:
                self.group_signaler(owned.pgid, signal.SIGTERM)
        deadline = time.monotonic() + self.cancel_grace_seconds
        for _, owned in owned_jobs:
            remaining = max(0.0, deadline - time.monotonic())
            owned.thread.join(remaining)
            if owned.process.poll() is None:
                self.group_signaler(owned.pgid, signal.SIGKILL)
