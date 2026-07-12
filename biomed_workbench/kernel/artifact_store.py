"""Content-addressed project storage for large scientific artifact payloads."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
from typing import Mapping

from .identity import validate_identifier


_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_MEDIA_TYPE_RE = re.compile(r"^[a-z0-9][a-z0-9.+-]*/[a-z0-9][a-z0-9.+-]*$")
_OBJECT_KEY_RE = re.compile(r"^sha256/([0-9a-f]{2})/([0-9a-f]{64})/payload$")


@dataclass(frozen=True)
class ArtifactPayload:
    """A machine-path-free reference to one content-addressed project object."""

    role: str
    object_key: str
    media_type: str
    byte_size: int
    sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "role", validate_identifier(self.role, "artifact payload role"))
        if not isinstance(self.sha256, str) or not _DIGEST_RE.fullmatch(self.sha256):
            raise ValueError("artifact payload SHA-256 is invalid")
        if not isinstance(self.object_key, str) or "\\" in self.object_key:
            raise ValueError("artifact payload object key must be a project-relative POSIX key")
        path = PurePosixPath(self.object_key)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError("artifact payload object key must not contain traversal or absolute paths")
        match = _OBJECT_KEY_RE.fullmatch(self.object_key)
        if not match or match.group(1) != self.sha256[:2] or match.group(2) != self.sha256:
            raise ValueError("artifact payload object key must match its SHA-256 identity")
        if not isinstance(self.media_type, str) or not _MEDIA_TYPE_RE.fullmatch(self.media_type):
            raise ValueError("artifact payload media type is invalid")
        if not isinstance(self.byte_size, int) or isinstance(self.byte_size, bool) or self.byte_size < 0:
            raise ValueError("artifact payload byte size must be a nonnegative integer")

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "ArtifactPayload":
        if set(payload) != {"role", "object_key", "media_type", "byte_size", "sha256"}:
            raise ValueError("artifact payload fields are incomplete or unsupported")
        return cls(**dict(payload))

    def to_dict(self) -> dict[str, object]:
        return {
            "role": self.role,
            "object_key": self.object_key,
            "media_type": self.media_type,
            "byte_size": self.byte_size,
            "sha256": self.sha256,
        }


class ProjectArtifactStore:
    """Import and verify regular files under one runtime project root."""

    def __init__(self, root: str | os.PathLike[str]):
        requested_root = Path(root).expanduser()
        if requested_root.exists() and requested_root.is_symlink():
            raise ValueError("artifact store root must not be a symlink")
        self.root = requested_root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        if self.root.is_symlink() or not self.root.is_dir():
            raise ValueError("artifact store root must be a real directory")

    @staticmethod
    def _copy_and_digest(source_fd: int, target: Path) -> tuple[str, int]:
        digest = hashlib.sha256()
        size = 0
        with os.fdopen(source_fd, "rb") as reader, target.open("wb") as writer:
            while chunk := reader.read(1024 * 1024):
                writer.write(chunk)
                digest.update(chunk)
                size += len(chunk)
            writer.flush()
            os.fsync(writer.fileno())
        return digest.hexdigest(), size

    def import_file(self, source: str | os.PathLike[str], *, role: str, media_type: str) -> ArtifactPayload:
        source_path = Path(source).expanduser()
        try:
            source_lstat = source_path.lstat()
            if stat.S_ISLNK(source_lstat.st_mode):
                raise ValueError("artifact source must be a regular non-symlink file")
            source_fd = os.open(source_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except OSError as exc:
            raise ValueError("artifact source is unavailable") from exc
        source_stat = os.fstat(source_fd)
        if (
            not stat.S_ISREG(source_stat.st_mode)
            or source_stat.st_dev != source_lstat.st_dev
            or source_stat.st_ino != source_lstat.st_ino
        ):
            os.close(source_fd)
            raise ValueError("artifact source must be a stable regular non-symlink file")

        staging = self.root / ".staging"
        staging.mkdir(exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(prefix="import-", dir=staging, delete=False) as temporary:
                temporary_path = Path(temporary.name)
            owned_source_fd = source_fd
            source_fd = -1
            sha256, byte_size = self._copy_and_digest(owned_source_fd, temporary_path)
            object_key = f"sha256/{sha256[:2]}/{sha256}/payload"
            payload = ArtifactPayload(role=role, object_key=object_key, media_type=media_type, byte_size=byte_size, sha256=sha256)
            destination = self.root / PurePosixPath(payload.object_key)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.parent.resolve().is_relative_to(self.root):
                raise ValueError("artifact destination escaped the project store")
            if destination.exists():
                temporary_path.unlink()
            else:
                os.replace(temporary_path, destination)
            temporary_path = None
            self.resolve(payload)
            return payload
        finally:
            if source_fd >= 0:
                os.close(source_fd)
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def resolve(self, payload: ArtifactPayload) -> Path:
        if not isinstance(payload, ArtifactPayload):
            raise TypeError("resolve requires an ArtifactPayload")
        candidate = self.root / PurePosixPath(payload.object_key)
        try:
            resolved = candidate.resolve(strict=True)
            file_stat = resolved.stat()
        except OSError as exc:
            raise ValueError("artifact payload is unavailable") from exc
        if not resolved.is_relative_to(self.root) or candidate.is_symlink() or not stat.S_ISREG(file_stat.st_mode):
            raise ValueError("artifact payload escaped the store or is not a regular file")
        if file_stat.st_size != payload.byte_size:
            raise ValueError("artifact payload size differs from its recorded identity")
        digest = hashlib.sha256()
        with resolved.open("rb") as reader:
            while chunk := reader.read(1024 * 1024):
                digest.update(chunk)
        if digest.hexdigest() != payload.sha256:
            raise ValueError("artifact payload digest differs from its recorded identity")
        return resolved

    def materialize(self, payload: ArtifactPayload, target: str | os.PathLike[str]) -> Path:
        """Atomically copy one verified payload to a caller-owned runtime file."""
        source = self.resolve(payload)
        try:
            source_fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except OSError as exc:
            raise ValueError("artifact payload is unavailable") from exc
        source_stat = os.fstat(source_fd)
        if not stat.S_ISREG(source_stat.st_mode) or source_stat.st_size != payload.byte_size:
            os.close(source_fd)
            raise ValueError("artifact payload type or size differs from its recorded identity")
        target_path = Path(target)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(prefix="materialize-", dir=target_path.parent, delete=False) as temporary:
                temporary_path = Path(temporary.name)
            owned_source_fd = source_fd
            source_fd = -1
            sha256, byte_size = self._copy_and_digest(owned_source_fd, temporary_path)
            if sha256 != payload.sha256 or byte_size != payload.byte_size:
                raise ValueError("artifact payload changed during materialization")
            os.replace(temporary_path, target_path)
            temporary_path = None
            return target_path
        finally:
            if source_fd >= 0:
                os.close(source_fd)
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
