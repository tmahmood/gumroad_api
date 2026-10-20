from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

from calc_data import gumroad
from calc_data.upload_dataclass import (
    PresignedFileUpload,
    UploadedFilePart,
)


@pytest.fixture
def presigned_readme_upload() -> PresignedFileUpload:
    return PresignedFileUpload(
        source_path="/project/README.md",
        filename="README.md",
        file_size=2048,
        upload_id="upload_123",
        key="attachments/seller/upload_123/original/README.md",
        file_url="https://gumroad-specials.s3.amazonaws.com/README.md",
    )


def test_upload_readme_to_dummy_product_runs_full_upload_flow(
    presigned_readme_upload: PresignedFileUpload, monkeypatch: pytest.MonkeyPatch
) -> None:
    file_summaries = [
        {"filename": "/project/README.md", "file_size": 2048}
    ]
    uploaded_parts = [UploadedFilePart(part_number=1, etag='"etag-1"')]
    canonical_file_url = "https://gumroad-specials.s3.amazonaws.com/README.md"

    mock_collect_file_sizes = MagicMock(return_value=file_summaries)
    mock_presign_files = MagicMock(return_value=[presigned_readme_upload])
    mock_upload_presigned_file = MagicMock(return_value=uploaded_parts)
    mock_complete_file_upload = MagicMock(
        return_value={"success": True, "file_url": canonical_file_url}
    )
    monkeypatch.setattr(gumroad, "collect_file_sizes", mock_collect_file_sizes)
    monkeypatch.setattr(gumroad, "presign_files", mock_presign_files)
    monkeypatch.setattr(gumroad, "upload_presigned_file", mock_upload_presigned_file)
    monkeypatch.setattr(gumroad, "complete_file_upload", mock_complete_file_upload)

    attach_payload = {
        "success": True,
        "file_id_mappings": {"README.md": "file_123"},
    }
    mock_response = MagicMock(spec=requests.Response)
    mock_response.json.return_value = attach_payload
    mock_request = MagicMock(return_value=mock_response)
    monkeypatch.setattr(gumroad, "gumroad_request", mock_request)

    result_payload = gumroad.upload_readme_to_dummy_product()

    expected_readme_path = (
        Path(gumroad.__file__).resolve().parents[2] / "README.md"
    )
    mock_collect_file_sizes.assert_called_once_with([expected_readme_path])
    mock_presign_files.assert_called_once_with(file_summaries)
    mock_upload_presigned_file.assert_called_once_with(presigned_readme_upload)
    mock_complete_file_upload.assert_called_once_with(
        presigned_readme_upload, uploaded_parts
    )
    mock_request.assert_called_once_with(
        "PUT",
        f"/v2/products/{gumroad.DUMMY_PRODUCT}",
        content={"files": [{"url": canonical_file_url}]},
    )
    assert result_payload == attach_payload


def test_upload_readme_to_dummy_product_raises_when_attach_fails(
    presigned_readme_upload: PresignedFileUpload, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        gumroad,
        "collect_file_sizes",
        MagicMock(return_value=[{"filename": "/project/README.md", "file_size": 2048}]),
    )
    monkeypatch.setattr(
        gumroad, "presign_files", MagicMock(return_value=[presigned_readme_upload])
    )
    monkeypatch.setattr(
        gumroad,
        "upload_presigned_file",
        MagicMock(return_value=[UploadedFilePart(part_number=1, etag='"etag-1"')]),
    )
    monkeypatch.setattr(
        gumroad,
        "complete_file_upload",
        MagicMock(
            return_value={
                "success": True,
                "file_url": "https://gumroad-specials.s3.amazonaws.com/README.md",
            }
        ),
    )

    mock_response = MagicMock(spec=requests.Response)
    mock_response.json.return_value = {
        "success": False,
        "message": "Invalid file URL",
    }
    monkeypatch.setattr(gumroad, "gumroad_request", MagicMock(return_value=mock_response))

    with pytest.raises(RuntimeError, match="Invalid file URL"):
        gumroad.upload_readme_to_dummy_product()
