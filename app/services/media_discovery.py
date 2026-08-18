from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.config import settings


def get_approved_root() -> Path:
    return Path(settings.dvd_source_root).resolve()


def discover_candidates(root: str | Path | None = None) -> list[dict[str, Any]]:
    base = Path(root or settings.dvd_source_root).resolve()
    if not base.exists() or not base.is_dir():
        return []

    discovered: list[dict[str, Any]] = []
    for dirpath, dirnames, filenames in os.walk(base, topdown=True, followlinks=False):
        current_dir = Path(dirpath)
        dirnames[:] = sorted(
            d for d in dirnames if not (current_dir / d).is_symlink() and (current_dir / d).exists()
        )

        for filename in sorted(filenames):
            candidate = current_dir / filename
            if candidate.is_symlink():
                continue
            if not candidate.is_file():
                continue
            if candidate.suffix.lower() != ".mkv":
                continue
            if " - dvd rve " in candidate.name.lower():
                continue

            try:
                relative_path = candidate.relative_to(base).as_posix()
            except ValueError:
                continue

            discovered.append(
                {
                    "relative_path": relative_path,
                    "filename": candidate.name,
                    "movie_folder": Path(relative_path).parent.as_posix() if Path(relative_path).parent != Path(".") else ".",
                    "size_bytes": candidate.stat().st_size,
                }
            )

    return sorted(discovered, key=lambda item: item["relative_path"])


def validate_candidate_relative_path(candidate_relative_path: str | None, root: str | Path | None = None) -> Path:
    if candidate_relative_path is None or not str(candidate_relative_path).strip():
        raise ValueError("A candidate relative path is required.")

    normalized = str(candidate_relative_path).strip()
    if normalized.startswith("/") or normalized.startswith("\\"):
        raise ValueError("Absolute paths are not allowed.")
    if ".." in Path(normalized).parts:
        raise ValueError("Path traversal is not allowed.")

    base = Path(root or settings.dvd_source_root).resolve()
    candidate = (base / normalized).resolve(strict=False)

    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise ValueError("Selected candidate is outside the approved DVD source root.") from exc

    if candidate.is_symlink():
        raise ValueError("Symlinks are not allowed for media analysis.")
    if not candidate.exists():
        raise FileNotFoundError("Selected candidate was not found.")
    if not candidate.is_file():
        raise ValueError("Selected candidate is not a regular file.")
    if candidate.suffix.lower() != ".mkv":
        raise ValueError("Only MKV candidates may be analyzed.")

    return candidate
