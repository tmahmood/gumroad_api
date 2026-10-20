"""Data classes for Gumroad presigned file uploads."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PresignedUploadPart:
    """A single multipart upload part returned by the presign endpoint."""

    part_number: int
    presigned_url: str

    def to_dict(self) -> dict[str, int | str]:
        """Convert the part to a JSON-serializable dict."""
        return {
            "part_number": self.part_number,
            "presigned_url": self.presigned_url,
        }


@dataclass
class UploadedFilePart:
    """An S3 multipart part that has been uploaded successfully."""

    part_number: int
    etag: str

    def to_dict(self) -> dict[str, int | str]:
        """Convert the uploaded part to a JSON-serializable dict."""
        return {
            "part_number": self.part_number,
            "etag": self.etag,
        }


@dataclass
class PresignedFileUpload:
    """Presigned upload details for one file.

    ``source_path`` is the local path that was presigned, while ``filename``
    is the base name sent to Gumroad and used in the object key.
    """

    source_path: str
    filename: str
    file_size: int
    upload_id: str
    key: str
    file_url: str
    parts: list[PresignedUploadPart] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert the upload to a JSON-serializable dict."""
        return {
            "source_path": self.source_path,
            "filename": self.filename,
            "file_size": self.file_size,
            "upload_id": self.upload_id,
            "key": self.key,
            "file_url": self.file_url,
            "parts": [part.to_dict() for part in self.parts],
        }
