import io
import json
import signal
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import rve as rve_api
from app.config import settings
from app.main import app
from app.services.rve_jobs import (
    PROFILE_NAME,
    RVEJobManager,
    RVEJobStore,
    build_rve_command,
    create_rve_job,
    list_local_preparations,
    locked_profile,
    public_job,
    validate_rve_output,
)

client = TestClient(app)


@pytest.fixture
def store(tmp_path):
    job_store = RVEJobStore(tmp_path / "state" / "jobs.sqlite3")
    job_store.initialize()
    return job_store


def job_record(tmp_path, job_id, *, state="created"):
    job_directory = tmp_path / job_id
    job_directory.mkdir(parents=True)
    log_path = job_directory / "job.log"
    log_path.touch()
    return {
        "job_id": job_id,
        "preparation_id": "a" * 32,
        "profile_name": PROFILE_NAME,
        "resolved_backend": "tensorrt",
        "resolved_model": locked_profile()["model_path"],
        "resolved_scale": 2,
        "profile_json": json.dumps(locked_profile(), sort_keys=True),
        "input_path": str(job_directory / "prepared.mkv"),
        "output_path": str(job_directory / "enhanced.mkv"),
        "partial_output_path": str(job_directory / "enhanced.partial.mkv"),
        "job_directory": str(job_directory),
        "input_width": 854,
        "input_height": 480,
        "input_frame_rate": "30000/1001",
        "input_duration_seconds": 10.0,
        "state": state,
        "created_at": "2026-08-18T00:00:00+00:00",
        "started_at": None,
        "finished_at": None,
        "pid": None,
        "pgid": None,
        "exit_code": None,
        "progress_percent": None,
        "progress_message": None,
        "failure_reason": None,
        "cancellation_reason": None,
        "log_path": str(log_path),
        "output_validation_status": None,
        "output_validation_json": None,
    }


def create_preparation_fixture(tmp_path, monkeypatch):
    work_root = tmp_path / "work"
    preparation_id = "b" * 32
    preparation_directory = work_root / preparation_id
    preparation_directory.mkdir(parents=True)
    prepared = preparation_directory / "prepared.mkv"
    prepared.write_bytes(b"prepared")
    plan = {
        "preparation_id": preparation_id,
        "final_prepared_output_path": str(prepared),
        "target_prepared_geometry": {"width": 854, "height": 480},
        "frame_rate": "30000/1001",
        "source_duration_seconds": 10.0,
    }
    (preparation_directory / "plan.json").write_text(json.dumps(plan))
    monkeypatch.setattr(settings, "preparation_work_root", str(work_root), raising=False)
    return work_root, preparation_id, prepared


def wait_for_state(store, job_id, terminal=True, timeout=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = store.get(job_id)
        if (job["state"] in {"completed", "failed", "cancelled", "interrupted"}) == terminal:
            return job
        time.sleep(0.01)
    raise AssertionError(f"Job did not reach expected state: {store.get(job_id)}")


def test_locked_profile_and_command_are_exact_and_not_browser_controlled(tmp_path):
    record = job_record(tmp_path, "1" * 32)
    command = build_rve_command(record)
    assert locked_profile()["backend"] == "tensorrt"
    assert locked_profile()["model_family"] == "Nomos8k Realistic Medium"
    assert locked_profile()["scale"] == 2
    assert locked_profile()["interpolation"] is False
    assert locked_profile()["decompression"] is False
    assert locked_profile()["denoise"] is False
    assert command[0] == str(Path(settings.rve_python).resolve())
    assert command[1] == str(Path(settings.rve_backend).resolve())
    assert command[command.index("--backend") + 1] == "tensorrt"
    assert command[command.index("--upscale_model") + 1] == locked_profile()["model_path"]
    assert command[command.index("--override_upscale_scale") + 1] == "2"
    assert command[command.index("--interpolate_factor") + 1] == "1"
    assert "--interpolate_model" not in command
    assert "--extra_restoration_models" not in command
    assert "--overwrite" not in command


def test_stored_profile_substitution_is_rejected(tmp_path):
    record = job_record(tmp_path, "2" * 32)
    profile = json.loads(record["profile_json"])
    profile["backend"] = "pytorch"
    record["profile_json"] = json.dumps(profile, sort_keys=True)
    with pytest.raises(ValueError, match="locked enhancement"):
        build_rve_command(record)


def test_create_job_accepts_only_validator_pass_preparation(tmp_path, monkeypatch, store):
    work_root, preparation_id, prepared = create_preparation_fixture(tmp_path, monkeypatch)
    job = create_rve_job(
        preparation_id,
        store,
        work_root=work_root,
        verify_runtime=False,
        validator=lambda path, plan: {"outcome": "PASS"},
    )
    assert job["state"] == "created"
    assert job["input_path"] == str(prepared)
    assert Path(job["output_path"]).is_relative_to(work_root)
    assert public_job(job)["local_artifact_identity"] is None
    listed = list_local_preparations(
        work_root=work_root,
        validator=lambda path, plan: {"outcome": "PASS", "reasons": ["valid"]},
    )
    assert listed == [
        {
            "preparation_id": preparation_id,
            "source_relative_path": None,
            "prepared_geometry": {"width": 854, "height": 480},
            "validation_status": "PASS",
            "available_for_rve": True,
            "reason": "valid",
        }
    ]


@pytest.mark.parametrize("outcome", ["FAIL", "WARNING / REVIEW REQUIRED"])
def test_create_job_rejects_non_pass_preparation(tmp_path, monkeypatch, store, outcome):
    work_root, preparation_id, _ = create_preparation_fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="must pass"):
        create_rve_job(
            preparation_id,
            store,
            work_root=work_root,
            verify_runtime=False,
            validator=lambda path, plan: {"outcome": outcome},
        )


def test_missing_or_partial_preparation_is_rejected(tmp_path, monkeypatch, store):
    work_root, preparation_id, prepared = create_preparation_fixture(tmp_path, monkeypatch)
    prepared.unlink()
    partial = prepared.with_name("prepared.partial.mkv")
    partial.write_bytes(b"partial")
    with pytest.raises(ValueError, match="must pass"):
        create_rve_job(
            preparation_id,
            store,
            work_root=work_root,
            verify_runtime=False,
            validator=lambda path, plan: {"outcome": "PASS" if path.is_file() else "FAIL"},
        )
    with pytest.raises(FileNotFoundError):
        create_rve_job(
            "c" * 32,
            store,
            work_root=work_root,
            verify_runtime=False,
            validator=lambda path, plan: {"outcome": "PASS"},
        )


def test_job_record_is_durable_across_store_reopen(tmp_path, store):
    record = job_record(tmp_path, "3" * 32)
    store.insert(record)
    reopened = RVEJobStore(store.database_path)
    assert reopened.get(record["job_id"])["profile_name"] == PROFILE_NAME


def test_state_machine_blocks_restart_of_terminal_job(tmp_path, store):
    record = job_record(tmp_path, "4" * 32)
    store.insert(record)
    store.claim(record["job_id"])
    store.transition(record["job_id"], {"running"}, "completed")
    with pytest.raises(ValueError, match="cannot start"):
        store.claim(record["job_id"])


def test_single_active_job_claim_is_transactional(tmp_path, store):
    first = job_record(tmp_path / "one", "5" * 32)
    second = job_record(tmp_path / "two", "6" * 32)
    store.insert(first)
    store.insert(second)
    barrier = threading.Barrier(3)
    outcomes = []

    def claim(job_id):
        barrier.wait()
        try:
            store.claim(job_id)
            outcomes.append("claimed")
        except RuntimeError:
            outcomes.append("conflict")

    threads = [
        threading.Thread(target=claim, args=(first["job_id"],)),
        threading.Thread(target=claim, args=(second["job_id"],)),
    ]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == ["claimed", "conflict"]


class ImmediateProcess:
    def __init__(self, command, output=b"", returncode=0):
        self.pid = 1234
        self.stdout = io.BytesIO(output)
        self.returncode = returncode
        Path(command[command.index("-o") + 1]).write_bytes(b"enhanced")

    def poll(self):
        return self.returncode

    def wait(self):
        return self.returncode


def test_process_launch_progress_and_valid_completion(tmp_path, store):
    record = job_record(tmp_path, "7" * 32)
    store.insert(record)
    captured = {}

    def popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return ImmediateProcess(
            command,
            b"BACKEND: Rendering\rFPS: 12 Current Frame: 150 ETA: 0:00:12BACKEND: done\r",
        )

    manager = RVEJobManager(
        store,
        popen_factory=popen,
        pgid_resolver=lambda pid: 4321,
        output_validator=lambda path, job: {"outcome": "PASS", "checks": []},
    )
    manager.start(record["job_id"])
    completed = wait_for_state(store, record["job_id"])
    assert completed["state"] == "completed"
    assert completed["progress_percent"] == 100.0
    assert completed["output_validation_status"] == "PASS"
    assert Path(completed["output_path"]).is_file()
    assert captured["kwargs"]["shell"] is False
    assert captured["kwargs"]["start_new_session"] is True
    assert Path(captured["kwargs"]["cwd"]) == Path(settings.rve_root).resolve()
    assert "REAL-Video-Enhancer" not in captured["command"]
    assert "Current Frame: 150" in Path(completed["log_path"]).read_text()
    assert "BACKEND:" not in completed["progress_message"]


@pytest.mark.parametrize(
    ("returncode", "validation", "reason"),
    [
        (1, {"outcome": "PASS"}, "exited with code"),
        (0, {"outcome": "FAIL"}, "failed bounded"),
    ],
)
def test_failed_backend_or_validation_never_completes(
    tmp_path, store, returncode, validation, reason
):
    record = job_record(tmp_path, uuid_for(returncode, validation["outcome"]))
    store.insert(record)
    manager = RVEJobManager(
        store,
        popen_factory=lambda command, **kwargs: ImmediateProcess(command, returncode=returncode),
        pgid_resolver=lambda pid: 4321,
        output_validator=lambda path, job: validation,
    )
    manager.start(record["job_id"])
    failed = wait_for_state(store, record["job_id"])
    assert failed["state"] == "failed"
    assert reason in failed["failure_reason"]


def uuid_for(returncode, outcome):
    return ("8" if returncode else "9") * 32


class BlockingProcess:
    def __init__(self, command):
        self.pid = 2345
        self.stdout = self
        self.returncode = None
        self.partial_path = Path(command[command.index("-o") + 1])

    def read(self, size):
        time.sleep(0.01)
        return b""

    def poll(self):
        return self.returncode

    def wait(self):
        while self.returncode is None:
            time.sleep(0.01)
        return self.returncode


def test_cancellation_targets_only_live_owned_group_and_cannot_complete(tmp_path, store):
    record = job_record(tmp_path, "a" * 32)
    store.insert(record)
    process_holder = {}
    signals = []

    def popen(command, **kwargs):
        process_holder["process"] = BlockingProcess(command)
        return process_holder["process"]

    def signal_group(pgid, sent_signal):
        signals.append((pgid, sent_signal))
        process_holder["process"].returncode = -sent_signal

    manager = RVEJobManager(
        store,
        popen_factory=popen,
        pgid_resolver=lambda pid: 9876,
        group_signaler=signal_group,
        cancel_grace_seconds=0.05,
    )
    manager.start(record["job_id"])
    deadline = time.monotonic() + 1
    while store.get(record["job_id"])["pgid"] is None and time.monotonic() < deadline:
        time.sleep(0.01)
    requested = manager.cancel(record["job_id"])
    assert requested["state"] == "cancel_requested"
    cancelled = wait_for_state(store, record["job_id"])
    assert cancelled["state"] == "cancelled"
    assert signals == [(9876, signal.SIGTERM)]
    assert cancelled["pid"] is None
    assert cancelled["pgid"] is None


def test_stale_pid_is_not_signaled_and_becomes_interrupted(tmp_path, store):
    record = job_record(tmp_path, "d" * 32)
    store.insert(record)
    store.claim(record["job_id"])
    store.update(record["job_id"], pid=999, pgid=999)
    signals = []
    manager = RVEJobManager(store, group_signaler=lambda pgid, sent_signal: signals.append((pgid, sent_signal)))
    result = manager.cancel(record["job_id"])
    assert result["state"] == "interrupted"
    assert signals == []


def test_restart_reconciliation_marks_active_jobs_interrupted_without_signals(tmp_path, store):
    record = job_record(tmp_path, "e" * 32)
    store.insert(record)
    store.claim(record["job_id"])
    store.update(record["job_id"], pid=999, pgid=999)
    assert store.reconcile_interrupted() == 1
    reconciled = store.get(record["job_id"])
    assert reconciled["state"] == "interrupted"
    assert reconciled["pid"] is None
    assert "automatic process reattachment" in reconciled["failure_reason"]


def test_rve_output_validation_checks_geometry_rate_and_duration(tmp_path, monkeypatch):
    output = tmp_path / "enhanced.partial.mkv"
    output.write_bytes(b"video")
    monkeypatch.setattr(
        "app.services.rve_jobs.probe_media",
        lambda path: {
            "status": "ok",
            "duration_seconds": 10.0,
            "video_stream": {
                "width": 1708,
                "height": 960,
                "avg_frame_rate": "30000/1001",
            },
        },
    )
    result = validate_rve_output(
        output,
        {
            "input_width": 854,
            "input_height": 480,
            "input_frame_rate": "30000/1001",
            "input_duration_seconds": 10.0,
        },
    )
    assert result["outcome"] == "PASS"


def test_api_create_start_status_cancel_and_rejects_profile_override(monkeypatch, tmp_path):
    record = job_record(tmp_path, "f" * 32)

    class FakeStore:
        def get(self, job_id):
            if job_id == "not-a-job":
                raise ValueError("Invalid RVE job identifier.")
            if job_id != record["job_id"]:
                raise FileNotFoundError("RVE job was not found.")
            return record

    class FakeManager:
        def start(self, job_id):
            return record

        def cancel(self, job_id):
            cancelled = dict(record)
            cancelled["state"] = "cancelled"
            return cancelled

    monkeypatch.setattr(rve_api, "create_rve_job", lambda preparation_id, store: record)
    monkeypatch.setattr(
        rve_api,
        "list_local_preparations",
        lambda: [{"preparation_id": "a" * 32, "available_for_rve": True}],
    )
    app.state.rve_store = FakeStore()
    app.state.rve_manager = FakeManager()
    create_response = client.post("/api/rve/jobs", json={"preparation_id": "a" * 32})
    assert create_response.status_code == 200
    assert create_response.json()["profile"]["name"] == PROFILE_NAME
    assert client.get("/api/rve/preparations").status_code == 200
    assert client.post(f"/api/rve/jobs/{record['job_id']}/start").status_code == 200
    assert client.get(f"/api/rve/jobs/{record['job_id']}").status_code == 200
    assert client.post(f"/api/rve/jobs/{record['job_id']}/cancel").status_code == 200
    override = client.post(
        "/api/rve/jobs",
        json={"preparation_id": "a" * 32, "model": "unapproved", "scale": 4},
    )
    assert override.status_code == 422
    assert client.get("/api/rve/jobs/not-a-job").status_code == 422


def test_media_page_contains_minimal_rve_workflow():
    response = client.get("/media")
    assert response.status_code == 200
    assert "Create RVE Job" in response.text
    assert "Start Enhancement" in response.text
    assert "Cancel Enhancement" in response.text
    assert "setInterval(refreshRveJob" in response.text
    assert "/api/rve/preparations" in response.text
