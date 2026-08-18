import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services.media_discovery import discover_candidates_across_locations
from app.services.operator_state import (
    OperatorStateStore,
    public_location,
    public_workflow,
    validate_destination_subfolder,
)
from app.services.system_telemetry import (
    TelemetryService,
    calculate_cpu_utilization,
    parse_cpu_stat,
    parse_nvidia_smi_csv,
    parse_sensors_temperature,
)

client = TestClient(app)


@pytest.fixture
def library_store(tmp_path, monkeypatch):
    movies = tmp_path / "movies"
    intake = movies / "DVD"
    intake.mkdir(parents=True)
    monkeypatch.setattr(settings, "trusted_nas_movies_root", str(movies))
    monkeypatch.setattr(settings, "dvd_source_root", str(intake))
    database = tmp_path / "state" / "app.sqlite3"
    store = OperatorStateStore(database)
    store.initialize()
    return store, movies, intake, database


def test_initial_source_adoption_is_stable_and_persistent(library_store):
    store, _, intake, database = library_store
    initial = store.list_locations(role="ORIGINAL_SOURCE")
    assert len(initial) == 1
    assert initial[0]["display_name"] == "DVD Intake"
    assert initial[0]["server_root"] == str(intake.resolve())

    reopened = OperatorStateStore(database)
    reopened.initialize()
    again = reopened.list_locations(role="ORIGINAL_SOURCE")
    assert len(again) == 1
    assert again[0]["location_id"] == initial[0]["location_id"]


def test_multiple_locations_disable_without_media_mutation(library_store):
    store, movies, _, _ = library_store
    archive = movies / "DVD Originals"
    archive.mkdir()
    media = archive / "Movie.mkv"
    media.write_bytes(b"original")

    location = store.create_location("Original Archive", "ORIGINAL_SOURCE", "DVD Originals")
    store.update_location(location["location_id"], enabled=False)

    assert media.read_bytes() == b"original"
    enabled = store.list_locations(role="ORIGINAL_SOURCE", enabled=True)
    assert location["location_id"] not in {item["location_id"] for item in enabled}


def test_location_validation_rejects_traversal_absolute_and_symlink_escape(library_store):
    store, movies, _, _ = library_store
    outside = movies.parent / "outside"
    outside.mkdir()
    (movies / "escape").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="safe relative"):
        store.create_location("Traversal", "ORIGINAL_SOURCE", "../outside")
    with pytest.raises(ValueError, match="safe relative"):
        store.create_location("Absolute", "ORIGINAL_SOURCE", str(outside))
    with pytest.raises(ValueError, match="symlink"):
        store.create_location("Escape", "ORIGINAL_SOURCE", "escape")
    with pytest.raises(ValueError, match="Invalid library location role"):
        store.create_location("Invalid", "OTHER", "DVD")


def test_destination_configuration_is_a_plan_and_does_not_create_folder(library_store):
    store, movies, _, _ = library_store
    planned = movies / "Upscaled"
    assert not planned.exists()

    location = store.create_location(
        "Upscaled Movies",
        "FINISHED_DESTINATION",
        "Upscaled",
    )

    assert not planned.exists()
    assert public_location(location)["display_path"] == "/movies/Upscaled"
    assert "server_root" not in public_location(location)


@pytest.mark.parametrize("folder", ["/absolute", "../escape", "Movie/../escape", r"Movie\escape"])
def test_destination_subfolder_rejects_unsafe_values(tmp_path, folder):
    with pytest.raises(ValueError):
        validate_destination_subfolder(folder, tmp_path)


def test_multi_root_discovery_deduplicates_overlap_and_keeps_distinct_files(library_store):
    store, movies, intake, _ = library_store
    nested = intake / "Nested"
    archive = movies / "Archive"
    nested.mkdir()
    archive.mkdir()
    (nested / "Same.mkv").write_bytes(b"one")
    (archive / "Same.mkv").write_bytes(b"two")
    store.create_location("Nested Source", "ORIGINAL_SOURCE", "DVD/Nested")
    store.create_location("Archive", "ORIGINAL_SOURCE", "Archive")

    results = discover_candidates_across_locations(
        store.list_locations(role="ORIGINAL_SOURCE", enabled=True)
    )

    assert [item["filename"] for item in results] == ["Same.mkv", "Same.mkv"]
    assert {item["location_name"] for item in results} == {"Archive", "DVD Intake"}


def test_discovery_api_searches_filename_folder_and_location(library_store, monkeypatch):
    store, movies, intake, _ = library_store
    (intake / "Ratatouille").mkdir()
    (intake / "Ratatouille" / "disc.mkv").write_bytes(b"movie")
    archive = movies / "Archive"
    archive.mkdir()
    (archive / "Other.mkv").write_bytes(b"other")
    store.create_location("Original Archive", "ORIGINAL_SOURCE", "Archive")
    monkeypatch.setattr(app.state, "operator_store", store, raising=False)

    filename = client.get("/api/media/discover?query=disc").json()["candidates"]
    folder = client.get("/api/media/discover?query=ratatouille").json()["candidates"]
    location = client.get("/api/media/discover?query=original%20archive").json()["candidates"]

    assert [item["filename"] for item in filename] == ["disc.mkv"]
    assert [item["filename"] for item in folder] == ["disc.mkv"]
    assert [item["filename"] for item in location] == ["Other.mkv"]
    assert location[0]["location_id"]


def test_discovery_api_filters_normal_results_to_eligible_sources(library_store, monkeypatch):
    store, _, intake, _ = library_store
    eligible_dir = intake / "Ratatouille"
    eligible_dir.mkdir()
    (eligible_dir / "Ratatouille - DVD Original.mkv").write_bytes(b"movie")
    (intake / "Legacy - Nomos8k.mkv").write_bytes(b"legacy")
    (intake / "The Usual Suspects - DVD RVE Nomos8k Medium 2x.mkv").write_bytes(b"enhanced")
    monkeypatch.setattr(app.state, "operator_store", store, raising=False)

    eligible = client.get("/api/media/discover?query=ratatouille").json()["candidates"]
    assert [item["filename"] for item in eligible] == ["Ratatouille - DVD Original.mkv"]
    assert client.get("/api/media/discover?query=nomos").json()["candidates"] == []
    assert all(item["preparation_eligibility"]["eligible"] for item in eligible)


def test_workflow_context_persists_and_uses_authoritative_ids(library_store):
    store, movies, intake, database = library_store
    movie_dir = intake / "Movie"
    movie_dir.mkdir()
    (movie_dir / "Movie.mkv").write_bytes(b"movie")
    destination = store.create_location(
        "Upscaled Movies",
        "FINISHED_DESTINATION",
        "Upscaled",
    )
    source = store.list_locations(role="ORIGINAL_SOURCE")[0]
    workflow = store.create_workflow(source["location_id"], "Movie/Movie.mkv")
    workflow = store.set_destination(
        workflow["workflow_id"],
        destination["location_id"],
    )
    workflow = store.associate_preparation(workflow["workflow_id"], "a" * 32)
    workflow = store.associate_rve_job("a" * 32, "b" * 32)

    reopened = OperatorStateStore(database)
    current = reopened.get_current_workflow()
    assert current["workflow_id"] == workflow["workflow_id"]
    assert current["preparation_id"] == "a" * 32
    assert current["rve_job_id"] == "b" * 32
    assert current["destination_location_name"] == "Upscaled Movies"
    assert current["destination_relative_folder"] is None
    assert not (movies / "Upscaled").exists()


def test_root_only_destination_hides_legacy_relative_folder(library_store):
    store, _, intake, _ = library_store
    (intake / "Movie.mkv").write_bytes(b"movie")
    source = store.list_locations(role="ORIGINAL_SOURCE")[0]
    destination = store.create_location(
        "DVD Upscaled",
        "FINISHED_DESTINATION",
        "DVD Upscaled",
    )
    workflow = store.create_workflow(source["location_id"], "Movie.mkv")
    with store._connect() as connection:
        connection.execute(
            """
            UPDATE operator_workflows
            SET destination_location_id = ?, destination_relative_folder = 'Movie'
            WHERE workflow_id = ?
            """,
            (destination["location_id"], workflow["workflow_id"]),
        )

    assert public_workflow(store.get_workflow(workflow["workflow_id"]))[
        "destination_relative_folder"
    ] is None


def test_reselecting_unstarted_source_reuses_current_workflow(library_store):
    store, _, intake, _ = library_store
    (intake / "Movie.mkv").write_bytes(b"movie")
    source = store.list_locations(role="ORIGINAL_SOURCE")[0]

    first = store.create_workflow(source["location_id"], "Movie.mkv")
    second = store.create_workflow(source["location_id"], "Movie.mkv")

    assert second["workflow_id"] == first["workflow_id"]


def test_workflow_rejects_wrong_location_roles(library_store):
    store, _, _, _ = library_store
    destination = store.create_location(
        "Destination",
        "FINISHED_DESTINATION",
        "Finished",
    )
    with pytest.raises(ValueError, match="ORIGINAL_SOURCE"):
        store.create_workflow(destination["location_id"], "Movie.mkv")


def test_gpu_cpu_and_sensor_parsers_use_controlled_evidence():
    gpu = parse_nvidia_smi_csv("67, 98, 8400, 16384, 224.5, 300, N/A\n")
    assert gpu["temperature_c"] == 67
    assert gpu["memory_total_mib"] == 16384
    assert gpu["fan_percent"] is None

    first = parse_cpu_stat("cpu  100 0 50 850 0 0 0 0\n")
    second = parse_cpu_stat("cpu  200 0 0 900 0 0 0 0\n")
    assert calculate_cpu_utilization(first, second) == 50.0

    sensors = {
        "k10temp-pci-00c3": {
            "Tctl": {"temp1_input": 71.25, "temp1_max": 95.0},
        }
    }
    assert parse_sensors_temperature(json.dumps(sensors)) == 71.25


def test_telemetry_snapshot_degrades_unavailable_metrics_safely():
    stats = iter(
        [
            "cpu  100 0 0 900 0 0 0 0\n",
            "cpu  150 0 0 950 0 0 0 0\n",
        ]
    )

    def runner(command, **kwargs):
        if command[0] == "nvidia-smi":
            raise subprocess.TimeoutExpired(command, 3)
        return SimpleNamespace(returncode=1, stdout="", stderr="missing")

    service = TelemetryService(runner=runner, proc_stat_reader=lambda: next(stats))
    result = service.snapshot()

    assert result["status"] == "partial"
    assert result["cpu"]["utilization_percent"] == 50.0
    assert result["cpu"]["temperature_c"] is None
    assert result["gpu"]["temperature_c"] is None


def test_telemetry_endpoint_failure_does_not_affect_job_or_health_api(monkeypatch):
    class PartialTelemetry:
        def snapshot(self):
            return {
                "status": "partial",
                "cpu": {"utilization_percent": None, "temperature_c": None},
                "gpu": {"temperature_c": None},
                "unavailable_reasons": ["Unavailable"],
            }

    monkeypatch.setattr(app.state, "telemetry_service", PartialTelemetry(), raising=False)
    assert client.get("/api/system/telemetry").status_code == 200
    assert client.get("/health").json() == {"status": "ok"}


def test_operator_page_exposes_one_staged_workflow_and_safe_status():
    response = client.get("/media")
    assert response.status_code == 200
    for text in (
        "Find DVD",
        "Finished Movie Destination",
        "Analyze &amp; Prepare",
        "DVD RVE Medium 2x",
        "System Status",
        "Recent Jobs",
        "Ready for Publication",
        "Publication",
        "Not yet performed",
        "Advanced Details",
    ):
        assert text in response.text
    assert "window.setInterval(loadTelemetry, 3000)" in response.text
    assert "addEventListener('input', filterSources)" in response.text
    assert "shell access" not in response.text
