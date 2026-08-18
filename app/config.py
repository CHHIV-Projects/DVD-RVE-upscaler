"""Minimal application configuration for the scaffold and media workflow."""


class Settings:
    app_name = "DVD RVE Upscaler"
    host = "0.0.0.0"
    port = 8010
    trusted_nas_movies_root = "/mnt/nas/movies"
    dvd_source_root = "/mnt/nas/movies/DVD"
    preparation_work_root = "/home/chuck/Videos/DVD-RVE-upscaler"
    preparation_timeout_seconds = 21600
    preparation_min_free_bytes = 10 * 1024**3
    preparation_source_size_multiplier = 2
    rve_root = "/home/chuck/apps/real-video-enhancer/bin"
    rve_python = "/home/chuck/apps/real-video-enhancer/bin/python/python/bin/python3"
    rve_backend = "/home/chuck/apps/real-video-enhancer/bin/backend/rve-backend.py"
    rve_ffmpeg = "/home/chuck/apps/real-video-enhancer/bin/bin/ffmpeg"
    rve_model = "/home/chuck/apps/real-video-enhancer/bin/models/4xNomos8k_span_otf_medium_no_update_params.pth"
    rve_state_database = "/home/chuck/Videos/DVD-RVE-upscaler/app-state/rve-jobs.sqlite3"
    rve_cancel_grace_seconds = 10
    app_version = "0.1.5"


settings = Settings()
