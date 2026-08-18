import copy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import media as media_api
from app.config import settings
from app.main import app
from app.services import media_preparation
from app.services.media_preparation import (
    assess_preparation_eligibility,
    acquire_execution_marker,
    build_ffmpeg_command,
    build_video_filter,
    check_available_space,
    create_preparation_plan,
    execute_preparation,
    promote_validated_output,
    propose_preparation_decision,
    validate_preparation_decision,
    validate_prepared_output,
)

client = TestClient(app)


@pytest.fixture
def source_tree(tmp_path, monkeypatch):
    root = tmp_path / "DVD"
    root.mkdir()
    source = root / "Movie - DVD Original.mkv"
    source.write_bytes(b"source-media")
    work_root = tmp_path / "work"
    monkeypatch.setattr(settings, "dvd_source_root", str(root), raising=False)
    monkeypatch.setattr(settings, "preparation_work_root", str(work_root), raising=False)
    return root, source, work_root


@pytest.fixture
def progressive_analysis():
    return {
        "status": "ok",
        "duration_seconds": 100.0,
        "video_stream": {
            "codec": "mpeg2video",
            "width": 720,
            "height": 480,
            "sample_aspect_ratio": "853:720",
            "display_aspect_ratio": "853:480",
            "pixel_format": "yuv420p",
            "field_order": "tt",
            "avg_frame_rate": "30000/1001",
            "r_frame_rate": "30000/1001",
        },
        "audio_streams": [{"codec": "ac3", "channels": 6, "language": "eng"}],
        "subtitle_streams": [{"codec": "subrip", "language": "eng"}],
        "chapter_count": 3,
        "geometry": {
            "status": "ok",
            "coded_width": 720,
            "coded_height": 480,
            "sar": "853:720",
            "prepared_width": 854,
            "prepared_height": 480,
        },
        "content_classification": "progressive",
        "final_classification": "progressive",
        "analysis_status": "ok",
        "classification_reasons": ["Clear progressive evidence."],
    }


@pytest.fixture
def valid_prepared_probe():
    return {
        "status": "ok",
        "duration_seconds": 100.2,
        "video_stream": {
            "codec": "h264",
            "width": 854,
            "height": 480,
            "sample_aspect_ratio": "1:1",
            "field_order": "progressive",
            "pixel_format": "yuv420p",
            "avg_frame_rate": "30000/1001",
            "r_frame_rate": "30000/1001",
        },
        "audio_streams": [{"codec": "ac3", "channels": 6, "language": "eng"}],
        "subtitle_streams": [{"codec": "subrip", "language": "eng"}],
        "chapter_count": 3,
    }


def make_validation_plan(progressive_analysis):
    return {
        "target_prepared_geometry": {"width": 854, "height": 480},
        "pixel_format": "yuv420p",
        "frame_rate": "30000/1001",
        "source_duration_seconds": 100.0,
        "source_audio_streams": progressive_analysis["audio_streams"],
        "source_subtitle_streams": progressive_analysis["subtitle_streams"],
        "source_chapter_count": 3,
    }


def test_valid_original_is_preparation_eligible(source_tree):
    root, source, _ = source_tree
    result = assess_preparation_eligibility(source.name, root=root, verify_read_only_mount=False)
    assert result["eligible"] is True


@pytest.mark.parametrize(
    ("filename", "marker"),
    [
        ("Movie - DVD RVE Medium 2x.mkv", "RVE"),
        ("Movie - Nomos8k.mkv", "Nomos"),
        ("Movie - Medium 2x.mkv", "Medium 2x"),
        ("Schindler's List - DVE RVE Medium 2x.mkv", "RVE"),
    ],
)
def test_enhancement_markers_block_preparation(tmp_path, filename, marker):
    root = tmp_path / "DVD"
    root.mkdir()
    (root / filename).write_bytes(b"enhanced")
    result = assess_preparation_eligibility(filename, root=root, verify_read_only_mount=False)
    assert result["eligible"] is False
    assert result["matched_marker"] == marker


def test_rve_marker_requires_token_boundary(tmp_path):
    root = tmp_path / "DVD"
    root.mkdir()
    candidate = root / "Harvey.mkv"
    candidate.write_bytes(b"original")
    result = assess_preparation_eligibility(candidate.name, root=root, verify_read_only_mount=False)
    assert result["eligible"] is True


def test_ineligible_paths_include_symlink_traversal_outside_and_non_mkv(tmp_path):
    root = tmp_path / "DVD"
    root.mkdir()
    outside = tmp_path / "outside.mkv"
    outside.write_bytes(b"outside")
    symlink = root / "link.mkv"
    symlink.symlink_to(outside)
    text_file = root / "notes.txt"
    text_file.write_text("not media")

    for candidate in ("link.mkv", "../outside.mkv", str(outside), "notes.txt"):
        result = assess_preparation_eligibility(candidate, root=root, verify_read_only_mount=False)
        assert result["eligible"] is False


@pytest.mark.parametrize(
    ("classification", "expected"),
    [
        ("progressive", "progressive"),
        ("interlaced_tff", "deinterlace_tff"),
        ("interlaced_bff", "deinterlace_bff"),
    ],
)
def test_unambiguous_analysis_maps_to_proposal(classification, expected):
    analysis = {"final_classification": classification, "analysis_status": "ok"}
    assert propose_preparation_decision(analysis)["proposed_decision"] == expected


def test_ambiguous_analysis_requires_explicit_approved_decision(progressive_analysis):
    analysis = copy.deepcopy(progressive_analysis)
    analysis["final_classification"] = "ambiguous"
    analysis["analysis_status"] = "review_required"
    proposal = propose_preparation_decision(analysis)
    assert proposal["proposed_decision"] is None
    for decision in ("progressive", "deinterlace_tff", "deinterlace_bff"):
        assert validate_preparation_decision(analysis, decision)["explicit_override"] is True
    with pytest.raises(ValueError, match="Invalid preparation decision"):
        validate_preparation_decision(analysis, "custom-filter")


def test_unambiguous_analysis_rejects_conflicting_override(progressive_analysis):
    with pytest.raises(ValueError, match="conflicts"):
        validate_preparation_decision(progressive_analysis, "deinterlace_tff")


def test_filter_generation_is_exact_and_controlled():
    assert build_video_filter("progressive", 854, 480) == "scale=854:480,setsar=1,setfield=prog"
    assert build_video_filter("deinterlace_tff", 854, 480) == (
        "bwdif=mode=send_frame:parity=tff:deint=all,scale=854:480,setsar=1,setfield=prog"
    )
    assert build_video_filter("deinterlace_bff", 854, 480) == (
        "bwdif=mode=send_frame:parity=bff:deint=all,scale=854:480,setsar=1,setfield=prog"
    )
    with pytest.raises(ValueError):
        build_video_filter("scale=1:1;rm", 854, 480)


def test_command_is_structured_nvenc_no_overwrite_and_preserves_streams():
    plan = {
        "source_absolute_path": "/safe/source.mkv",
        "temporary_output_path": "/safe/work/prepared.partial.mkv",
        "video_filter": "scale=854:480,setsar=1,setfield=prog",
    }
    command = build_ffmpeg_command(plan)
    assert isinstance(command, list)
    assert "h264_nvenc" in command
    assert "libx264" not in command
    assert "-n" in command
    assert "-y" not in command
    assert command[command.index("-c:a") + 1] == "copy"
    assert command[command.index("-c:s") + 1] == "copy"
    assert "-map_metadata" in command
    assert "-map_chapters" in command
    assert command[-1] == "/safe/work/prepared.partial.mkv"


def test_plan_uses_unique_contained_paths_and_records_override(source_tree, progressive_analysis):
    root, source, work_root = source_tree
    analysis = copy.deepcopy(progressive_analysis)
    analysis["final_classification"] = "ambiguous"
    analysis["analysis_status"] = "review_required"
    first = create_preparation_plan(
        source.name,
        "progressive",
        analysis=analysis,
        root=root,
        work_root=work_root,
        verify_runtime=False,
    )
    second = create_preparation_plan(
        source.name,
        "progressive",
        analysis=analysis,
        root=root,
        work_root=work_root,
        verify_runtime=False,
    )
    assert first["preparation_id"] != second["preparation_id"]
    assert first["explicit_override"] is True
    assert Path(first["working_directory"]).parent == work_root.resolve()
    assert Path(first["temporary_output_path"]).name == "prepared.partial.mkv"
    assert Path(first["final_prepared_output_path"]).name == "prepared.mkv"
    assert Path(first["source_absolute_path"]) != Path(first["temporary_output_path"])
    assert (Path(first["working_directory"]) / "plan.json").is_file()


def test_work_root_inside_source_is_rejected(source_tree, progressive_analysis):
    root, source, _ = source_tree
    with pytest.raises(ValueError, match="separate"):
        create_preparation_plan(
            source.name,
            "progressive",
            analysis=progressive_analysis,
            root=root,
            work_root=root / "work",
            verify_runtime=False,
        )


def test_insufficient_space_guard_blocks_plan(source_tree, progressive_analysis, monkeypatch):
    root, source, work_root = source_tree
    monkeypatch.setattr(settings, "preparation_min_free_bytes", 10**30, raising=False)
    assert check_available_space(work_root, source.stat().st_size)["sufficient"] is False
    with pytest.raises(ValueError, match="Insufficient"):
        create_preparation_plan(
            source.name,
            "progressive",
            analysis=progressive_analysis,
            root=root,
            work_root=work_root,
            verify_runtime=False,
        )


def test_valid_prepared_fixture_passes(tmp_path, progressive_analysis, valid_prepared_probe, monkeypatch):
    output = tmp_path / "prepared.partial.mkv"
    output.write_bytes(b"valid-media")
    monkeypatch.setattr(media_preparation, "probe_media", lambda path: valid_prepared_probe)
    result = validate_prepared_output(output, make_validation_plan(progressive_analysis))
    assert result["outcome"] == "PASS"


@pytest.mark.parametrize(
    ("field", "bad_value", "failed_check"),
    [
        ("codec", "mpeg2video", "video_codec"),
        ("width", 720, "video_width"),
        ("sample_aspect_ratio", "8:9", "square_pixel_sar"),
        ("field_order", "tt", "progressive_field_order"),
        ("pixel_format", "yuv444p", "pixel_format"),
    ],
)
def test_invalid_video_properties_fail_validation(
    tmp_path,
    progressive_analysis,
    valid_prepared_probe,
    monkeypatch,
    field,
    bad_value,
    failed_check,
):
    output = tmp_path / "prepared.partial.mkv"
    output.write_bytes(b"invalid-media")
    probe = copy.deepcopy(valid_prepared_probe)
    probe["video_stream"][field] = bad_value
    monkeypatch.setattr(media_preparation, "probe_media", lambda path: probe)
    result = validate_prepared_output(output, make_validation_plan(progressive_analysis))
    assert result["outcome"] == "FAIL"
    assert any(check["name"] == failed_check and check["outcome"] == "FAIL" for check in result["checks"])


@pytest.mark.parametrize(
    ("mutation", "failed_check"),
    [
        (lambda probe: probe.update(duration_seconds=102.0), "duration"),
        (lambda probe: probe.update(audio_streams=[]), "audio_stream_count"),
        (lambda probe: probe.update(subtitle_streams=[]), "subtitle_stream_count"),
        (lambda probe: probe.update(chapter_count=2), "chapter_count"),
    ],
)
def test_duration_and_stream_loss_fail_validation(
    tmp_path,
    progressive_analysis,
    valid_prepared_probe,
    monkeypatch,
    mutation,
    failed_check,
):
    output = tmp_path / "prepared.partial.mkv"
    output.write_bytes(b"invalid-media")
    probe = copy.deepcopy(valid_prepared_probe)
    mutation(probe)
    monkeypatch.setattr(media_preparation, "probe_media", lambda path: probe)
    result = validate_prepared_output(output, make_validation_plan(progressive_analysis))
    assert result["outcome"] == "FAIL"
    assert any(check["name"] == failed_check and check["outcome"] == "FAIL" for check in result["checks"])


def test_missing_file_and_ffprobe_failure_fail_validation(tmp_path, progressive_analysis, monkeypatch):
    plan = make_validation_plan(progressive_analysis)
    missing = validate_prepared_output(tmp_path / "missing.mkv", plan)
    assert missing["outcome"] == "FAIL"

    output = tmp_path / "bad.mkv"
    output.write_bytes(b"not-media")
    monkeypatch.setattr(
        media_preparation,
        "probe_media",
        lambda path: {"status": "probe_failed", "error": "bad media"},
    )
    unreadable = validate_prepared_output(output, plan)
    assert unreadable["outcome"] == "FAIL"


def test_promotion_never_overwrites_existing_final(tmp_path):
    partial = tmp_path / "prepared.partial.mkv"
    final = tmp_path / "prepared.mkv"
    partial.write_bytes(b"partial")
    final.write_bytes(b"existing")
    with pytest.raises(FileExistsError):
        promote_validated_output(partial, final)
    assert partial.read_bytes() == b"partial"
    assert final.read_bytes() == b"existing"


def test_execution_marker_atomically_blocks_duplicate_start(tmp_path):
    preparation_directory = tmp_path / ("a" * 32)
    preparation_directory.mkdir()
    marker = acquire_execution_marker(preparation_directory)
    assert marker.read_text() == "started\n"
    with pytest.raises(FileExistsError, match="already started"):
        acquire_execution_marker(preparation_directory)


def test_execute_promotes_only_pass(
    source_tree,
    progressive_analysis,
    valid_prepared_probe,
    monkeypatch,
):
    root, source, work_root = source_tree
    plan = create_preparation_plan(
        source.name,
        "progressive",
        analysis=progressive_analysis,
        root=root,
        work_root=work_root,
        verify_runtime=False,
    )

    def fake_run(command, **kwargs):
        Path(command[-1]).write_bytes(b"prepared-media")
        return type("Proc", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(media_preparation.subprocess, "run", fake_run)
    monkeypatch.setattr(media_preparation, "probe_media", lambda path: valid_prepared_probe)
    result = execute_preparation(plan["preparation_id"], work_root=work_root, verify_runtime=False)
    assert result["status"] == "completed"
    assert result["validation"]["outcome"] == "PASS"
    assert result["promoted"] is True
    assert Path(result["prepared_artifact"]).is_file()
    assert not Path(plan["temporary_output_path"]).exists()


def test_execute_failure_does_not_promote(source_tree, progressive_analysis, monkeypatch):
    root, source, work_root = source_tree
    plan = create_preparation_plan(
        source.name,
        "progressive",
        analysis=progressive_analysis,
        root=root,
        work_root=work_root,
        verify_runtime=False,
    )

    def fake_run(command, **kwargs):
        Path(command[-1]).write_bytes(b"partial-evidence")
        return type("Proc", (), {"returncode": 1, "stdout": "", "stderr": "NVENC failed"})()

    monkeypatch.setattr(media_preparation.subprocess, "run", fake_run)
    result = execute_preparation(plan["preparation_id"], work_root=work_root, verify_runtime=False)
    assert result["status"] == "failed"
    assert result["promoted"] is False
    assert Path(plan["temporary_output_path"]).is_file()
    assert not Path(plan["final_prepared_output_path"]).exists()


def test_plan_and_prepare_api_boundaries(monkeypatch):
    plan = {
        "preparation_id": "a" * 32,
        "source_relative_path": "Movie.mkv",
        "source_absolute_path": "/internal/source.mkv",
        "temporary_output_path": "/internal/prepared.partial.mkv",
        "source_mtime_ns": 1,
    }
    monkeypatch.setattr(media_api, "create_preparation_plan", lambda relative_path, decision: plan)
    response = client.post(
        "/api/media/prepare/plan",
        json={"relative_path": "Movie.mkv", "decision": "progressive"},
    )
    assert response.status_code == 200
    assert response.json()["preparation_id"] == "a" * 32
    assert "source_absolute_path" not in response.json()

    invalid = client.post(
        "/api/media/prepare/plan",
        json={"relative_path": "Movie.mkv", "decision": "custom-filter"},
    )
    assert invalid.status_code == 422

    monkeypatch.setattr(
        media_api,
        "execute_preparation",
        lambda preparation_id: {"status": "completed", "preparation_id": preparation_id},
    )
    executed = client.post("/api/media/prepare", json={"preparation_id": "a" * 32})
    assert executed.status_code == 200
    assert executed.json()["status"] == "completed"
