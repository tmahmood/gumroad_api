"""Upload local files to S3 with Gumroad presigned multipart URLs."""

from __future__ import annotations

from pathlib import Path

import requests

from calc_data.upload_dataclass import PresignedFileUpload, UploadedFilePart

S3_UPLOAD_TIMEOUT_SECONDS = 600.0


def upload_presigned_file(
    presigned_upload: PresignedFileUpload,
) -> list[UploadedFilePart]:
    """Upload one local file to its presigned S3 multipart URLs.

    The file is split into as many chunks as there are presigned parts and
    the chunks are sent in part-number order, so the stored object keeps the
    original byte order.

    Args:
        presigned_upload: Presigned upload details from ``presign_file``.

    Returns:
        One entry per uploaded part with the ``ETag`` header returned by S3,
        sorted by part number.

    Raises:
        ValueError: If the local file size differs from the presigned size,
            or if there are no presigned parts.
        RuntimeError: If S3 does not return an ``ETag`` header.
        requests.HTTPError: If S3 rejects an upload.
        OSError: If the local file cannot be read.
    """
    source_path = Path(presigned_upload.source_path)
    actual_file_size = source_path.stat().st_size
    if actual_file_size != presigned_upload.file_size:
        raise ValueError(
            f"File {source_path} is {actual_file_size} bytes but was presigned "
            f"for {presigned_upload.file_size} bytes"
        )

    number_of_parts = len(presigned_upload.parts)
    if number_of_parts == 0:
        raise ValueError(f"No presigned parts for {source_path}")

    part_size_bytes = (
        presigned_upload.file_size + number_of_parts - 1
    ) // number_of_parts

    uploaded_parts: list[UploadedFilePart] = []
    with source_path.open("rb") as source_file:
        for presigned_part in sorted(
            presigned_upload.parts, key=lambda part: part.part_number
        ):
            part_content = source_file.read(part_size_bytes)
            if not part_content:
                raise ValueError(
                    f"File {source_path} ended before part "
                    f"{presigned_part.part_number} was uploaded"
                )

            response = requests.put(
                presigned_part.presigned_url,
                data=part_content,
                timeout=S3_UPLOAD_TIMEOUT_SECONDS,
            )
            response.raise_for_status()

            etag = response.headers.get("ETag")
            if not etag:
                raise RuntimeError(
                    f"S3 did not return an ETag for part "
                    f"{presigned_part.part_number} of {source_path}"
                )

            uploaded_parts.append(
                UploadedFilePart(
                    part_number=presigned_part.part_number,
                    etag=etag,
                )
            )

    return uploaded_parts


def upload_presigned_files(
    presigned_uploads: list[PresignedFileUpload],
) -> list[list[UploadedFilePart]]:
    """Upload a list of presigned files to S3.

    Args:
        presigned_uploads: Presigned uploads from ``presign_files``.

    Returns:
        Uploaded parts for each input file, in the same order.

    Raises:
        See ``upload_presigned_file``.
    """
    return [
        upload_presigned_file(presigned_upload)
        for presigned_upload in presigned_uploads
    ]
