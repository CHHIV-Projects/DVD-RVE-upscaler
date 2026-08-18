"""Minimal application configuration for the scaffold and media workflow."""


class Settings:
    app_name = "DVD RVE Upscaler"
    host = "0.0.0.0"
    port = 8010
    dvd_source_root = "/mnt/nas/movies/DVD"
    app_version = "0.1.2"


settings = Settings()
