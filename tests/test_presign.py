from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

from calc_data import gumroad
from calc_data.upload_dataclass import PresignedFileUpload, PresignedUploadPart
from calc_data.utilities import FileSummary


def test_presign_files_returns_upload_details_for_each_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    course_pdf_path = tmp_path / "course.pdf"
    presign_response_payload = {
        "success": True,
        "upload_id": "upload_123",
        "key": "attachments/product_123/upload_123/original/course.pdf",
        "file_url": "https://gumroad-specials.s3.amazonaws.com/attachments/course.pdf",
        "parts": [
            {
                "part_number": 1,
                "presigned_url": "https://gumroad-specials.s3.amazonaws.com/course.pdf?partNumber=1",
            },
            {
                "part_number": 2,
                "presigned_url": "https://gumroad-specials.s3.amazonaws.com/course.pdf?partNumber=2",
            },
        ],
    }

    mock_response = MagicMock(spec=requests.Response)
    mock_response.json.return_value = presign_response_payload
    mock_request = MagicMock(return_value=mock_response)
    monkeypatch.setattr(gumroad, "gumroad_request", mock_request)

    file_summaries: list[FileSummary] = [
        {"filename": str(course_pdf_path), "file_size": 104857600}
    ]

    presigned_uploads = gumroad.presign_files(file_summaries)

    mock_request.assert_called_once_with(
        "POST",
        "/v2/files/presign",
        content={"filename": "course.pdf", "file_size": 104857600},
    )

    assert len(presigned_uploads) == 1
    presigned_upload = presigned_uploads[0]
    assert presigned_upload.source_path == str(course_pdf_path)
    assert presigned_upload.filename == "course.pdf"
    assert presigned_upload.file_size == 104857600
    assert presigned_upload.upload_id == "upload_123"
    assert presigned_upload.key == presign_response_payload["key"]
    assert presigned_upload.file_url == presign_response_payload["file_url"]
    assert [part.part_number for part in presigned_upload.parts] == [1, 2]
    assert presigned_upload.parts[1].presigned_url.endswith("partNumber=2")


def test_presign_files_raises_when_gumroad_rejects_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_response = MagicMock(spec=requests.Response)
    mock_response.json.return_value = {
        "success": False,
        "message": "File is too large",
    }
    monkeypatch.setattr(gumroad, "gumroad_request", MagicMock(return_value=mock_response))

    file_summaries: list[FileSummary] = [
        {"filename": str(tmp_path / "course.pdf"), "file_size": 104857600}
    ]

    with pytest.raises(RuntimeError, match="File is too large"):
        gumroad.presign_files(file_summaries)


def test_presigned_file_upload_to_dict_includes_parts(tmp_path: Path) -> None:
    presigned_upload = PresignedFileUpload(
        source_path=str(tmp_path / "course.pdf"),
        filename="course.pdf",
        file_size=123,
        upload_id="upload_123",
        key="attachments/course.pdf",
        file_url="https://example.com/course.pdf",
        parts=[PresignedUploadPart(part_number=1, presigned_url="https://example.com/part")],
    )

    serialized_upload = presigned_upload.to_dict()

    assert serialized_upload["filename"] == "course.pdf"
    assert serialized_upload["parts"] == [
        {"part_number": 1, "presigned_url": "https://example.com/part"}
    ]
