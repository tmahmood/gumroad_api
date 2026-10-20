from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

from calc_data import s3_upload
from calc_data.upload_dataclass import (
    PresignedFileUpload,
    PresignedUploadPart,
    UploadedFilePart,
)


@pytest.fixture
def presigned_upload(tmp_path: Path) -> PresignedFileUpload:
    source_file = tmp_path / "course.pdf"
    source_file.write_bytes(b"0123456789")

    return PresignedFileUpload(
        source_path=str(source_file),
        filename="course.pdf",
        file_size=10,
        upload_id="upload_123",
        key="attachments/course.pdf",
        file_url="https://gumroad-specials.s3.amazonaws.com/course.pdf",
        parts=[
            PresignedUploadPart(1, "https://example.com/part?partNumber=1"),
            PresignedUploadPart(2, "https://example.com/part?partNumber=2"),
            PresignedUploadPart(3, "https://example.com/part?partNumber=3"),
        ],
    )


def test_upload_presigned_file_sends_chunks_in_order_and_captures_etags(
    presigned_upload: PresignedFileUpload, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_put = MagicMock()
    mock_put.side_effect = [
        build_mock_response('"etag-1"'),
        build_mock_response('"etag-2"'),
        build_mock_response('"etag-3"'),
    ]
    monkeypatch.setattr(s3_upload.requests, "put", mock_put)

    uploaded_parts = s3_upload.upload_presigned_file(presigned_upload)

    assert [call.kwargs["data"] for call in mock_put.call_args_list] == [
        b"0123",
        b"4567",
        b"89",
    ]
    assert [
        call.args[0] for call in mock_put.call_args_list
    ] == [
        "https://example.com/part?partNumber=1",
        "https://example.com/part?partNumber=2",
        "https://example.com/part?partNumber=3",
    ]
    assert uploaded_parts == [
        UploadedFilePart(part_number=1, etag='"etag-1"'),
        UploadedFilePart(part_number=2, etag='"etag-2"'),
        UploadedFilePart(part_number=3, etag='"etag-3"'),
    ]


def test_upload_presigned_file_raises_when_etag_is_missing(
    presigned_upload: PresignedFileUpload, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_put = MagicMock(return_value=build_mock_response(None))
    monkeypatch.setattr(s3_upload.requests, "put", mock_put)

    with pytest.raises(RuntimeError, match="ETag"):
        s3_upload.upload_presigned_file(presigned_upload)


def test_upload_presigned_file_raises_when_local_size_differs(
    presigned_upload: PresignedFileUpload, monkeypatch: pytest.MonkeyPatch
) -> None:
    presigned_upload.file_size = 999
    mock_put = MagicMock()
    monkeypatch.setattr(s3_upload.requests, "put", mock_put)

    with pytest.raises(ValueError, match="presigned"):
        s3_upload.upload_presigned_file(presigned_upload)

    mock_put.assert_not_called()


def test_upload_presigned_file_raises_without_parts(
    presigned_upload: PresignedFileUpload, monkeypatch: pytest.MonkeyPatch
) -> None:
    presigned_upload.parts = []
    mock_put = MagicMock()
    monkeypatch.setattr(s3_upload.requests, "put", mock_put)

    with pytest.raises(ValueError, match="No presigned parts"):
        s3_upload.upload_presigned_file(presigned_upload)

    mock_put.assert_not_called()


def test_upload_presigned_files_uploads_each_file(
    presigned_upload: PresignedFileUpload, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    second_source_file = tmp_path / "workbook.pdf"
    second_source_file.write_bytes(b"abcdefghij")
    second_upload = PresignedFileUpload(
        source_path=str(second_source_file),
        filename="workbook.pdf",
        file_size=10,
        upload_id="upload_456",
        key="attachments/workbook.pdf",
        file_url="https://gumroad-specials.s3.amazonaws.com/workbook.pdf",
        parts=[PresignedUploadPart(1, "https://example.com/workbook")],
    )

    mock_put = MagicMock(
        side_effect=[
            build_mock_response('"etag-a"'),
            build_mock_response('"etag-b"'),
            build_mock_response('"etag-c"'),
            build_mock_response('"etag-d"'),
        ]
    )
    monkeypatch.setattr(s3_upload.requests, "put", mock_put)

    uploaded_parts_by_file = s3_upload.upload_presigned_files(
        [presigned_upload, second_upload]
    )

    assert len(uploaded_parts_by_file) == 2
    assert len(uploaded_parts_by_file[0]) == 3
    assert uploaded_parts_by_file[1] == [
        UploadedFilePart(part_number=1, etag='"etag-d"')
    ]


def build_mock_response(etag: str | None) -> MagicMock:
    mock_response = MagicMock(spec=requests.Response)
    mock_response.headers = {"ETag": etag} if etag else {}
    return mock_response
