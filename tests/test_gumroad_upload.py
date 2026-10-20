from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import requests

from calc_data import gumroad


def test_put_sends_put_request_with_correct_parameters(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GUMROAD_ACCESS_TOKEN", "dummy_token_123")

    mock_response = MagicMock(spec=requests.Response)
    mock_response.status_code = 200
    mock_request = MagicMock(return_value=mock_response)
    monkeypatch.setattr(requests, "request", mock_request)

    response = gumroad.put("/v2/products/product_abc", content={"published": True})

    assert response == mock_response
    mock_request.assert_called_once_with(
        method="PUT",
        url="https://api.gumroad.com/v2/products/product_abc",
        headers={
            "Authorization": "Bearer dummy_token_123",
            "Accept": "application/json",
        },
        params=None,
        json={"published": True},
        data=None,
        files=None,
        timeout=30.0,
    )


def test_put_supports_files_and_data_parameters(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GUMROAD_ACCESS_TOKEN", "dummy_token_123")

    mock_response = MagicMock(spec=requests.Response)
    mock_response.status_code = 200
    mock_request = MagicMock(return_value=mock_response)
    monkeypatch.setattr(requests, "request", mock_request)

    dummy_files = {"file": ("test.txt", b"sample content")}
    dummy_data = {"name": "Updated Product Name"}

    response = gumroad.put(
        "/v2/products/product_abc",
        files=dummy_files,
        data=dummy_data,
        timeout=15.0,
    )

    assert response == mock_response
    mock_request.assert_called_once_with(
        method="PUT",
        url="https://api.gumroad.com/v2/products/product_abc",
        headers={
            "Authorization": "Bearer dummy_token_123",
            "Accept": "application/json",
        },
        params=None,
        json=None,
        data=dummy_data,
        files=dummy_files,
        timeout=15.0,
    )


def test_gumroad_request_supports_custom_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GUMROAD_ACCESS_TOKEN", "dummy_token_123")

    mock_response = MagicMock(spec=requests.Response)
    mock_response.status_code = 200
    mock_request = MagicMock(return_value=mock_response)
    monkeypatch.setattr(requests, "request", mock_request)

    response = gumroad.gumroad_request(
        "PUT",
        "/v2/products/custom_id",
        headers={"X-Custom-Header": "CustomValue"},
    )

    assert response == mock_response
    mock_request.assert_called_once_with(
        method="PUT",
        url="https://api.gumroad.com/v2/products/custom_id",
        headers={
            "Authorization": "Bearer dummy_token_123",
            "Accept": "application/json",
            "X-Custom-Header": "CustomValue",
        },
        params=None,
        json=None,
        data=None,
        files=None,
        timeout=30.0,
    )


def test_prepare_files_for_put_formats_file_paths(tmp_path: Path) -> None:
    first_test_file = tmp_path / "document_alpha.txt"
    second_test_file = tmp_path / "document_beta.pdf"
    first_test_file.write_bytes(b"first content")
    second_test_file.write_bytes(b"second content")

    prepared_results = gumroad.prepare_files_for_put([str(first_test_file), second_test_file])

    assert len(prepared_results) == 2

    first_field_name, (first_file_name, first_file_stream) = prepared_results[0]
    assert first_field_name == "file"
    assert first_file_name == "document_alpha.txt"
    assert first_file_stream.read() == b"first content"
    first_file_stream.close()

    second_field_name, (second_file_name, second_file_stream) = prepared_results[1]
    assert second_field_name == "file"
    assert second_file_name == "document_beta.pdf"
    assert second_file_stream.read() == b"second content"
    second_file_stream.close()


def test_prepare_files_for_put_raises_error_for_nonexistent_file(tmp_path: Path) -> None:
    missing_file_path = tmp_path / "nonexistent_file.txt"

    with pytest.raises(FileNotFoundError, match="File not found"):
        gumroad.prepare_files_for_put([missing_file_path])


def test_prepare_files_for_put_handles_tuples_and_custom_streams() -> None:
    custom_byte_stream = BytesIO(b"in-memory data")
    custom_byte_stream.name = "memory_file.dat"
    explicit_tuple_entry = ("custom_field", ("direct.bin", b"binary bytes"))

    prepared_results = gumroad.prepare_files_for_put([custom_byte_stream, explicit_tuple_entry])

    assert len(prepared_results) == 2
    assert prepared_results[0] == ("file", ("memory_file.dat", custom_byte_stream))
    assert prepared_results[1] == explicit_tuple_entry


def test_upload_product_file_list_prepares_and_sends_only_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    test_artifact_path = tmp_path / "release_archive.zip"
    test_artifact_path.write_bytes(b"zip archive payload")

    mock_response = MagicMock(spec=requests.Response)
    mock_response.status_code = 200
    mock_put = MagicMock(return_value=mock_response)
    monkeypatch.setattr(gumroad, "put", mock_put)

    response = gumroad.upload_product_file_list(
        "product_batch_123",
        [test_artifact_path],
        timeout=25.0,
        verify=True,
    )

    assert response == mock_response
    mock_put.assert_called_once()
    called_endpoint = mock_put.call_args[0][0]
    assert called_endpoint == "/v2/products/product_batch_123"

    called_keyword_arguments = mock_put.call_args[1]
    assert "data" not in called_keyword_arguments
    assert "params" not in called_keyword_arguments
    assert "content" not in called_keyword_arguments
    assert called_keyword_arguments["timeout"] == 25.0
    assert called_keyword_arguments["verify"] is True

    prepared_files = called_keyword_arguments["files"]
    assert len(prepared_files) == 1
    field_identifier, (file_basename, binary_stream) = prepared_files[0]
    assert field_identifier == "file"
    assert file_basename == "release_archive.zip"
    binary_stream.close()


def test_gumroad_request_raises_error_when_success_is_false_with_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GUMROAD_ACCESS_TOKEN", "dummy_token_123")

    mock_response = MagicMock(spec=requests.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "success": False,
        "message": "Resource not found or unauthorized",
    }
    monkeypatch.setattr(requests, "request", MagicMock(return_value=mock_response))

    with pytest.raises(
        RuntimeError,
        match="Gumroad API request failed: Resource not found or unauthorized",
    ):
        gumroad.gumroad_request("GET", "/v2/products/invalid_id")


def test_gumroad_request_raises_error_when_success_is_false_with_error_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GUMROAD_ACCESS_TOKEN", "dummy_token_123")

    mock_response = MagicMock(spec=requests.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "success": False,
        "error": "Invalid product credentials",
    }
    monkeypatch.setattr(requests, "request", MagicMock(return_value=mock_response))

    with pytest.raises(
        RuntimeError,
        match="Gumroad API request failed: Invalid product credentials",
    ):
        gumroad.gumroad_request("POST", "/v2/products")


def test_gumroad_request_raises_error_when_success_is_false_without_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GUMROAD_ACCESS_TOKEN", "dummy_token_123")

    mock_response = MagicMock(spec=requests.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {"success": False}
    monkeypatch.setattr(requests, "request", MagicMock(return_value=mock_response))

    with pytest.raises(
        RuntimeError,
        match="Gumroad API request failed: Request returned success=false",
    ):
        gumroad.gumroad_request("PUT", "/v2/products/target_id")


def test_gumroad_request_succeeds_when_success_is_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GUMROAD_ACCESS_TOKEN", "dummy_token_123")

    mock_response = MagicMock(spec=requests.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {"success": True, "product": {"name": "Test"}}
    monkeypatch.setattr(requests, "request", MagicMock(return_value=mock_response))

    response = gumroad.gumroad_request("GET", "/v2/products/valid_id")
    assert response == mock_response


def test_request_presigned_file_upload_url_sends_post_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_response = MagicMock(spec=requests.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "success": True,
        "url": "https://s3.amazonaws.com/bucket/upload_target",
    }
    mock_post = MagicMock(return_value=mock_response)
    monkeypatch.setattr(gumroad, "post", mock_post)

    response = gumroad.request_presigned_file_upload_url(
        filename="distribution.zip",
        file_size=1024,
        timeout=12.0,
    )

    assert response == mock_response
    mock_post.assert_called_once_with(
        "/v2/files/presign",
        content={"filename": "distribution.zip", "file_name": "distribution.zip", "file_size": 1024},
        params=None,
        timeout=12.0,
    )


def test_request_presigned_file_upload_url_raises_error_when_file_size_exceeds_20gb() -> None:
    twenty_gb_plus_one_byte = (20 * 1024 * 1024 * 1024) + 1
    with pytest.raises(ValueError, match="File size exceeds maximum allowed size of 20GB"):
        gumroad.request_presigned_file_upload_url(
            filename="large_archive.iso",
            file_size=twenty_gb_plus_one_byte,
        )


def test_request_presigned_file_upload_url_accepts_file_size_at_20gb_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exact_twenty_gb_bytes = 20 * 1024 * 1024 * 1024
    mock_response = MagicMock(spec=requests.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {"success": True, "url": "https://s3.amazonaws.com/bucket/target"}
    mock_post = MagicMock(return_value=mock_response)
    monkeypatch.setattr(gumroad, "post", mock_post)

    response = gumroad.request_presigned_file_upload_url(
        filename="exact_limit.iso",
        file_size=exact_twenty_gb_bytes,
    )

    assert response == mock_response
    mock_post.assert_called_once_with(
        "/v2/files/presign",
        content={"filename": "exact_limit.iso", "file_name": "exact_limit.iso", "file_size": exact_twenty_gb_bytes},
        params=None,
        timeout=30.0,
    )


def test_extract_presigned_parts_from_presign_response_with_dict_parts() -> None:
    multipart_payload = {
        "success": True,
        "parts": [
            {"part_number": 1, "presigned_url": "https://s3.amazonaws.com/bucket/part1", "size": 500},
            {"part_number": 2, "presigned_url": "https://s3.amazonaws.com/bucket/part2", "size": 500},
        ],
    }
    extracted_parts = gumroad.extract_presigned_parts_from_presign_response(multipart_payload)
    assert len(extracted_parts) == 2
    assert extracted_parts[0] == {
        "part_number": 1,
        "presigned_url": "https://s3.amazonaws.com/bucket/part1",
        "size": 500,
    }
    assert extracted_parts[1] == {
        "part_number": 2,
        "presigned_url": "https://s3.amazonaws.com/bucket/part2",
        "size": 500,
    }


def test_extract_presigned_parts_from_presign_response_with_string_parts() -> None:
    string_parts_payload = {
        "success": True,
        "data": {
            "parts": [
                "https://s3.amazonaws.com/bucket/chunk_alpha",
                "https://s3.amazonaws.com/bucket/chunk_beta",
            ]
        },
    }
    extracted_parts = gumroad.extract_presigned_parts_from_presign_response(string_parts_payload)
    assert len(extracted_parts) == 2
    assert extracted_parts[0] == {
        "part_number": 1,
        "presigned_url": "https://s3.amazonaws.com/bucket/chunk_alpha",
    }
    assert extracted_parts[1] == {
        "part_number": 2,
        "presigned_url": "https://s3.amazonaws.com/bucket/chunk_beta",
    }


def test_extract_presigned_parts_from_presign_response_fallback_to_single_url() -> None:
    single_url_payload = {"success": True, "url": "https://s3.amazonaws.com/bucket/single_target"}
    extracted_parts = gumroad.extract_presigned_parts_from_presign_response(single_url_payload)
    assert len(extracted_parts) == 1
    assert extracted_parts[0] == {
        "part_number": 1,
        "presigned_url": "https://s3.amazonaws.com/bucket/single_target",
    }


def test_upload_file_to_presigned_parts_single_part(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_put_response = MagicMock(spec=requests.Response)
    mock_put_response.status_code = 200
    mock_requests_put = MagicMock(return_value=mock_put_response)
    monkeypatch.setattr(requests, "put", mock_requests_put)

    responses = gumroad.upload_file_to_presigned_parts(
        parts=[{"part_number": 1, "presigned_url": "https://s3.amazonaws.com/bucket/part1"}],
        file_path_or_content=b"complete file content",
    )

    assert len(responses) == 1
    assert responses[0] == mock_put_response
    mock_requests_put.assert_called_once_with(
        url="https://s3.amazonaws.com/bucket/part1",
        data=b"complete file content",
        headers=None,
        timeout=60.0,
    )


def test_upload_file_to_presigned_parts_multiple_parts_partitions_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_put_response = MagicMock(spec=requests.Response)
    mock_put_response.status_code = 200
    mock_requests_put = MagicMock(return_value=mock_put_response)
    monkeypatch.setattr(requests, "put", mock_requests_put)

    sample_bytes = b"0123456789"  # 10 bytes across 3 parts: chunks of 4, 4, 2 bytes
    parts = [
        {"part_number": 1, "presigned_url": "https://s3.amazonaws.com/bucket/part_1"},
        {"part_number": 2, "presigned_url": "https://s3.amazonaws.com/bucket/part_2"},
        {"part_number": 3, "presigned_url": "https://s3.amazonaws.com/bucket/part_3"},
    ]

    responses = gumroad.upload_file_to_presigned_parts(
        parts=parts,
        file_path_or_content=sample_bytes,
    )

    assert len(responses) == 3
    assert mock_requests_put.call_count == 3
    assert mock_requests_put.call_args_list[0][1]["data"] == b"0123"
    assert mock_requests_put.call_args_list[1][1]["data"] == b"4567"
    assert mock_requests_put.call_args_list[2][1]["data"] == b"89"


def test_upload_file_to_presigned_parts_with_explicit_sizes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_put_response = MagicMock(spec=requests.Response)
    mock_put_response.status_code = 200
    mock_requests_put = MagicMock(return_value=mock_put_response)
    monkeypatch.setattr(requests, "put", mock_requests_put)

    sample_bytes = b"abcdefghij"
    parts = [
        {"part_number": 1, "presigned_url": "https://s3.amazonaws.com/bucket/explicit_1", "size": 3},
        {"part_number": 2, "presigned_url": "https://s3.amazonaws.com/bucket/explicit_2", "size": 7},
    ]

    responses = gumroad.upload_file_to_presigned_parts(
        parts=parts,
        file_path_or_content=sample_bytes,
    )

    assert len(responses) == 2
    assert mock_requests_put.call_count == 2
    assert mock_requests_put.call_args_list[0][1]["data"] == b"abc"
    assert mock_requests_put.call_args_list[1][1]["data"] == b"defghij"


def test_upload_file_to_presigned_parts_raises_for_empty_parts() -> None:
    with pytest.raises(ValueError, match="No parts provided for upload"):
        gumroad.upload_file_to_presigned_parts(parts=[], file_path_or_content=b"content")


def test_request_presigned_file_upload_url_with_file_path_executes_parts_upload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    temp_file = tmp_path / "video_upload.mp4"
    temp_file.write_bytes(b"video frame content")

    mock_presign_response = MagicMock(spec=requests.Response)
    mock_presign_response.status_code = 200
    mock_presign_response.json.return_value = {
        "success": True,
        "parts": [
            {"part_number": 1, "presigned_url": "https://s3.amazonaws.com/bucket/video_part1"}
        ],
    }
    mock_post = MagicMock(return_value=mock_presign_response)
    monkeypatch.setattr(gumroad, "post", mock_post)

    mock_upload_parts = MagicMock(return_value=[MagicMock()])
    monkeypatch.setattr(gumroad, "upload_file_to_presigned_parts", mock_upload_parts)

    response = gumroad.request_presigned_file_upload_url(
        file_path_or_content=temp_file,
    )

    assert response == mock_presign_response
    mock_post.assert_called_once_with(
        "/v2/files/presign",
        content={"filename": "video_upload.mp4", "file_name": "video_upload.mp4", "file_size": len(b"video frame content")},
        params=None,
        timeout=30.0,
    )
    mock_upload_parts.assert_called_once_with(
        parts=[{"part_number": 1, "presigned_url": "https://s3.amazonaws.com/bucket/video_part1"}],
        file_path_or_content=temp_file,
        timeout=30.0,
    )


def test_extract_s3_upload_url_from_presign_response() -> None:
    direct_url_payload = {"success": True, "url": "https://s3.amazonaws.com/bucket/file1"}
    assert (
        gumroad.extract_s3_upload_url_from_presign_response(direct_url_payload)
        == ["https://s3.amazonaws.com/bucket/file1"]
    )

    nested_url_payload = {
        "success": True,
        "data": {"s3_url": "https://s3.amazonaws.com/bucket/file2"},
    }
    assert (
        gumroad.extract_s3_upload_url_from_presign_response(nested_url_payload)
        == ["https://s3.amazonaws.com/bucket/file2"]
    )

    mock_response = MagicMock(spec=requests.Response)
    mock_response.json.return_value = {
        "presigned_url": "https://s3.amazonaws.com/bucket/file3"
    }
    assert (
        gumroad.extract_s3_upload_url_from_presign_response(mock_response)
        == ["https://s3.amazonaws.com/bucket/file3"]
    )

    parts_payload = {
        "success": True,
        "parts": [{"part_number": 1, "presigned_url": "https://s3.amazonaws.com/bucket/file_parts"}],
    }
    assert (
        gumroad.extract_s3_upload_url_from_presign_response(parts_payload)
        == ["https://s3.amazonaws.com/bucket/file_parts"]
    )


def test_extract_s3_upload_url_from_presign_response_multipart_schema() -> None:
    presigned_payload = {
        "success": True,
        "upload_id": "ibZBv_75gd9o.uPYmGbJ5JjxqK4_VsP3...",
        "key": "attachments/A-m3CDDC5dlrSdKZp0RFhA==/9f2c1b7d6e4a/original/course.pdf",
        "file_url": "https://gumroad-specials.s3.amazonaws.com/attachments/A-m3CDDC5dlrSdKZp0RFhA==/9f2c1b7d6e4a/original/course.pdf",
        "parts": [
            {
                "part_number": 1,
                "presigned_url": "https://gumroad-specials.s3.amazonaws.com/...&partNumber=1&uploadId=...",
            },
            {
                "part_number": 2,
                "presigned_url": "https://gumroad-specials.s3.amazonaws.com/...&partNumber=2&uploadId=...",
            },
        ],
    }
    extracted_urls = gumroad.extract_s3_upload_url_from_presign_response(presigned_payload)
    assert extracted_urls == [
        "https://gumroad-specials.s3.amazonaws.com/...&partNumber=1&uploadId=...",
        "https://gumroad-specials.s3.amazonaws.com/...&partNumber=2&uploadId=...",
    ]


def test_extract_s3_upload_url_raises_value_error_when_missing() -> None:
    empty_payload = {"success": True}
    with pytest.raises(
        ValueError, match="Could not extract S3 upload URL from presign response"
    ):
        gumroad.extract_s3_upload_url_from_presign_response(empty_payload)


def test_upload_file_to_presigned_s3_url_uploads_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sample_file = tmp_path / "sample_manual.pdf"
    sample_file.write_bytes(b"binary pdf content")

    mock_s3_response = MagicMock(spec=requests.Response)
    mock_s3_response.status_code = 200
    mock_requests_put = MagicMock(return_value=mock_s3_response)
    monkeypatch.setattr(requests, "put", mock_requests_put)

    response = gumroad.upload_file_to_presigned_s3_url(
        "https://s3.amazonaws.com/bucket/target_location",
        sample_file,
        headers={"Content-Type": "application/pdf"},
        timeout=40.0,
    )

    assert response == mock_s3_response
    mock_requests_put.assert_called_once()
    called_s3_url = mock_requests_put.call_args[1]["url"]
    assert called_s3_url == "https://s3.amazonaws.com/bucket/target_location"
    assert mock_requests_put.call_args[1]["headers"] == {
        "Content-Type": "application/pdf"
    }
    assert mock_requests_put.call_args[1]["timeout"] == 40.0
    mock_s3_response.raise_for_status.assert_called_once()


def test_upload_file_to_presigned_s3_url_supports_bytes_and_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_payload_bytes = b"inline payload bytes"

    mock_s3_response = MagicMock(spec=requests.Response)
    mock_s3_response.status_code = 200
    mock_requests_put = MagicMock(return_value=mock_s3_response)
    monkeypatch.setattr(requests, "put", mock_requests_put)

    response = gumroad.upload_file_to_presigned_s3_url(
        "https://s3.amazonaws.com/bucket/target_bytes",
        raw_payload_bytes,
    )

    assert response == mock_s3_response
    mock_requests_put.assert_called_once_with(
        url="https://s3.amazonaws.com/bucket/target_bytes",
        data=raw_payload_bytes,
        headers=None,
        timeout=60.0,
    )


def test_upload_file_to_presigned_s3_url_raises_for_missing_file(tmp_path: Path) -> None:
    missing_target = tmp_path / "does_not_exist.bin"
    with pytest.raises(FileNotFoundError, match="File not found"):
        gumroad.upload_file_to_presigned_s3_url(
            "https://s3.amazonaws.com/bucket/missing", missing_target
        )


def test_attach_file_urls_to_product_sends_put_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_response = MagicMock(spec=requests.Response)
    mock_response.status_code = 200
    mock_put = MagicMock(return_value=mock_response)
    monkeypatch.setattr(gumroad, "put", mock_put)

    response = gumroad.attach_file_urls_to_product(
        "product_target_888",
        ["https://s3.amazonaws.com/bucket/file_one", "https://s3.amazonaws.com/bucket/file_two"],
        timeout=18.0,
    )

    assert response == mock_response
    mock_put.assert_called_once_with(
        "/v2/products/product_target_888",
        content={
            "files": [
                "https://s3.amazonaws.com/bucket/file_one",
                "https://s3.amazonaws.com/bucket/file_two",
            ]
        },
        timeout=18.0,
    )


def test_upload_product_files_via_presign_orchestrates_flow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_file = tmp_path / "document.txt"
    source_file.write_bytes(b"document payload")

    mock_presign_response = MagicMock(spec=requests.Response)
    mock_presign_response.status_code = 200
    mock_presign_response.json.return_value = {
        "success": True,
        "url": "https://s3.amazonaws.com/bucket/document_signed",
    }
    mock_request_presigned = MagicMock(return_value=mock_presign_response)
    monkeypatch.setattr(
        gumroad, "request_presigned_file_upload_url", mock_request_presigned
    )

    mock_upload_parts = MagicMock()
    monkeypatch.setattr(gumroad, "upload_file_to_presigned_parts", mock_upload_parts)

    mock_final_response = MagicMock(spec=requests.Response)
    mock_final_response.status_code = 200
    mock_attach_files = MagicMock(return_value=mock_final_response)
    monkeypatch.setattr(gumroad, "attach_file_urls_to_product", mock_attach_files)

    response = gumroad.upload_product_files_via_presign(
        "product_orchestrator_999",
        [source_file],
        timeout=45.0,
    )

    assert response == mock_final_response
    mock_request_presigned.assert_called_once_with(
        filename="document.txt",
        file_size=len(b"document payload"),
        timeout=45.0,
    )
    mock_upload_parts.assert_called_once_with(
        parts=[{"part_number": 1, "presigned_url": "https://s3.amazonaws.com/bucket/document_signed"}],
        file_path_or_content=source_file,
        timeout=45.0,
    )
    mock_attach_files.assert_called_once_with(
        product_id="product_orchestrator_999",
        file_urls=["https://s3.amazonaws.com/bucket/document_signed"],
        timeout=45.0,
    )


def test_upload_product_files_via_presign_multipart_orchestration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive_file = tmp_path / "archive.tar.gz"
    archive_file.write_bytes(b"tarball binary data")

    mock_presign_response = MagicMock(spec=requests.Response)
    mock_presign_response.status_code = 200
    mock_presign_response.json.return_value = {
        "success": True,
        "parts": [
            {"part_number": 1, "presigned_url": "https://s3.amazonaws.com/bucket/archive_part_1"},
            {"part_number": 2, "presigned_url": "https://s3.amazonaws.com/bucket/archive_part_2"},
        ],
    }
    mock_request_presigned = MagicMock(return_value=mock_presign_response)
    monkeypatch.setattr(
        gumroad, "request_presigned_file_upload_url", mock_request_presigned
    )

    mock_upload_parts = MagicMock()
    monkeypatch.setattr(gumroad, "upload_file_to_presigned_parts", mock_upload_parts)

    mock_final_response = MagicMock(spec=requests.Response)
    mock_final_response.status_code = 200
    mock_attach_files = MagicMock(return_value=mock_final_response)
    monkeypatch.setattr(gumroad, "attach_file_urls_to_product", mock_attach_files)

    response = gumroad.upload_product_files_via_presign(
        "product_multi_111",
        [archive_file],
        timeout=50.0,
    )

    assert response == mock_final_response
    mock_request_presigned.assert_called_once_with(
        filename="archive.tar.gz",
        file_size=len(b"tarball binary data"),
        timeout=50.0,
    )
    mock_upload_parts.assert_called_once_with(
        parts=[
            {"part_number": 1, "presigned_url": "https://s3.amazonaws.com/bucket/archive_part_1"},
            {"part_number": 2, "presigned_url": "https://s3.amazonaws.com/bucket/archive_part_2"},
        ],
        file_path_or_content=archive_file,
        timeout=50.0,
    )
    mock_attach_files.assert_called_once_with(
        product_id="product_multi_111",
        file_urls=["https://s3.amazonaws.com/bucket/archive_part_1"],
        timeout=50.0,
    )
