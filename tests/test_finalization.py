import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services.finalization import (
    OUTPUT_SUFFIX,
    FinalizationService,
    FinalizationStore,
    build_final_remux_command,
    generated_filename,
    publication_root_status,
    suggest_movie_title,
    validate_final_output,
    validate_movie_title,
)
from app.services.finalization import _atomic_rename_noreplace
from app.services.operator_state import OperatorStateStore
from app.services.rve_jobs import PROFILE_NAME, RVEJobStore, locked_profile

client = TestClient(app)


def valid_probe():
    return {
        "status": "ok",
        "duration_seconds": 100.0,
        "video_stream": {
            "codec": "h264",
            "width": 1708,
            "height": 960,
            "sample_aspect_ratio": "1:1",
            "pixel_format": "yuv420p",
            "field_order": "progressive",
            "avg_frame_rate": "30000/1001",
            "r_frame_rate": "30000/1001",
        },
        "audio_streams": [{"codec": "ac3"}],
        "subtitle_streams": [{"codec": "subrip"}],
        "attachment_streams": [],
        "chapter_count": 32,
        "chapters": [{"title": f"Chapter {number:02d}"} for number in range(1, 33)],
    }


@pytest.fixture
def finalization_environment(tmp_path, monkeypatch):
    movies = tmp_path / "movies"
    source_root = movies / "DVD Originals"
    destination_root = movies / "DVD Upscaled"
    source_root.mkdir(parents=True)
    source = source_root / "Ratatouille" / "Ratatouille - DVD Original.mkv"
    source.parent.mkdir()
    source.write_bytes(b"original")
    destination_root.mkdir()
    work_root = tmp_path / "work"
    database = tmp_path / "state" / "app.sqlite3"

    monkeypatch.setattr(settings, "trusted_nas_movies_root", str(movies))
    monkeypatch.setattr(settings, "dvd_source_root", str(source_root))
    monkeypatch.setattr(settings, "preparation_work_root", str(work_root))
    monkeypatch.setattr(settings, "rve_state_database", str(database))
    monkeypatch.setattr(settings, "publication_root", str(tmp_path / "publication"))

    operator_store = OperatorStateStore(database)
    operator_store.initialize()
    source_location = operator_store.list_locations(role="ORIGINAL_SOURCE")[0]
    destination = operator_store.create_location(
        "DVD Upscaled",
        "FINISHED_DESTINATION",
        "DVD Upscaled",
    )
    workflow = operator_store.create_workflow(
        source_location["location_id"],
        "Ratatouille/Ratatouille - DVD Original.mkv",
    )
    workflow = operator_store.set_destination(
        workflow["workflow_id"],
        destination["location_id"],
    )

    preparation_id = "a" * 32
    preparation_directory = work_root / preparation_id
    preparation_directory.mkdir(parents=True)
    prepared = preparation_directory / "prepared.mkv"
    prepared.write_bytes(b"prepared")
    source_stat = source.stat()
    plan = {
        "preparation_id": preparation_id,
        "workflow_id": workflow["workflow_id"],
        "source_location_id": source_location["location_id"],
        "destination_location_id": destination["location_id"],
        "source_root": str(source_root.resolve()),
        "source_relative_path": "Ratatouille/Ratatouille - DVD Original.mkv",
        "source_size_bytes": source_stat.st_size,
        "source_mtime_ns": source_stat.st_mtime_ns,
        "final_prepared_output_path": str(prepared),
        "target_prepared_geometry": {"width": 854, "height": 480},
        "frame_rate": "30000/1001",
        "source_duration_seconds": 100.0,
    }
    (preparation_directory / "plan.json").write_text(json.dumps(plan))
    workflow = operator_store.associate_preparation(
        workflow["workflow_id"],
        preparation_id,
    )

    rve_store = RVEJobStore(database)
    rve_store.initialize()
    job_id = "b" * 32
    job_directory = preparation_directory / "rve" / job_id
    job_directory.mkdir(parents=True)
    enhanced = job_directory / "enhanced.mkv"
    enhanced.write_bytes(b"enhanced")
    log = job_directory / "job.log"
    log.touch()
    profile = locked_profile()
    rve_store.insert(
        {
            "job_id": job_id,
            "preparation_id": preparation_id,
            "profile_name": PROFILE_NAME,
            "resolved_backend": profile["backend"],
            "resolved_model": profile["model_path"],
            "resolved_scale": profile["scale"],
            "profile_json": json.dumps(profile, sort_keys=True),
            "input_path": str(prepared),
            "output_path": str(enhanced),
            "partial_output_path": str(job_directory / "enhanced.partial.mkv"),
            "job_directory": str(job_directory),
            "input_width": 854,
            "input_height": 480,
            "input_frame_rate": "30000/1001",
            "input_duration_seconds": 100.0,
            "state": "completed",
            "created_at": "2026-08-18T00:00:00+00:00",
            "started_at": "2026-08-18T00:00:01+00:00",
            "finished_at": "2026-08-18T00:01:00+00:00",
            "pid": None,
            "pgid": None,
            "exit_code": 0,
            "progress_percent": 100.0,
            "progress_message": "Complete",
            "failure_reason": None,
            "cancellation_reason": None,
            "log_path": str(log),
            "output_validation_status": "PASS",
            "output_validation_json": json.dumps({"outcome": "PASS"}),
        }
    )
    workflow = operator_store.associate_rve_job(preparation_id, job_id)

    finalization_store = FinalizationStore(database)
    finalization_store.initialize()
    service = FinalizationService(
        finalization_store,
        operator_store,
        rve_store,
        work_root=work_root,
        prepared_validator=lambda path, stored_plan: {"outcome": "PASS"},
        rve_validator=lambda path, job: {"outcome": "PASS", "probe": valid_probe()},
        verify_runtime=False,
    )
    return {
        "service": service,
        "store": finalization_store,
        "operator_store": operator_store,
        "rve_store": rve_store,
        "workflow": workflow,
        "plan": plan,
        "work_root": work_root,
        "database": database,
    }


def test_title_suggestion_and_profile_owned_generated_name():
    assert suggest_movie_title("Ratatouille - DVD Original.mkv") == "Ratatouille"
    assert suggest_movie_title("Ratatouille/D2_t00.mkv") == "Ratatouille"
    assert suggest_movie_title("SomeMovie.mkv") == "SomeMovie"
    assert generated_filename("Edited Title") == f"Edited Title - {OUTPUT_SUFFIX}.mkv"


@pytest.mark.parametrize(
    "title",
    ["", ".", "..", "../escape", "/absolute", r"nested\movie", "bad:name", "CON"],
)
def test_unsafe_movie_titles_are_rejected(title):
    with pytest.raises(ValueError):
        validate_movie_title(title)


def test_remux_command_uses_single_rve_input_explicit_maps_and_stream_copy(tmp_path):
    command = build_final_remux_command(tmp_path / "enhanced.mkv", tmp_path / "final.partial.mkv")
    assert command.count("-i") == 1
    assert [command[index + 1] for index, value in enumerate(command) if value == "-map"] == [
        "0:v:0",
        "0:a?",
        "0:s?",
        "0:t?",
    ]
    assert command[command.index("-map_metadata") + 1] == "0"
    assert command[command.index("-map_chapters") + 1] == "0"
    assert command[command.index("-c") + 1] == "copy"
    assert "-y" not in command
    assert not any("nvenc" in argument for argument in command)


def test_authoritative_completed_workflow_creates_durable_record(finalization_environment):
    environment = finalization_environment
    record = environment["service"].create(
        environment["workflow"]["workflow_id"],
        "Ratatouille",
    )
    reopened = FinalizationStore(environment["database"])
    persisted = reopened.get(record["finalization_id"])
    assert persisted["state"] == "created"
    assert persisted["final_filename"] == "Ratatouille - DVD RVE Nomos8k Medium 2x.mkv"
    assert persisted["workflow_id"] == environment["workflow"]["workflow_id"]


def test_explicit_historical_adoption_persists_and_allows_finalization(
    finalization_environment,
):
    environment = finalization_environment
    original_workflow_id = environment["workflow"]["workflow_id"]
    with environment["operator_store"]._connect() as connection:
        connection.execute(
            """
            UPDATE operator_workflows
            SET preparation_id = NULL, rve_job_id = NULL
            WHERE workflow_id = ?
            """,
            (original_workflow_id,),
        )
    plan_path = environment["work_root"] / ("a" * 32) / "plan.json"
    plan = json.loads(plan_path.read_text())
    for key in ("workflow_id", "source_location_id", "destination_location_id", "source_root"):
        plan.pop(key, None)
    plan["source_absolute_path"] = "/historical/DVD/Ratatouille - DVD Original.mkv"
    plan["source_relative_path"] = "Historical/Ratatouille - DVD Original.mkv"
    plan_path.write_text(json.dumps(plan))

    source_location = environment["operator_store"].list_locations(
        role="ORIGINAL_SOURCE",
        enabled=True,
    )[0]
    destination = environment["operator_store"].get_location(
        environment["workflow"]["destination_location_id"],
    )
    adopted = environment["service"].adopt_historical_workflow(
        source_location_id=source_location["location_id"],
        source_relative_path="Ratatouille/Ratatouille - DVD Original.mkv",
        destination_location_id=destination["location_id"],
        preparation_id="a" * 32,
        rve_job_id="b" * 32,
    )

    reopened = OperatorStateStore(environment["database"])
    persisted = reopened.get_workflow(adopted["workflow_id"])
    evidence = reopened.get_historical_workflow_adoption(adopted["workflow_id"])
    assert persisted["source_relative_path"] == "Ratatouille/Ratatouille - DVD Original.mkv"
    assert persisted["destination_location_name"] == "DVD Upscaled"
    assert persisted["preparation_id"] == "a" * 32
    assert persisted["rve_job_id"] == "b" * 32
    assert evidence["historical_source_relative_path"] == (
        "Historical/Ratatouille - DVD Original.mkv"
    )
    assert environment["service"].preview(adopted["workflow_id"])["ready"] is True


def test_historical_adoption_rejects_source_identity_mismatch(finalization_environment):
    environment = finalization_environment
    with environment["operator_store"]._connect() as connection:
        connection.execute(
            """
            UPDATE operator_workflows
            SET preparation_id = NULL, rve_job_id = NULL
            WHERE workflow_id = ?
            """,
            (environment["workflow"]["workflow_id"],),
        )
    plan_path = environment["work_root"] / ("a" * 32) / "plan.json"
    plan = json.loads(plan_path.read_text())
    plan["source_size_bytes"] += 1
    plan_path.write_text(json.dumps(plan))
    source_location = environment["operator_store"].list_locations(
        role="ORIGINAL_SOURCE",
        enabled=True,
    )[0]

    with pytest.raises(ValueError, match="Relocated source identity"):
        environment["service"].adopt_historical_workflow(
            source_location_id=source_location["location_id"],
            source_relative_path="Ratatouille/Ratatouille - DVD Original.mkv",
            destination_location_id=environment["workflow"]["destination_location_id"],
            preparation_id="a" * 32,
            rve_job_id="b" * 32,
        )


@pytest.mark.parametrize("state", ["created", "running", "failed", "cancelled", "interrupted"])
def test_non_completed_rve_job_is_rejected(finalization_environment, state):
    environment = finalization_environment
    with environment["rve_store"]._connect() as connection:
        connection.execute("UPDATE rve_jobs SET state = ? WHERE job_id = ?", (state, "b" * 32))
    with pytest.raises(ValueError, match="completed locked-profile PASS"):
        environment["service"].create(
            environment["workflow"]["workflow_id"],
            "Ratatouille",
        )


def test_missing_or_failed_upstream_authority_is_rejected(finalization_environment):
    environment = finalization_environment
    workflow_id = environment["workflow"]["workflow_id"]
    with environment["operator_store"]._connect() as connection:
        connection.execute(
            "UPDATE operator_workflows SET preparation_id = NULL WHERE workflow_id = ?",
            (workflow_id,),
        )
    with pytest.raises(ValueError, match="no authoritative preparation"):
        environment["service"].create(workflow_id, "Ratatouille")


def test_current_validator_failures_block_finalization_input(finalization_environment):
    environment = finalization_environment
    service = FinalizationService(
        environment["store"],
        environment["operator_store"],
        environment["rve_store"],
        work_root=environment["work_root"],
        prepared_validator=lambda path, plan: {"outcome": "FAIL"},
        rve_validator=lambda path, job: {"outcome": "PASS", "probe": valid_probe()},
        verify_runtime=False,
    )
    with pytest.raises(ValueError, match="current validator PASS"):
        service.create(environment["workflow"]["workflow_id"], "Ratatouille")


def test_missing_rve_association_and_current_rve_fail_are_rejected(
    finalization_environment,
):
    environment = finalization_environment
    workflow_id = environment["workflow"]["workflow_id"]
    with environment["operator_store"]._connect() as connection:
        connection.execute(
            "UPDATE operator_workflows SET rve_job_id = NULL WHERE workflow_id = ?",
            (workflow_id,),
        )
    with pytest.raises(ValueError, match="no authoritative RVE job"):
        environment["service"].create(workflow_id, "Ratatouille")

    with environment["operator_store"]._connect() as connection:
        connection.execute(
            "UPDATE operator_workflows SET rve_job_id = ? WHERE workflow_id = ?",
            ("b" * 32, workflow_id),
        )
    environment["service"].rve_validator = lambda path, job: {"outcome": "FAIL"}
    with pytest.raises(ValueError, match="current validator PASS"):
        environment["service"].create(workflow_id, "Ratatouille")


def test_disabled_or_nonapproved_destination_is_rejected(finalization_environment):
    environment = finalization_environment
    destination_id = environment["workflow"]["destination_location_id"]
    environment["operator_store"].update_location(destination_id, enabled=False)
    with pytest.raises(ValueError, match="disabled"):
        environment["service"].create(
            environment["workflow"]["workflow_id"],
            "Ratatouille",
        )


def test_finalize_validates_partial_before_promoting(finalization_environment):
    environment = finalization_environment
    calls = []

    def runner(command, **kwargs):
        Path(command[-1]).write_bytes(b"final")
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    def validator(path, expected, **kwargs):
        calls.append(path.name)
        assert path.name == "final.partial.mkv"
        return {"outcome": "PASS", "checks": []}

    environment["service"].runner = runner
    environment["service"].final_validator = validator
    record = environment["service"].create(
        environment["workflow"]["workflow_id"],
        "Ratatouille",
    )
    result = environment["service"].finalize(record["finalization_id"])
    assert result["state"] == "finalized"
    assert Path(result["local_final_path"]).read_bytes() == b"final"
    assert not Path(result["local_partial_path"]).exists()
    assert calls == ["final.partial.mkv"]


def test_failed_final_validation_never_promotes(finalization_environment):
    environment = finalization_environment

    def runner(command, **kwargs):
        Path(command[-1]).write_bytes(b"bad")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    environment["service"].runner = runner
    environment["service"].final_validator = lambda path, expected: {"outcome": "FAIL"}
    record = environment["service"].create(
        environment["workflow"]["workflow_id"],
        "Ratatouille",
    )
    result = environment["service"].finalize(record["finalization_id"])
    assert result["state"] == "failed"
    assert not Path(result["local_final_path"]).exists()
    assert Path(result["local_partial_path"]).exists()


def test_final_validator_checks_streams_geometry_and_timing(tmp_path, monkeypatch):
    output = tmp_path / "final.mkv"
    output.write_bytes(b"final")
    monkeypatch.setattr("app.services.finalization.probe_media", lambda path: valid_probe())
    assert validate_final_output(output, valid_probe())["outcome"] == "PASS"
    wrong = valid_probe()
    wrong["chapter_count"] = 31
    result = validate_final_output(output, wrong)
    assert result["outcome"] == "FAIL"
    assert "chapter_count" in result["reasons"][0]


def test_final_validator_checks_stream_identity_and_chapter_title_order(tmp_path, monkeypatch):
    output = tmp_path / "final.mkv"
    output.write_bytes(b"final")
    actual = valid_probe()
    monkeypatch.setattr("app.services.finalization.probe_media", lambda path: actual)

    wrong_audio = valid_probe()
    wrong_audio["audio_streams"][0]["codec"] = "aac"
    result = validate_final_output(output, wrong_audio)
    assert result["outcome"] == "FAIL"
    assert "audio_stream_inventory" in result["reasons"][0]

    wrong_chapters = valid_probe()
    wrong_chapters["chapters"][0], wrong_chapters["chapters"][1] = (
        wrong_chapters["chapters"][1],
        wrong_chapters["chapters"][0],
    )
    result = validate_final_output(output, wrong_chapters)
    assert result["outcome"] == "FAIL"
    assert "chapter_title_order" in result["reasons"][0]


def _make_finalized(environment):
    record = environment["service"].create(
        environment["workflow"]["workflow_id"],
        "Ratatouille",
    )
    local_final = Path(record["local_final_path"])
    local_final.write_bytes(b"validated-final")
    return environment["store"].transition(
        record["finalization_id"],
        {"created"},
        "finalized",
        finalized_at="2026-08-18T00:00:00+00:00",
        final_validation_status="PASS",
        final_validation_json=json.dumps({"outcome": "PASS"}),
    )


def test_publication_is_unavailable_without_distinct_narrow_mount(finalization_environment):
    environment = finalization_environment
    record = _make_finalized(environment)
    with pytest.raises(RuntimeError, match="narrow publication mount is absent"):
        environment["service"].publish(record["finalization_id"])
    assert environment["store"].get(record["finalization_id"])["state"] == "finalized"
    assert not Path(settings.publication_root).exists()


def test_publication_collision_preserves_existing_file(finalization_environment):
    environment = finalization_environment
    publication = Path(settings.publication_root)
    publication.mkdir()
    existing = publication / "Ratatouille - DVD RVE Nomos8k Medium 2x.mkv"
    existing.write_bytes(b"existing")
    environment["service"].publication_checker = lambda: {"available": True}
    record = _make_finalized(environment)
    with pytest.raises(FileExistsError, match="already exists"):
        environment["service"].publish(record["finalization_id"])
    assert existing.read_bytes() == b"existing"
    assert environment["store"].get(record["finalization_id"])["state"] == "finalized"


def test_staged_publication_validates_then_atomically_promotes(finalization_environment):
    environment = finalization_environment
    publication = Path(settings.publication_root)
    publication.mkdir()
    observations = []

    def validator(path, expected, **kwargs):
        observations.append(path.name)
        return {"outcome": "PASS", "checks": []}

    def promoter(source, destination):
        assert source.name.startswith(".Ratatouille")
        assert not destination.exists()
        source.rename(destination)

    environment["service"].publication_checker = lambda: {"available": True}
    environment["service"].final_validator = validator
    environment["service"].promoter = promoter
    record = _make_finalized(environment)
    result = environment["service"].publish(record["finalization_id"])
    target = publication / record["final_filename"]
    assert result["state"] == "published"
    assert target.read_bytes() == b"validated-final"
    assert observations == [
        f".{target.name}.{record['finalization_id']}.partial.mkv",
        target.name,
    ]
    assert not list(publication.glob(".*.partial.mkv"))


def test_failed_publication_candidate_is_cleaned_without_exposing_final_name(
    finalization_environment,
):
    environment = finalization_environment
    publication = Path(settings.publication_root)
    publication.mkdir()
    environment["service"].publication_checker = lambda: {"available": True}
    environment["service"].final_validator = lambda path, expected, **kwargs: {
        "outcome": "FAIL",
        "checks": [],
    }
    record = _make_finalized(environment)
    result = environment["service"].publish(record["finalization_id"])
    assert result["state"] == "failed"
    assert result["publication_validation_status"] == "FAIL"
    assert not any(publication.iterdir())
    assert Path(record["local_final_path"]).read_bytes() == b"validated-final"


def test_publication_cleanup_failure_still_records_failed_state(
    finalization_environment,
    monkeypatch,
):
    environment = finalization_environment
    publication = Path(settings.publication_root)
    publication.mkdir()
    environment["service"].publication_checker = lambda: {"available": True}
    record = _make_finalized(environment)
    environment["service"].final_validator = lambda path, expected, **kwargs: (
        {"outcome": "PASS"}
        if ".partial.mkv" in path.name
        else {"outcome": "FAIL"}
    )
    environment["service"].promoter = lambda source, destination: source.rename(destination)
    original_unlink = Path.unlink

    def failing_unlink(path, *args, **kwargs):
        if path.name == record["final_filename"]:
            raise OSError("simulated NAS cleanup failure")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", failing_unlink)
    result = environment["service"].publish(record["finalization_id"])

    assert result["state"] == "failed"
    assert "promoted publication cleanup failed" in result["failure_reason"]
    assert (publication / record["final_filename"]).is_file()


def test_interrupted_active_state_is_durably_failed(finalization_environment):
    environment = finalization_environment
    record = environment["service"].create(
        environment["workflow"]["workflow_id"],
        "Ratatouille",
    )
    environment["store"].transition(record["finalization_id"], {"created"}, "finalizing")
    reopened = FinalizationStore(environment["database"])
    assert reopened.reconcile_interrupted() == 1
    result = reopened.get(record["finalization_id"])
    assert result["state"] == "failed"
    assert "automatic retry" in result["failure_reason"]


def test_publication_root_must_be_exact_distinct_writable_nas_mount(tmp_path, monkeypatch):
    publication = tmp_path / "publication"
    publication.mkdir()
    movies = tmp_path / "movies"
    movies.mkdir()
    monkeypatch.setattr("app.services.finalization.os.access", lambda path, mode: True)
    values = {
        "TARGET": str(publication),
        "SOURCE": "//nas/Movies/DVD Upscaled",
        "FSTYPE": "cifs",
        "OPTIONS": "rw,nosuid",
    }

    def runner(command, **kwargs):
        return SimpleNamespace(returncode=0, stdout=values[command[-1]], stderr="")

    assert publication_root_status(root=publication, movies_root=movies, runner=runner)[
        "available"
    ]
    values["TARGET"] = str(tmp_path)
    assert not publication_root_status(root=publication, movies_root=movies, runner=runner)[
        "available"
    ]
    values["TARGET"] = str(publication)
    values["SOURCE"] = "//nas/Movies"
    assert not publication_root_status(root=publication, movies_root=movies, runner=runner)[
        "available"
    ]
    assert not publication_root_status(
        root=movies,
        movies_root=movies,
        runner=runner,
    )["available"]


def test_publication_root_uses_backing_cifs_row_after_autofs_activation(tmp_path, monkeypatch):
    publication = tmp_path / "publication"
    publication.mkdir()
    movies = tmp_path / "movies"
    movies.mkdir()
    accessed = []

    def access_guard(path, mode):
        accessed.append((str(path), mode))
        return True

    monkeypatch.setattr("app.services.finalization.os.access", access_guard)
    values = {
        "TARGET": f"{publication}\n{publication}",
        "SOURCE": "systemd-1\n//nas/Movies/DVD Upscaled",
        "FSTYPE": "autofs\ncifs",
        "OPTIONS": "rw,nosuid\nrw,vers=3.0,credentials=dvd-rve-publisher",
    }

    def runner(command, **kwargs):
        return SimpleNamespace(returncode=0, stdout=values[command[-1]], stderr="")

    status = publication_root_status(root=publication, movies_root=movies, runner=runner)
    assert status["available"] is True
    assert status["filesystem"] == "cifs"
    assert accessed
    assert not publication_root_status(
        root=publication,
        movies_root=movies,
        runner=lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="systemd-1\n",
            stderr="",
        ),
    )["available"]


def test_atomic_promotion_never_replaces_existing_file(tmp_path):
    source = tmp_path / "candidate"
    destination = tmp_path / "final"
    source.write_bytes(b"candidate")
    _atomic_rename_noreplace(source, destination)
    assert destination.read_bytes() == b"candidate"
    second = tmp_path / "second"
    second.write_bytes(b"second")
    with pytest.raises(FileExistsError):
        _atomic_rename_noreplace(second, destination)
    assert destination.read_bytes() == b"candidate"
    assert second.read_bytes() == b"second"


def test_finalization_api_rejects_browser_paths_and_reports_absent_mount(
    finalization_environment, monkeypatch
):
    environment = finalization_environment
    monkeypatch.setattr(app.state, "finalization_store", environment["store"], raising=False)
    monkeypatch.setattr(
        app.state,
        "finalization_service",
        environment["service"],
        raising=False,
    )
    workflow_id = environment["workflow"]["workflow_id"]
    override = client.post(
        f"/api/workflows/{workflow_id}/finalization",
        json={"movie_title": "Ratatouille", "destination_path": "/mnt/nas/movies"},
    )
    assert override.status_code == 422
    preview = client.get(f"/api/workflows/{workflow_id}/finalization")
    assert preview.status_code == 200
    assert preview.json()["publication"]["available"] is False


def test_browser_exposes_continuous_explicit_finalization_workflow():
    page = client.get("/media")
    assert page.status_code == 200
    for text in (
        "Finalize &amp; Publish",
        "Product Owner action is required",
        "Finalize Local MKV",
        "Publish to",
        "No completion percentage is estimated",
        "Start New Movie",
        "/api/finalizations/",
    ):
        assert text in page.text
