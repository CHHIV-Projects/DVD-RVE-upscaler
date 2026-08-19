from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import settings
from app.services.media_discovery import validate_candidate_relative_path

LOCATION_ROLES = {"ORIGINAL_SOURCE", "FINISHED_DESTINATION"}
LOCATION_ID_NAMESPACE = uuid.UUID("71c33dca-3701-4d36-bfb2-2948bfcbad35")


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _trusted_root() -> Path:
    return Path(settings.trusted_nas_movies_root).expanduser().resolve()


def _validate_display_name(display_name: str) -> str:
    normalized = str(display_name or "").strip()
    if not normalized:
        raise ValueError("A location display name is required.")
    if len(normalized) > 120:
        raise ValueError("Location display name must be 120 characters or fewer.")
    return normalized


def _relative_parts(value: str, *, label: str, allow_current: bool = False) -> tuple[str, ...]:
    normalized = str(value or "").strip()
    if allow_current and normalized in {"", "."}:
        return ()
    if not normalized:
        raise ValueError(f"A {label} is required.")
    if "\\" in normalized:
        raise ValueError(f"{label.capitalize()} must use a controlled relative server path.")
    relative = Path(normalized)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError(f"{label.capitalize()} must be a safe relative path.")
    return relative.parts


def _ensure_no_symlink_components(base: Path, parts: tuple[str, ...], *, label: str) -> None:
    current = base
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"{label.capitalize()} may not contain symlink components.")


def _ensure_contained(candidate: Path, base: Path, *, label: str) -> Path:
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"{label.capitalize()} escapes the trusted NAS Movies hierarchy.") from exc
    return resolved


def validate_location_folder(folder: str, role: str) -> tuple[Path, str]:
    if role not in LOCATION_ROLES:
        raise ValueError("Invalid library location role.")
    trusted = _trusted_root()
    parts = _relative_parts(folder, label="library folder", allow_current=True)
    _ensure_no_symlink_components(trusted, parts, label="library folder")
    resolved = _ensure_contained(trusted.joinpath(*parts), trusted, label="library folder")
    if role == "ORIGINAL_SOURCE" and (not resolved.exists() or not resolved.is_dir()):
        raise ValueError("Original DVD source location must be an existing directory.")
    if resolved.exists() and not resolved.is_dir():
        raise ValueError("Library location must identify a directory.")
    relative = Path(*parts).as_posix() if parts else "."
    return resolved, relative


def validate_destination_subfolder(value: str, destination_root: str | Path) -> str:
    root = Path(destination_root).expanduser().resolve(strict=False)
    parts = _relative_parts(value, label="destination movie folder", allow_current=True)
    _ensure_no_symlink_components(root, parts, label="destination movie folder")
    _ensure_contained(root.joinpath(*parts), root, label="destination movie folder")
    return Path(*parts).as_posix() if parts else "."


def _stable_location_id(role: str, server_root: Path) -> str:
    return uuid.uuid5(LOCATION_ID_NAMESPACE, f"{role}:{server_root}").hex


class OperatorStateStore:
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
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS library_locations (
                    location_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (
                        role IN ('ORIGINAL_SOURCE', 'FINISHED_DESTINATION')
                    ),
                    server_root TEXT NOT NULL,
                    relative_folder TEXT NOT NULL,
                    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (role, server_root)
                );

                CREATE TABLE IF NOT EXISTS operator_workflows (
                    workflow_id TEXT PRIMARY KEY,
                    source_location_id TEXT NOT NULL,
                    source_relative_path TEXT NOT NULL,
                    destination_location_id TEXT,
                    destination_relative_folder TEXT,
                    preparation_id TEXT,
                    rve_job_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (source_location_id)
                        REFERENCES library_locations(location_id),
                    FOREIGN KEY (destination_location_id)
                        REFERENCES library_locations(location_id)
                );

                CREATE INDEX IF NOT EXISTS operator_workflows_updated
                    ON operator_workflows (updated_at DESC);
                CREATE UNIQUE INDEX IF NOT EXISTS operator_workflows_rve_job
                    ON operator_workflows (rve_job_id)
                    WHERE rve_job_id IS NOT NULL;

                CREATE TABLE IF NOT EXISTS historical_workflow_adoptions (
                    workflow_id TEXT PRIMARY KEY,
                    preparation_id TEXT NOT NULL UNIQUE,
                    rve_job_id TEXT NOT NULL UNIQUE,
                    historical_source_absolute_path TEXT NOT NULL,
                    historical_source_relative_path TEXT NOT NULL,
                    adopted_source_size_bytes INTEGER NOT NULL,
                    adopted_source_mtime_ns INTEGER NOT NULL,
                    authorized_at TEXT NOT NULL,
                    FOREIGN KEY (workflow_id)
                        REFERENCES operator_workflows(workflow_id)
                );
                """
            )
        os.chmod(self.database_path, 0o600)
        self._adopt_initial_source()

    def _adopt_initial_source(self) -> None:
        source = Path(settings.dvd_source_root).expanduser().resolve()
        trusted = _trusted_root()
        try:
            relative = source.relative_to(trusted).as_posix()
        except ValueError as exc:
            raise ValueError("Initial DVD source is outside the trusted NAS Movies hierarchy.") from exc
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO library_locations (
                    location_id, display_name, role, server_root, relative_folder,
                    enabled, created_at, updated_at
                ) VALUES (?, ?, 'ORIGINAL_SOURCE', ?, ?, 1, ?, ?)
                """,
                (
                    _stable_location_id("ORIGINAL_SOURCE", source),
                    "DVD Intake",
                    str(source),
                    relative,
                    now,
                    now,
                ),
            )

    def create_location(self, display_name: str, role: str, folder: str) -> dict[str, Any]:
        name = _validate_display_name(display_name)
        root, relative = validate_location_folder(folder, role)
        now = utc_now()
        record = {
            "location_id": _stable_location_id(role, root),
            "display_name": name,
            "role": role,
            "server_root": str(root),
            "relative_folder": relative,
            "enabled": 1,
            "created_at": now,
            "updated_at": now,
        }
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO library_locations (
                        location_id, display_name, role, server_root, relative_folder,
                        enabled, created_at, updated_at
                    ) VALUES (
                        :location_id, :display_name, :role, :server_root, :relative_folder,
                        :enabled, :created_at, :updated_at
                    )
                    """,
                    record,
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("That library location is already configured.") from exc
        return self.get_location(record["location_id"])

    def get_location(
        self,
        location_id: str,
        *,
        role: str | None = None,
        require_enabled: bool = False,
    ) -> dict[str, Any]:
        if not uuid.UUID(str(location_id)).hex == str(location_id):
            raise ValueError("Invalid library location identifier.")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM library_locations WHERE location_id = ?",
                (location_id,),
            ).fetchone()
        if row is None:
            raise FileNotFoundError("Library location was not found.")
        location = dict(row)
        if role is not None and location["role"] != role:
            raise ValueError(f"Library location is not a {role} location.")
        if require_enabled and not bool(location["enabled"]):
            raise ValueError("Library location is disabled.")
        return location

    def list_locations(
        self,
        *,
        role: str | None = None,
        enabled: bool | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        if role is not None:
            if role not in LOCATION_ROLES:
                raise ValueError("Invalid library location role.")
            clauses.append("role = ?")
            values.append(role)
        if enabled is not None:
            clauses.append("enabled = ?")
            values.append(int(enabled))
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM library_locations{where} "
                "ORDER BY role, lower(display_name), location_id",
                values,
            ).fetchall()
        return [dict(row) for row in rows]

    def update_location(
        self,
        location_id: str,
        *,
        display_name: str | None = None,
        enabled: bool | None = None,
    ) -> dict[str, Any]:
        self.get_location(location_id)
        updates: dict[str, Any] = {"updated_at": utc_now()}
        if display_name is not None:
            updates["display_name"] = _validate_display_name(display_name)
        if enabled is not None:
            updates["enabled"] = int(enabled)
        if len(updates) == 1:
            raise ValueError("No library location update was supplied.")
        assignments = ", ".join(f"{column} = ?" for column in updates)
        with self._connect() as connection:
            connection.execute(
                f"UPDATE library_locations SET {assignments} WHERE location_id = ?",
                (*updates.values(), location_id),
            )
        return self.get_location(location_id)

    def create_workflow(self, source_location_id: str, source_relative_path: str) -> dict[str, Any]:
        location = self.get_location(
            source_location_id,
            role="ORIGINAL_SOURCE",
            require_enabled=True,
        )
        source = validate_candidate_relative_path(
            source_relative_path,
            root=location["server_root"],
        )
        relative = source.relative_to(Path(location["server_root"])).as_posix()
        current = self.get_current_workflow()
        if (
            current
            and current["source_location_id"] == source_location_id
            and current["source_relative_path"] == relative
            and current["preparation_id"] is None
            and current["rve_job_id"] is None
        ):
            return current
        now = utc_now()
        workflow_id = uuid.uuid4().hex
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO operator_workflows (
                    workflow_id, source_location_id, source_relative_path,
                    destination_location_id, destination_relative_folder,
                    preparation_id, rve_job_id, created_at, updated_at
                ) VALUES (?, ?, ?, NULL, NULL, NULL, NULL, ?, ?)
                """,
                (workflow_id, source_location_id, relative, now, now),
            )
        return self.get_workflow(workflow_id)

    def get_workflow(self, workflow_id: str) -> dict[str, Any]:
        if not uuid.UUID(str(workflow_id)).hex == str(workflow_id):
            raise ValueError("Invalid workflow identifier.")
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    w.*,
                    source.display_name AS source_location_name,
                    destination.display_name AS destination_location_name
                FROM operator_workflows AS w
                JOIN library_locations AS source
                    ON source.location_id = w.source_location_id
                LEFT JOIN library_locations AS destination
                    ON destination.location_id = w.destination_location_id
                WHERE w.workflow_id = ?
                """,
                (workflow_id,),
            ).fetchone()
        if row is None:
            raise FileNotFoundError("Workflow was not found.")
        return dict(row)

    def get_current_workflow(self) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT workflow_id FROM operator_workflows "
                "ORDER BY updated_at DESC, created_at DESC LIMIT 1"
            ).fetchone()
        return self.get_workflow(row["workflow_id"]) if row else None

    def set_destination(
        self,
        workflow_id: str,
        destination_location_id: str,
    ) -> dict[str, Any]:
        self.get_workflow(workflow_id)
        self.get_location(
            destination_location_id,
            role="FINISHED_DESTINATION",
            require_enabled=True,
        )
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE operator_workflows
                SET destination_location_id = ?,
                    destination_relative_folder = ?,
                    updated_at = ?
                WHERE workflow_id = ?
                """,
                (destination_location_id, None, utc_now(), workflow_id),
            )
        return self.get_workflow(workflow_id)

    def associate_preparation(self, workflow_id: str, preparation_id: str) -> dict[str, Any]:
        workflow = self.get_workflow(workflow_id)
        if workflow["preparation_id"] not in {None, preparation_id}:
            raise ValueError("Workflow is already associated with a different preparation.")
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE operator_workflows
                SET preparation_id = ?, updated_at = ?
                WHERE workflow_id = ?
                """,
                (preparation_id, utc_now(), workflow_id),
            )
        return self.get_workflow(workflow_id)

    def associate_rve_job(self, preparation_id: str, job_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT workflow_id, rve_job_id FROM operator_workflows "
                "WHERE preparation_id = ? ORDER BY updated_at DESC LIMIT 1",
                (preparation_id,),
            ).fetchone()
            if row is None:
                return None
            if row["rve_job_id"] not in {None, job_id}:
                raise ValueError("Workflow is already associated with a different RVE job.")
            connection.execute(
                """
                UPDATE operator_workflows
                SET rve_job_id = ?, updated_at = ?
                WHERE workflow_id = ?
                """,
                (job_id, utc_now(), row["workflow_id"]),
            )
        return self.get_workflow(row["workflow_id"])

    def create_historical_workflow_adoption(
        self,
        *,
        source_location_id: str,
        source_relative_path: str,
        destination_location_id: str,
        preparation_id: str,
        rve_job_id: str,
        historical_source_absolute_path: str,
        historical_source_relative_path: str,
        source_size_bytes: int,
        source_mtime_ns: int,
    ) -> dict[str, Any]:
        source_location = self.get_location(
            source_location_id,
            role="ORIGINAL_SOURCE",
            require_enabled=True,
        )
        self.get_location(
            destination_location_id,
            role="FINISHED_DESTINATION",
            require_enabled=True,
        )
        source = validate_candidate_relative_path(
            source_relative_path,
            root=source_location["server_root"],
        )
        relative = source.relative_to(Path(source_location["server_root"])).as_posix()
        for value, label in (
            (preparation_id, "preparation"),
            (rve_job_id, "RVE job"),
        ):
            try:
                if uuid.UUID(str(value)).hex != str(value):
                    raise ValueError
            except ValueError as exc:
                raise ValueError(f"Invalid historical {label} identifier.") from exc
        if not historical_source_absolute_path or not historical_source_relative_path:
            raise ValueError("Historical source identity evidence is required.")
        now = utc_now()
        workflow_id = uuid.uuid4().hex
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO operator_workflows (
                        workflow_id, source_location_id, source_relative_path,
                        destination_location_id, destination_relative_folder,
                        preparation_id, rve_job_id, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?)
                    """,
                    (
                        workflow_id,
                        source_location_id,
                        relative,
                        destination_location_id,
                        preparation_id,
                        rve_job_id,
                        now,
                        now,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO historical_workflow_adoptions (
                        workflow_id, preparation_id, rve_job_id,
                        historical_source_absolute_path,
                        historical_source_relative_path,
                        adopted_source_size_bytes, adopted_source_mtime_ns,
                        authorized_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        workflow_id,
                        preparation_id,
                        rve_job_id,
                        historical_source_absolute_path,
                        historical_source_relative_path,
                        int(source_size_bytes),
                        int(source_mtime_ns),
                        now,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                "Historical preparation or RVE evidence is already associated."
            ) from exc
        return self.get_workflow(workflow_id)

    def get_historical_workflow_adoption(
        self,
        workflow_id: str,
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM historical_workflow_adoptions WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchone()
        return dict(row) if row else None

    def find_workflow_by_preparation(self, preparation_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT workflow_id FROM operator_workflows "
                "WHERE preparation_id = ? ORDER BY updated_at DESC LIMIT 1",
                (preparation_id,),
            ).fetchone()
        return self.get_workflow(row["workflow_id"]) if row else None

    def find_workflow_by_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT workflow_id FROM operator_workflows WHERE rve_job_id = ?",
                (job_id,),
            ).fetchone()
        return self.get_workflow(row["workflow_id"]) if row else None


def public_location(location: dict[str, Any]) -> dict[str, Any]:
    relative = location["relative_folder"]
    display_path = "/movies" if relative == "." else f"/movies/{relative}"
    return {
        "location_id": location["location_id"],
        "display_name": location["display_name"],
        "role": location["role"],
        "folder": relative,
        "display_path": display_path,
        "enabled": bool(location["enabled"]),
        "created_at": location["created_at"],
        "updated_at": location["updated_at"],
    }


def public_workflow(workflow: dict[str, Any]) -> dict[str, Any]:
    return {
        "workflow_id": workflow["workflow_id"],
        "source_location_id": workflow["source_location_id"],
        "source_location_name": workflow["source_location_name"],
        "source_relative_path": workflow["source_relative_path"],
        "destination_location_id": workflow["destination_location_id"],
        "destination_location_name": workflow["destination_location_name"],
        "destination_relative_folder": None,
        "preparation_id": workflow["preparation_id"],
        "rve_job_id": workflow["rve_job_id"],
        "created_at": workflow["created_at"],
        "updated_at": workflow["updated_at"],
    }
