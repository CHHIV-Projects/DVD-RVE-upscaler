import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import media as media_api
from app.config import settings
from app.main import app
from app.services import media_analysis, media_preparation
from app.services.media_analysis import _classify_samples, compute_square_pixel_geometry, parse_idet_summary, probe_media
from app.services.media_discovery import discover_candidates, validate_candidate_relative_path
from app.services.operator_state import OperatorStateStore

client = TestClient(app)


def test_app_imports():
    assert app is not None


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_landing_page_returns_http_success():
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_landing_page_contains_application_identity():
    response = client.get("/")
    assert response.status_code == 200
    assert "DVD RVE Upscaler" in response.text


def test_media_page_returns_http_success():
    response = client.get("/media")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "DVD RVE Upscaler" in response.text


def test_discovery_filters_non_mkv_and_enhanced_candidates(tmp_path, monkeypatch):
    root = tmp_path / "DVD"
    movie_dir = root / "Movie Name"
    movie_dir.mkdir(parents=True)
    (movie_dir / "Movie Name - DVD Original.mkv").write_bytes(b"good")
    (movie_dir / "Movie Name - DVD RVE Medium 2x.mkv").write_bytes(b"enhanced")
    (movie_dir / "notes.txt").write_text("ignore")
    (root / "other").mkdir()
    (root / "other" / "Other.mkv").write_bytes(b"other")

    monkeypatch.setattr(settings, "dvd_source_root", str(root), raising=False)
    response = client.get("/api/media/discover")
    assert response.status_code == 200
    candidates = response.json()["candidates"]
    paths = [entry["relative_path"] for entry in candidates]
    assert paths == ["Movie Name/Movie Name - DVD Original.mkv", "other/Other.mkv"]


def test_discovery_ordering_and_symlink_handling(tmp_path):
    root = tmp_path / "DVD"
    (root / "b").mkdir(parents=True)
    (root / "a").mkdir(parents=True)
    (root / "b" / "z.mkv").write_bytes(b"z")
    (root / "a" / "a.mkv").write_bytes(b"a")
    symlink = root / "a" / "link.mkv"
    symlink.symlink_to(root / "b" / "z.mkv")
    discovered = discover_candidates(root)
    assert [item["relative_path"] for item in discovered] == ["a/a.mkv", "b/z.mkv"]
    assert "a/link.mkv" not in [item["relative_path"] for item in discovered]


def test_validate_candidate_rejects_traversal_and_outside_root(tmp_path):
    root = tmp_path / "DVD"
    root.mkdir()
    good = root / "good.mkv"
    good.write_bytes(b"ok")

    with pytest.raises(ValueError):
        validate_candidate_relative_path("../outside.mkv", root=root)
    with pytest.raises(ValueError):
        validate_candidate_relative_path("/etc/passwd", root=root)
    with pytest.raises(ValueError):
        validate_candidate_relative_path("nested/../../outside.mkv", root=root)

    resolved = validate_candidate_relative_path("good.mkv", root=root)
    assert resolved == good

    outside = tmp_path / "outside.mkv"
    outside.write_bytes(b"no")
    with pytest.raises((ValueError, FileNotFoundError)):
        validate_candidate_relative_path(str(outside.relative_to(tmp_path)), root=root)


def test_probe_media_parses_ffprobe_json(monkeypatch):
    payload = {
        "format": {"format_name": "matroska,webm", "duration": "123.456", "size": "987654"},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "mpeg2video",
                "width": 720,
                "height": 480,
                "sample_aspect_ratio": "853:720",
                "display_aspect_ratio": "853:480",
                "field_order": "tt",
                "avg_frame_rate": "30000/1001",
                "r_frame_rate": "30000/1001",
                "pix_fmt": "yuv420p",
            },
            {
                "codec_type": "audio",
                "codec_name": "ac3",
                "channels": 6,
                "channel_layout": "5.1(side)",
                "tags": {"language": "eng", "title": "Surround 5.1"},
            },
            {
                "codec_type": "subtitle",
                "codec_name": "subrip",
                "tags": {"language": "eng", "title": "English"},
            },
        ],
        "chapters": [{}, {}, {}],
    }

    def fake_run(*args, **kwargs):
        return type("Proc", (), {"returncode": 0, "stdout": json.dumps(payload), "stderr": ""})()

    monkeypatch.setattr(media_analysis.subprocess, "run", fake_run)
    result = probe_media(Path("/tmp/input.mkv"))

    assert result["status"] == "ok"
    assert result["duration_seconds"] == 123.456
    assert result["container_name"] == "matroska,webm"
    assert result["chapter_count"] == 3
    assert result["video_stream"]["width"] == 720
    assert result["video_stream"]["sample_aspect_ratio"] == "853:720"
    assert result["video_stream"]["pixel_format"] == "yuv420p"
    assert result["audio_streams"][0]["codec"] == "ac3"
    assert result["subtitle_streams"][0]["title"] == "English"


def test_geometry_policy_examples_and_invalid_sar():
    widescreen = compute_square_pixel_geometry({"width": 720, "height": 480, "sample_aspect_ratio": "853:720", "display_aspect_ratio": "853:480"})
    assert widescreen["display_width"] == 853
    assert widescreen["prepared_width"] == 854
    assert widescreen["status"] == "ok"

    four_by_three = compute_square_pixel_geometry({"width": 720, "height": 480, "sample_aspect_ratio": "8:9", "display_aspect_ratio": "8:9"})
    assert four_by_three["display_width"] == 640
    assert four_by_three["prepared_width"] == 640

    invalid = compute_square_pixel_geometry({"width": 720, "height": 480, "sample_aspect_ratio": "invalid", "display_aspect_ratio": "16:9"})
    assert invalid["status"] == "review_required"

    disagreement = compute_square_pixel_geometry({"width": 720, "height": 480, "sample_aspect_ratio": "853:720", "display_aspect_ratio": "4:3"})
    assert disagreement["status"] == "review_required"


def test_idet_summary_parsing_handles_real_ffmpeg_output():
    output = """
    [Parsed_idet_0] Repeated Fields: Neither:     0 Top:     0 Bottom:     0
    [Parsed_idet_0] Single frame detection: TFF:     0 BFF:     0 Progressive:   632 Undetermined:   370
    [Parsed_idet_0] Multi frame detection: TFF:     0 BFF:     0 Progressive:  1002 Undetermined:     0
    """
    parsed = parse_idet_summary(output)
    assert parsed["tff"] == 0
    assert parsed["bff"] == 0
    assert parsed["progressive"] == 1002
    assert parsed["undetermined"] == 0
    assert parsed["single_progressive"] == 632
    assert parsed["single_undetermined"] == 370
    assert parsed["repeated_top"] == 0
    assert parsed["repeated_bottom"] == 0


def test_idet_sample_uses_multi_frame_counts_and_repeated_field_population(monkeypatch):
    output = """
    [Parsed_idet_0] Repeated Fields: Neither: 80 Top: 15 Bottom: 5
    [Parsed_idet_0] Single frame detection: TFF: 900 BFF: 0 Progressive: 100 Undetermined: 0
    [Parsed_idet_0] Multi frame detection: TFF: 0 BFF: 0 Progressive: 1000 Undetermined: 0
    """

    def fake_run(*args, **kwargs):
        return type("Proc", (), {"returncode": 0, "stdout": "", "stderr": output})()

    monkeypatch.setattr(media_analysis.subprocess, "run", fake_run)
    sample = media_analysis.run_idet_sample(Path("/tmp/input.mkv"), 10.0)

    assert sample["progressive"] == 1000
    assert sample["tff"] == 0
    assert sample["total_determined"] == 1000
    assert sample["progressive_ratio"] == 1.0
    assert sample["repeated_neither"] == 80
    assert sample["repeated_field_ratio"] == 0.2


def test_idet_sample_marks_too_few_determined_frames_insufficient(monkeypatch):
    output = """
    [Parsed_idet_0] Repeated Fields: Neither: 99 Top: 0 Bottom: 0
    [Parsed_idet_0] Single frame detection: TFF: 0 BFF: 0 Progressive: 99 Undetermined: 0
    [Parsed_idet_0] Multi frame detection: TFF: 0 BFF: 0 Progressive: 99 Undetermined: 0
    """

    def fake_run(*args, **kwargs):
        return type("Proc", (), {"returncode": 0, "stdout": "", "stderr": output})()

    monkeypatch.setattr(media_analysis.subprocess, "run", fake_run)
    sample = media_analysis.run_idet_sample(Path("/tmp/input.mkv"), 10.0)

    assert sample["total_determined"] == 99
    assert sample["status"] == "insufficient"


def test_classification_thresholds_and_ambiguous_outputs():
    progressive = _classify_samples([
        {"status": "usable", "progressive_ratio": 0.98, "tff_ratio": 0.01, "bff_ratio": 0.01, "repeated_field_ratio": 0.0},
        {"status": "usable", "progressive_ratio": 0.97, "tff_ratio": 0.02, "bff_ratio": 0.01, "repeated_field_ratio": 0.0},
    ])
    assert progressive["content_classification"] == "progressive"

    tff = _classify_samples([
        {"status": "usable", "progressive_ratio": 0.05, "tff_ratio": 0.95, "bff_ratio": 0.00, "repeated_field_ratio": 0.0},
        {"status": "usable", "progressive_ratio": 0.04, "tff_ratio": 0.96, "bff_ratio": 0.00, "repeated_field_ratio": 0.0},
    ])
    assert tff["content_classification"] == "interlaced_tff"

    bff = _classify_samples([
        {"status": "usable", "progressive_ratio": 0.03, "tff_ratio": 0.00, "bff_ratio": 0.97, "repeated_field_ratio": 0.0},
        {"status": "usable", "progressive_ratio": 0.04, "tff_ratio": 0.01, "bff_ratio": 0.95, "repeated_field_ratio": 0.0},
    ])
    assert bff["content_classification"] == "interlaced_bff"

    ambiguous = _classify_samples([
        {"status": "usable", "progressive_ratio": 0.65, "tff_ratio": 0.30, "bff_ratio": 0.05, "repeated_field_ratio": 0.05},
        {"status": "usable", "progressive_ratio": 0.40, "tff_ratio": 0.55, "bff_ratio": 0.05, "repeated_field_ratio": 0.05},
    ])
    assert ambiguous["content_classification"] == "ambiguous"

    telecine = _classify_samples([
        {"status": "usable", "progressive_ratio": 0.98, "tff_ratio": 0.01, "bff_ratio": 0.01, "repeated_field_ratio": 0.11},
    ])
    assert telecine["content_classification"] == "telecine_suspected"

    insufficient = _classify_samples([
        {"status": "insufficient", "progressive_ratio": 0.0, "tff_ratio": 0.0, "bff_ratio": 0.0, "repeated_field_ratio": 0.0},
    ])
    assert insufficient["content_classification"] == "unsupported"


def test_metadata_interlace_conflicts_with_progressive_content(monkeypatch):
    probe_result = {
        "status": "ok",
        "duration_seconds": 100.0,
        "container_name": "matroska,webm",
        "size_bytes": "123",
        "video_stream": {"field_order": "tt"},
        "audio_streams": [],
        "subtitle_streams": [],
        "chapter_count": 0,
        "geometry": {"status": "ok"},
    }
    progressive_sample = {
        "status": "usable",
        "progressive_ratio": 1.0,
        "tff_ratio": 0.0,
        "bff_ratio": 0.0,
        "repeated_field_ratio": 0.0,
    }
    monkeypatch.setattr(
        media_analysis,
        "validate_candidate_relative_path",
        lambda relative_path, root=None: Path("/tmp/input.mkv"),
    )
    monkeypatch.setattr(media_analysis, "probe_media", lambda source_path: probe_result)
    monkeypatch.setattr(media_analysis, "run_idet_sample", lambda *args, **kwargs: progressive_sample)

    result = media_analysis.analyze_candidate("input.mkv")

    assert result["metadata_field_order"] == "tt"
    assert result["content_classification"] == "progressive"
    assert result["final_classification"] == "ambiguous"
    assert result["analysis_status"] == "review_required"
    assert any("materially conflicts" in reason for reason in result["classification_reasons"])


def test_api_discovery_and_analysis_endpoints(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.api.media.discover_candidates",
        lambda: [{"relative_path": "A.mkv", "filename": "A.mkv", "movie_folder": "."}],
    )
    monkeypatch.setattr(
        media_api,
        "assess_preparation_eligibility",
        lambda relative_path, **kwargs: {
            "eligible": True,
            "status": "eligible",
            "reason": "eligible",
        },
    )
    response = client.get("/api/media/discover")
    assert response.status_code == 200
    assert response.json()["count"] == 1

    root = tmp_path / "DVD"
    root.mkdir()
    (root / "A.mkv").write_bytes(b"contents")
    monkeypatch.setattr(settings, "dvd_source_root", str(root), raising=False)
    monkeypatch.setattr(
        media_api,
        "analyze_candidate",
        lambda relative_path, root=None: {
            "status": "ok",
            "relative_source": relative_path,
            "final_classification": "progressive",
        },
    )
    result = client.post("/api/media/analyze", json={"relative_path": "A.mkv"})
    assert result.status_code == 200
    assert result.json()["final_classification"] == "progressive"
    assert result.json()["preparation_proposal"]["proposed_decision"] == "progressive"

    response = client.post("/api/media/analyze", json={"relative_path": "/tmp/A.mkv"})
    assert response.status_code == 400
    assert response.json()["detail"] == "invalid path"


def test_prepare_plan_is_idempotent_for_same_workflow_and_rejects_conflicts(tmp_path, monkeypatch):
    movies = tmp_path / "movies"
    root = movies / "Library DVDs"
    source_folder = root / "Ratatouille"
    source_folder.mkdir(parents=True)
    source = source_folder / "Ratatouille - DVD Original.mkv"
    source.write_bytes(b"movie")
    monkeypatch.setattr(settings, "dvd_source_root", str(root), raising=False)
    monkeypatch.setattr(settings, "trusted_nas_movies_root", str(movies), raising=False)
    state_path = tmp_path / "state.sqlite3"
    store = OperatorStateStore(state_path)
    store.initialize()
    source_location = store.list_locations(role="ORIGINAL_SOURCE")[0]
    destination = store.create_location("DVD Upscaled", "FINISHED_DESTINATION", "DVD Upscaled")
    relative_path = "Ratatouille/Ratatouille - DVD Original.mkv"
    workflow = store.create_workflow(source_location["location_id"], relative_path)
    with store._connect() as connection:
        connection.execute(
            """
            UPDATE operator_workflows
            SET destination_location_id = ?, destination_relative_folder = ?
            WHERE workflow_id = ?
            """,
            (destination["location_id"], "Ratatouille", workflow["workflow_id"]),
        )
    monkeypatch.setattr(app.state, "operator_store", store, raising=False)
    work_root = tmp_path / "prepwork"
    monkeypatch.setattr(settings, "preparation_work_root", str(work_root), raising=False)
    analysis = {
        "status": "ok",
        "content_classification": "progressive",
        "final_classification": "progressive",
        "analysis_status": "ok",
        "classification_reasons": ["Progressive."],
        "geometry": {
            "status": "ok",
            "prepared_width": 854,
            "prepared_height": 480,
        },
        "video_stream": {"avg_frame_rate": "30000/1001"},
        "duration_seconds": 100.0,
        "audio_streams": [],
        "subtitle_streams": [],
        "chapter_count": 0,
    }
    monkeypatch.setattr(media_api, "analyze_candidate", lambda *args, **kwargs: dict(analysis))
    monkeypatch.setattr(
        media_api,
        "assess_preparation_eligibility",
        lambda *args, **kwargs: {"eligible": True, "status": "eligible", "reason": "Eligible."},
    )
    monkeypatch.setattr(
        media_preparation,
        "assess_preparation_eligibility",
        lambda *args, **kwargs: {"eligible": True, "status": "eligible", "reason": "Eligible."},
    )
    monkeypatch.setattr(media_preparation, "analyze_candidate", lambda *args, **kwargs: dict(analysis))
    monkeypatch.setattr(media_preparation, "work_root_is_local", lambda path: True)

    destination_response = client.patch(
        f"/api/workflows/{workflow['workflow_id']}/destination",
        json={"destination_location_id": destination["location_id"]},
    )
    assert destination_response.status_code == 200
    assert destination_response.json()["destination_relative_folder"] is None
    with store._connect() as connection:
        stored_folder = connection.execute(
            "SELECT destination_relative_folder FROM operator_workflows WHERE workflow_id = ?",
            (workflow["workflow_id"],),
        ).fetchone()[0]
    assert stored_folder is None

    analyzed = client.post(
        "/api/media/analyze",
        json={
            "location_id": source_location["location_id"],
            "relative_path": relative_path,
        },
    )
    assert analyzed.status_code == 200

    first = client.post(
        "/api/media/prepare/plan",
        json={
            "location_id": source_location["location_id"],
            "workflow_id": workflow["workflow_id"],
            "relative_path": relative_path,
            "decision": "progressive",
        },
    )
    reopened = OperatorStateStore(state_path)
    reopened.initialize()
    monkeypatch.setattr(app.state, "operator_store", reopened, raising=False)
    second = client.post(
        "/api/media/prepare/plan",
        json={
            "location_id": source_location["location_id"],
            "workflow_id": workflow["workflow_id"],
            "relative_path": relative_path,
            "decision": "progressive",
        },
    )
    assert first.status_code == 200
    assert second.status_code == 200
    plan_id = first.json()["preparation_id"]
    assert second.json()["preparation_id"] == plan_id
    assert first.json()["preparation_status"] == "plan_ready"
    assert second.json()["ready_to_prepare"] is True
    assert reopened.get_workflow(workflow["workflow_id"])["preparation_id"] == plan_id
    assert [path.parent.name for path in work_root.glob("*/plan.json")] == [plan_id]

    (work_root / plan_id / "prepared.mkv").write_bytes(b"completed")
    third = client.post(
        "/api/media/prepare/plan",
        json={
            "location_id": source_location["location_id"],
            "workflow_id": workflow["workflow_id"],
            "relative_path": relative_path,
            "decision": "progressive",
        },
    )
    assert third.status_code == 200
    assert third.json()["preparation_id"] == plan_id
    assert third.json()["preparation_status"] == "completed"
    assert third.json()["ready_to_prepare"] is False

    conflict = client.post(
        "/api/media/prepare/plan",
        json={
            "location_id": source_location["location_id"],
            "workflow_id": workflow["workflow_id"],
            "relative_path": relative_path,
            "decision": "deinterlace_tff",
        },
    )
    assert conflict.status_code == 422
    assert "conflicts" in conflict.json()["detail"]
    with pytest.raises(ValueError, match="different preparation"):
        reopened.associate_preparation(workflow["workflow_id"], "f" * 32)


def test_media_page_content_mentions_analysis_workflow():
    response = client.get("/media")
    assert response.status_code == 200
    assert "Find DVD" in response.text
    assert "Finished Movie Destination" in response.text
    assert "Analyze DVD" in response.text
    assert "Review Preparation Plan" in response.text
    assert "Prepare DVD" in response.text
    assert "destination_relative_folder" not in response.text
