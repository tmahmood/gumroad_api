from unittest.mock import MagicMock

import pytest
import requests

from calc_data import gumroad
from calc_data.upload_dataclass import (
    PresignedFileUpload,
    PresignedUploadPart,
    UploadedFilePart,
)


@pytest.fixture
def presigned_upload() -> PresignedFileUpload:
    return PresignedFileUpload(
        source_path="/tmp/course.pdf",
        filename="course.pdf",
        file_size=10,
        upload_id="upload_123",
        key="attachments/product_123/upload_123/original/course.pdf",
        file_url="https://gumroad-specials.s3.amazonaws.com/course.pdf",
        parts=[
            PresignedUploadPart(1, "https://example.com/part?partNumber=1"),
            PresignedUploadPart(2, "https://example.com/part?partNumber=2"),
        ],
    )


def test_complete_file_upload_posts_sorted_parts_and_returns_payload(
    presigned_upload: PresignedFileUpload, monkeypatch: pytest.MonkeyPatch
) -> None:
    completion_payload = {
        "success": True,
        "file_url": "https://gumroad-specials.s3.amazonaws.com/course.pdf",
    }
    mock_response = MagicMock(spec=requests.Response)
    mock_response.json.return_value = completion_payload
    mock_request = MagicMock(return_value=mock_response)
    monkeypatch.setattr(gumroad, "gumroad_request", mock_request)

    uploaded_parts = [
        UploadedFilePart(part_number=2, etag='"etag-2"'),
        UploadedFilePart(part_number=1, etag='"etag-1"'),
    ]

    completion_result = gumroad.complete_file_upload(presigned_upload, uploaded_parts)

    mock_request.assert_called_once_with(
        "POST",
        "/v2/files/complete",
        content={
            "upload_id": "upload_123",
            "key": "attachments/product_123/upload_123/original/course.pdf",
            "parts": [
                {"part_number": 1, "etag": '"etag-1"'},
                {"part_number": 2, "etag": '"etag-2"'},
            ],
        },
    )
    assert completion_result == completion_payload


def test_complete_file_upload_raises_when_success_is_false(
    presigned_upload: PresignedFileUpload, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_response = MagicMock(spec=requests.Response)
    mock_response.json.return_value = {
        "success": False,
        "message": "Invalid ETag for part 1",
    }
    monkeypatch.setattr(gumroad, "gumroad_request", MagicMock(return_value=mock_response))

    with pytest.raises(RuntimeError, match="Invalid ETag for part 1"):
        gumroad.complete_file_upload(
            presigned_upload,
            [UploadedFilePart(part_number=1, etag='"etag-1"')],
        )


def test_complete_file_uploads_requires_matching_part_lists(
    presigned_upload: PresignedFileUpload,
) -> None:
    with pytest.raises(ValueError, match="1 presigned uploads but 0 part lists"):
        gumroad.complete_file_uploads([presigned_upload], [])


def test_complete_file_uploads_completes_each_upload(
    presigned_upload: PresignedFileUpload, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_response = MagicMock(spec=requests.Response)
    mock_response.json.return_value = {"success": True, "file_url": "https://example.com"}
    mock_request = MagicMock(return_value=mock_response)
    monkeypatch.setattr(gumroad, "gumroad_request", mock_request)

    uploaded_parts = [UploadedFilePart(part_number=1, etag='"etag-1"')]

    completion_results = gumroad.complete_file_uploads(
        [presigned_upload], [uploaded_parts]
    )

    assert mock_request.call_count == 1
    assert completion_results == [{"success": True, "file_url": "https://example.com"}]
