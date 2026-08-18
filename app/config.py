"""Minimal application configuration for the scaffold and media workflow."""


class Settings:
    app_name = "DVD RVE Upscaler"
    host = "0.0.0.0"
    port = 8010
    dvd_source_root = "/mnt/nas/movies/DVD"
    preparation_work_root = "/home/chuck/Videos/DVD-RVE-upscaler"
    preparation_timeout_seconds = 21600
    preparation_min_free_bytes = 10 * 1024**3
    preparation_source_size_multiplier = 2
    app_version = "0.1.3"


settings = Settings()
