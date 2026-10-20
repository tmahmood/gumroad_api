"""Gumroad API client.

Connects to https://api.gumroad.com using an access token provided via the
``GUMROAD_ACCESS_TOKEN`` environment variable.
"""

from __future__ import annotations

import functools
import json
import os
from pathlib import Path
from typing import Any, BinaryIO, Sequence

from calc_data.products_dataclass import GumroadProduct

import requests
from dotenv import load_dotenv

from calc_data.utilities import _is_cache_valid, _write_debug, CACHE_DIR

GUMROAD_BASE_URL = "https://api.gumroad.com"
CACHE_VERSION = "v1"
DUMMY_PRODUCT = "ZiQxH2j2thl6z0P3qti1HQ=="
MAX_PRESIGNED_FILE_SIZE_BYTES = 20 * 1024 * 1024 * 1024  # 20 GB in bytes
PRESIGNED_UPLOAD_PART_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB in bytes


def _get_access_token() -> str:
    """Return the Gumroad access token from the environment."""
    access_token = os.environ.get("GUMROAD_ACCESS_TOKEN")
    if not access_token:
        raise RuntimeError(
            "GUMROAD_ACCESS_TOKEN environment variable is not set"
        )
    return access_token


def gumroad_request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    content: dict[str, Any] | None = None,
    files: Any | None = None,
    data: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
    **request_keyword_arguments: Any,
) -> requests.Response:
    """Make an authenticated request to the Gumroad API.

    Args:
        method: HTTP method (e.g. ``"GET"``, ``"POST"``, ``"PUT"``).
        path: API path, e.g. ``"/v2/products"``. Leading slash is optional.
        params: Query parameters to send with the request.
        content: JSON body to send with the request.
        files: Files dictionary or multipart form data to send with the request.
        data: Form data to send with the request.
        headers: Additional HTTP headers to send with the request.
        timeout: Request timeout in seconds.
        **request_keyword_arguments: Additional keyword arguments passed to requests.request.

    Returns:
        The ``requests.Response`` object.

    Raises:
        RuntimeError: If ``GUMROAD_ACCESS_TOKEN`` is not set or API response indicates failure.
        requests.HTTPError: If the API returns a non-2xx status.
    """
    access_token = _get_access_token()
    request_url = path if path.startswith("http") else GUMROAD_BASE_URL + path

    request_headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    if headers:
        request_headers.update(headers)

    response = requests.request(
        method=method,
        url=request_url,
        headers=request_headers,
        params=params,
        json=content,
        data=data,
        files=files,
        timeout=timeout,
        **request_keyword_arguments,
    )
    response.raise_for_status()

    try:
        response_payload = response.json()
    except (ValueError, json.JSONDecodeError):
        response_payload = None

    if isinstance(response_payload, dict) and response_payload.get("success") is False:
        error_message = (
            response_payload.get("message")
            or response_payload.get("error")
            or "Request returned success=false"
        )
        raise RuntimeError(f"Gumroad API request failed: {error_message}")

    print(response.text)
    return response


def _store_response(decorated_function):
    """Decorator that stores the API response in a versioned JSON file."""
    @functools.wraps(decorated_function)
    def wrapper(endpoint_path: str, **request_keyword_arguments: Any) -> requests.Response:
        sanitized_endpoint_path = endpoint_path.lstrip("/").replace("/", "_")
        version_suffix = (
            str(CACHE_VERSION)
            if str(CACHE_VERSION).startswith("v")
            else f"v{CACHE_VERSION}"
        )
        cache_file_path = CACHE_DIR / f"gumroad_{sanitized_endpoint_path}_{version_suffix}.json"

        if _is_cache_valid(cache_file_path):
            try:
                cached_payload = json.loads(cache_file_path.read_text())
                cached_response_payload = cached_payload.get("response")
                if cached_response_payload is not None:
                    cached_response = requests.Response()
                    cached_response.status_code = 200
                    cached_response._content = json.dumps(cached_response_payload).encode("utf-8")
                    return cached_response
            except (OSError, json.JSONDecodeError, AttributeError):
                pass

        response = decorated_function(endpoint_path, **request_keyword_arguments)
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_payload = {
                "version": str(CACHE_VERSION),
                "cache_version": str(CACHE_VERSION),
                "response": response.json(),
            }
            cache_file_path.write_text(json.dumps(cache_payload, indent=2))
        except (OSError, json.JSONDecodeError):
            pass
        return response
    return wrapper


@_store_response
def get(path: str, **request_keyword_arguments: Any) -> requests.Response:
    """Convenience wrapper for GET requests."""
    return gumroad_request("GET", path, **request_keyword_arguments)


def post(path: str, *, content: dict[str, Any] | None = None, **request_keyword_arguments: Any) -> requests.Response:
    """Convenience wrapper for POST requests."""
    return gumroad_request("POST", path, content=content, **request_keyword_arguments)


def put(
    path: str,
    *,
    content: dict[str, Any] | None = None,
    files: Any | None = None,
    data: dict[str, Any] | None = None,
    **request_keyword_arguments: Any,
) -> requests.Response:
    """Convenience wrapper for PUT requests."""
    return gumroad_request(
        "PUT",
        path,
        content=content,
        files=files,
        data=data,
        **request_keyword_arguments,
    )


def prepare_files_for_put(
    file_paths: Sequence[str | Path | BinaryIO | tuple[str, Any]],
) -> list[tuple[str, Any]]:
    """Prepare a sequence of file paths or file streams into multipart tuples for PUT.

    Args:
        file_paths: Sequence of file paths or open binary file objects.

    Returns:
        List of multipart tuples formatted for requests.

    Raises:
        FileNotFoundError: If a specified file path does not exist.
    """
    prepared_files_list: list[tuple[str, Any]] = []
    for file_entry in file_paths:
        if isinstance(file_entry, (str, Path)):
            file_path_object = Path(file_entry)
            if not file_path_object.is_file():
                raise FileNotFoundError(f"File not found: {file_path_object}")
            opened_file_handle = open(file_path_object, "rb")
            prepared_files_list.append(
                ("file", (file_path_object.name, opened_file_handle))
            )
        elif isinstance(file_entry, tuple):
            prepared_files_list.append(file_entry)
        else:
            file_stream_name = getattr(file_entry, "name", "file")
            prepared_files_list.append(
                ("file", (Path(file_stream_name).name, file_entry))
            )
    return prepared_files_list


def upload_product_file_list(
    product_id: str,
    file_paths: Sequence[str | Path | BinaryIO | tuple[str, Any]],
    *,
    timeout: float = 30.0,
    **request_keyword_arguments: Any,
) -> requests.Response:
    """Prepare a list of files and send only that to the Gumroad PUT API using put.

    Args:
        product_id: The unique identifier of the Gumroad product.
        file_paths: Sequence of file paths or file streams to prepare and upload.
        timeout: Request timeout in seconds.
        **request_keyword_arguments: Additional keyword arguments passed to put.

    Returns:
        The ``requests.Response`` object.
    """
    prepared_files_list = prepare_files_for_put(file_paths)
    print(prepared_files_list)
    return put(
        f"/v2/products/{product_id}",
        files=prepared_files_list,
        timeout=timeout,
        **request_keyword_arguments,
    )


def request_presigned_file_upload_url(
    file_name: str | None = None,
    filename: str | None = None,
    file_size: int | None = None,
    *,
    file_path_or_content: str | Path | BinaryIO | bytes | None = None,
    content: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    timeout: float = 30.0,
    **request_keyword_arguments: Any,
) -> requests.Response:
    """Request a presigned S3 upload URL from the Gumroad API.

    Args:
        file_name: Optional name of the file to be uploaded.
        filename: Optional name of the file to be uploaded (Gumroad API parameter).
        file_size: Optional size of the file in bytes (must not exceed 20GB).
        file_path_or_content: Optional path or content of the file to upload after presigning.
        content: Optional JSON payload to send with the presign request.
        params: Optional query parameters for the request.
        timeout: Request timeout in seconds.
        **request_keyword_arguments: Additional keyword arguments passed to post.

    Returns:
        The ``requests.Response`` object containing presigned URL information.

    Raises:
        ValueError: If the file size exceeds the 20GB limit.
    """
    resolved_file_name = filename or file_name
    resolved_file_size = file_size

    if file_path_or_content is not None:
        if isinstance(file_path_or_content, (str, Path)):
            target_path_object = Path(file_path_or_content)
            if target_path_object.is_file():
                if not resolved_file_name:
                    resolved_file_name = target_path_object.name
                if resolved_file_size is None:
                    resolved_file_size = target_path_object.stat().st_size
        elif isinstance(file_path_or_content, bytes):
            if resolved_file_size is None:
                resolved_file_size = len(file_path_or_content)
            if not resolved_file_name:
                resolved_file_name = "file.bin"
        elif hasattr(file_path_or_content, "read"):
            if not resolved_file_name and hasattr(file_path_or_content, "name"):
                resolved_file_name = Path(str(getattr(file_path_or_content, "name"))).name
            if resolved_file_size is None and hasattr(file_path_or_content, "seek") and hasattr(file_path_or_content, "tell"):
                current_stream_position = file_path_or_content.tell()
                file_path_or_content.seek(0, os.SEEK_END)
                resolved_file_size = file_path_or_content.tell() - current_stream_position
                file_path_or_content.seek(current_stream_position)

    request_payload = dict(content) if content else {}

    if resolved_file_name is not None and "filename" not in request_payload and "file_name" not in request_payload and "name" not in request_payload:
        request_payload["filename"] = resolved_file_name
        request_payload["file_name"] = resolved_file_name

    if resolved_file_size is None:
        resolved_file_size = request_payload.get("file_size", request_payload.get("filesize"))

    if resolved_file_size is not None:
        if resolved_file_size > MAX_PRESIGNED_FILE_SIZE_BYTES:
            raise ValueError(
                f"File size exceeds maximum allowed size of 20GB ({MAX_PRESIGNED_FILE_SIZE_BYTES} bytes): {resolved_file_size} bytes"
            )
        request_payload["file_size"] = resolved_file_size

    presigned_response = post(
        "/v2/files/presign",
        content=request_payload if request_payload else None,
        params=params,
        timeout=timeout,
        **request_keyword_arguments,
    )

    if file_path_or_content is not None:
        presigned_parts_list = extract_presigned_parts_from_presign_response(presigned_response)
        upload_file_to_presigned_parts(
            parts=presigned_parts_list,
            file_path_or_content=file_path_or_content,
            timeout=timeout,
        )

    return presigned_response


def extract_s3_upload_url_from_presign_response(
    presigned_response_payload: dict[str, Any] | requests.Response,
) -> list[str]:
    """Extract the S3 upload URLs from a presign API response or dictionary.

    Args:
        presigned_response_payload: Response object or dictionary from presign request.

    Returns:
        List of S3 presigned URL strings for uploading the file parts.

    Raises:
        ValueError: If no valid S3 upload URL is found in the response.
    """
    if isinstance(presigned_response_payload, requests.Response):
        presigned_data_dictionary = presigned_response_payload.json()
    else:
        presigned_data_dictionary = presigned_response_payload

    if isinstance(presigned_data_dictionary, dict):
        raw_parts_data = presigned_data_dictionary.get("parts")
        if raw_parts_data is None and isinstance(presigned_data_dictionary.get("data"), dict):
            raw_parts_data = presigned_data_dictionary["data"].get("parts")

        if isinstance(raw_parts_data, list) and len(raw_parts_data) > 0:
            extracted_presigned_urls_list: list[str] = []
            for part_item in raw_parts_data:
                if isinstance(part_item, str) and part_item:
                    extracted_presigned_urls_list.append(part_item)
                elif isinstance(part_item, dict):
                    part_upload_url = (
                        part_item.get("presigned_url")
                        or part_item.get("url")
                        or part_item.get("s3_url")
                        or part_item.get("upload_url")
                    )
                    if part_upload_url:
                        extracted_presigned_urls_list.append(str(part_upload_url))
            if extracted_presigned_urls_list:
                return extracted_presigned_urls_list

        for possible_key in ("url", "presigned_url", "s3_url", "upload_url"):
            if possible_key in presigned_data_dictionary and presigned_data_dictionary[possible_key]:
                return [str(presigned_data_dictionary[possible_key])]

        if "data" in presigned_data_dictionary and isinstance(presigned_data_dictionary["data"], dict):
            nested_data_dictionary = presigned_data_dictionary["data"]
            for possible_key in ("url", "presigned_url", "s3_url", "upload_url"):
                if possible_key in nested_data_dictionary and nested_data_dictionary[possible_key]:
                    return [str(nested_data_dictionary[possible_key])]

    raise ValueError("Could not extract S3 upload URL from presign response")


def extract_presigned_parts_from_presign_response(
    presigned_response_payload: dict[str, Any] | requests.Response,
) -> list[dict[str, Any]]:
    """Extract the list of presigned upload part dictionaries from a presign API response.

    Args:
        presigned_response_payload: Response object or dictionary from presign request.

    Returns:
        List of part dictionaries containing at least ``"presigned_url"`` and ``"part_number"``.

    Raises:
        ValueError: If no valid presigned upload parts or URLs are found in the response.
    """
    if isinstance(presigned_response_payload, requests.Response):
        presigned_data_dictionary = presigned_response_payload.json()
    else:
        presigned_data_dictionary = presigned_response_payload

    extracted_parts_list: list[dict[str, Any]] = []

    if isinstance(presigned_data_dictionary, dict):
        raw_parts_data = presigned_data_dictionary.get("parts")
        if raw_parts_data is None and isinstance(presigned_data_dictionary.get("data"), dict):
            raw_parts_data = presigned_data_dictionary["data"].get("parts")

        if isinstance(raw_parts_data, list) and len(raw_parts_data) > 0:
            for part_index, part_item in enumerate(raw_parts_data):
                if isinstance(part_item, str):
                    extracted_parts_list.append(
                        {"part_number": part_index + 1, "presigned_url": part_item}
                    )
                elif isinstance(part_item, dict):
                    part_url = (
                        part_item.get("presigned_url")
                        or part_item.get("url")
                        or part_item.get("s3_url")
                        or part_item.get("upload_url")
                    )
                    if part_url:
                        part_dict: dict[str, Any] = {
                            "part_number": part_item.get("part_number", part_index + 1),
                            "presigned_url": str(part_url),
                        }
                        if "size" in part_item:
                            part_dict["size"] = part_item["size"]
                        extracted_parts_list.append(part_dict)

    if extracted_parts_list:
        return extracted_parts_list

    try:
        single_upload_urls_list = extract_s3_upload_url_from_presign_response(presigned_data_dictionary)
        return [
            {"part_number": part_index + 1, "presigned_url": single_part_url}
            for part_index, single_part_url in enumerate(single_upload_urls_list)
        ]
    except ValueError:
        pass

    raise ValueError("Could not extract presigned upload parts from presign response")


def upload_file_to_presigned_s3_url(
    s3_upload_url: str,
    file_path_or_content: str | Path | BinaryIO | bytes,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 60.0,
    **request_keyword_arguments: Any,
) -> requests.Response:
    """Upload binary file content to a presigned S3 URL via HTTP PUT.

    Args:
        s3_upload_url: The presigned S3 URL for uploading the file.
        file_path_or_content: File path, open file stream, or raw bytes to upload.
        headers: Optional HTTP headers to include with the S3 request.
        timeout: Request timeout in seconds.
        **request_keyword_arguments: Additional keyword arguments passed to requests.put.

    Returns:
        The ``requests.Response`` object from S3.

    Raises:
        FileNotFoundError: If a given file path does not exist.
        requests.HTTPError: If S3 returns a non-2xx status code.
    """
    if isinstance(file_path_or_content, (str, Path)):
        target_file_path = Path(file_path_or_content)
        if not target_file_path.is_file():
            raise FileNotFoundError(f"File not found: {target_file_path}")
        with open(target_file_path, "rb") as binary_file_handle:
            upload_response = requests.put(
                url=s3_upload_url,
                data=binary_file_handle,
                headers=headers,
                timeout=timeout,
                **request_keyword_arguments,
            )
    else:
        upload_response = requests.put(
            url=s3_upload_url,
            data=file_path_or_content,
            headers=headers,
            timeout=timeout,
            **request_keyword_arguments,
        )
    upload_response.raise_for_status()
    return upload_response


def upload_file_to_presigned_parts(
    parts: Sequence[dict[str, Any] | str],
    file_path_or_content: str | Path | BinaryIO | bytes,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 60.0,
    **request_keyword_arguments: Any,
) -> list[requests.Response]:
    """Upload file content to one or multiple presigned part URLs.

    If a single part is provided, the entire file is uploaded.
    If multiple parts are provided, the file is partitioned across the parts and uploaded.

    Args:
        parts: Sequence of part dictionaries with ``"presigned_url"`` or URL strings.
        file_path_or_content: File path, open file stream, or raw bytes to upload.
        headers: Optional HTTP headers to include with each upload request.
        timeout: Request timeout in seconds.
        **request_keyword_arguments: Additional keyword arguments passed to requests.put.

    Returns:
        List of ``requests.Response`` objects for each uploaded part.

    Raises:
        FileNotFoundError: If a given file path does not exist.
        ValueError: If no parts are provided or a part is missing a URL.
        requests.HTTPError: If an upload request returns a non-2xx status code.
    """
    if isinstance(file_path_or_content, (str, Path)):
        target_file_path = Path(file_path_or_content)
        if not target_file_path.is_file():
            raise FileNotFoundError(f"File not found: {target_file_path}")
        total_file_bytes = target_file_path.read_bytes()
    elif isinstance(file_path_or_content, bytes):
        total_file_bytes = file_path_or_content
    elif hasattr(file_path_or_content, "read"):
        total_file_bytes = file_path_or_content.read()
    else:
        raise TypeError(f"Unsupported file content type: {type(file_path_or_content)}")

    normalized_parts_list: list[dict[str, Any]] = []
    for part_index, part_entry in enumerate(parts):
        if isinstance(part_entry, str):
            normalized_parts_list.append(
                {"part_number": part_index + 1, "presigned_url": part_entry}
            )
        elif isinstance(part_entry, dict):
            part_url = (
                part_entry.get("presigned_url")
                or part_entry.get("url")
                or part_entry.get("s3_url")
                or part_entry.get("upload_url")
            )
            if not part_url:
                raise ValueError(f"Part at index {part_index} missing presigned_url")
            normalized_part: dict[str, Any] = {
                "part_number": part_entry.get("part_number", part_index + 1),
                "presigned_url": str(part_url),
            }
            if "size" in part_entry:
                normalized_part["size"] = part_entry["size"]
            normalized_parts_list.append(normalized_part)
        else:
            raise TypeError(f"Invalid part item type: {type(part_entry)}")

    total_parts_count = len(normalized_parts_list)
    if total_parts_count == 0:
        raise ValueError("No parts provided for upload")

    if total_parts_count == 1:
        single_upload_response = upload_file_to_presigned_s3_url(
            s3_upload_url=normalized_parts_list[0]["presigned_url"],
            file_path_or_content=total_file_bytes,
            headers=headers,
            timeout=timeout,
            **request_keyword_arguments,
        )
        return [single_upload_response]

    total_file_size = len(total_file_bytes)
    upload_responses_list: list[requests.Response] = []

    has_explicit_sizes = all(
        isinstance(part_entry.get("size"), int) and part_entry["size"] > 0
        for part_entry in normalized_parts_list
    )

    if has_explicit_sizes:
        current_byte_offset = 0
        for part_entry in normalized_parts_list:
            part_size = part_entry["size"]
            chunk_bytes = total_file_bytes[current_byte_offset : current_byte_offset + part_size]
            current_byte_offset += part_size
            part_upload_response = upload_file_to_presigned_s3_url(
                s3_upload_url=part_entry["presigned_url"],
                file_path_or_content=chunk_bytes,
                headers=headers,
                timeout=timeout,
                **request_keyword_arguments,
            )
            upload_responses_list.append(part_upload_response)
    else:
        part_chunk_size = (
            (total_file_size + total_parts_count - 1) // total_parts_count
            if total_parts_count > 0
            else total_file_size
        )
        for part_index, part_entry in enumerate(normalized_parts_list):
            start_offset = part_index * part_chunk_size
            if part_index == total_parts_count - 1:
                end_offset = total_file_size
            else:
                end_offset = min(start_offset + part_chunk_size, total_file_size)
            chunk_bytes = total_file_bytes[start_offset:end_offset]
            part_upload_response = upload_file_to_presigned_s3_url(
                s3_upload_url=part_entry["presigned_url"],
                file_path_or_content=chunk_bytes,
                headers=headers,
                timeout=timeout,
                **request_keyword_arguments,
            )
            upload_responses_list.append(part_upload_response)

    return upload_responses_list


def attach_file_urls_to_product(
    product_id: str,
    file_urls: Sequence[str] | str,
    *,
    timeout: float = 30.0,
    **request_keyword_arguments: Any,
) -> requests.Response:
    """Send PUT request to associate uploaded file URLs with a Gumroad product.

    Args:
        product_id: The unique identifier of the Gumroad product.
        file_urls: Sequence of uploaded file URLs or a single file URL string.
        timeout: Request timeout in seconds.
        **request_keyword_arguments: Additional keyword arguments passed to put.

    Returns:
        The ``requests.Response`` object from Gumroad API.
    """
    normalized_file_urls_list = (
        [file_urls] if isinstance(file_urls, str) else list(file_urls)
    )
    return put(
        f"/v2/products/{product_id}",
        content={"files": normalized_file_urls_list},
        timeout=timeout,
        **request_keyword_arguments,
    )


def upload_product_files_via_presign(
    product_id: str,
    file_paths: Sequence[str | Path | BinaryIO | bytes],
    *,
    timeout: float = 60.0,
    **request_keyword_arguments: Any,
) -> requests.Response:
    """Upload files to Gumroad using the presign, S3 multipart/single upload, and product PUT flow.

    Args:
        product_id: The unique identifier of the Gumroad product.
        file_paths: Sequence of file paths, file streams, or bytes to upload.
        timeout: Request timeout in seconds for each operation.
        **request_keyword_arguments: Additional keyword arguments passed to the final product PUT request.

    Returns:
        The ``requests.Response`` object from the final product update.
    """
    uploaded_file_urls_list: list[str] = []
    for file_entry in file_paths:
        file_name_string, file_size_integer = find_filename_and_size(file_entry)

        presigned_response = request_presigned_file_upload_url(
            filename=file_name_string,
            file_size=file_size_integer,
            timeout=timeout,
        )
        presigned_parts_list = extract_presigned_parts_from_presign_response(presigned_response)
        upload_file_to_presigned_parts(
            parts=presigned_parts_list,
            file_path_or_content=file_entry,
            timeout=timeout,
        )
        try:
            s3_upload_urls_list = extract_s3_upload_url_from_presign_response(presigned_response)
            s3_upload_url = s3_upload_urls_list[0]
        except (ValueError, IndexError):
            s3_upload_url = presigned_parts_list[0]["presigned_url"]
        uploaded_file_urls_list.append(s3_upload_url)

    return attach_file_urls_to_product(
        product_id=product_id,
        file_urls=uploaded_file_urls_list,
        timeout=timeout,
        **request_keyword_arguments,
    )


def find_filename_and_size(file_entry: str | Path | BinaryIO | bytes) -> tuple[str | None, int | None]:
    file_name_string: str | None = None
    file_size_integer: int | None = None
    if isinstance(file_entry, (str, Path)):
        target_path_object = Path(file_entry)
        if not target_path_object.is_file():
            raise FileNotFoundError(f"File not found: {target_path_object}")
        file_name_string = target_path_object.name
        file_size_integer = target_path_object.stat().st_size
    elif isinstance(file_entry, bytes):
        file_name_string = "file.bin"
        file_size_integer = len(file_entry)
    elif hasattr(file_entry, "name"):
        file_name_string = Path(str(getattr(file_entry, "name"))).name
        if hasattr(file_entry, "seek") and hasattr(file_entry, "tell"):
            current_stream_position = file_entry.tell()
            file_entry.seek(0, os.SEEK_END)
            file_size_integer = file_entry.tell() - current_stream_position
            file_entry.seek(current_stream_position)
    return file_name_string, file_size_integer


def _normalize_products(payload: Any) -> list[GumroadProduct]:
    """Extract a list of GumroadProduct dicts from a Gumroad API response."""
    if isinstance(payload, dict):
        for response_key in ("products", "data", "results"):
            products_list = payload.get(response_key)
            if isinstance(products_list, list):
                return [GumroadProduct(**product_data) for product_data in products_list]
        return []
    if isinstance(payload, list):
        return [GumroadProduct(**product_data) for product_data in payload]
    return []


def list_products() -> tuple[list[GumroadProduct], dict[str, Any]]:
    """List all products owned by the authenticated user (raw API data)."""
    response = get("/v2/products")
    try:
        raw_response_data = response.json()
    except json.JSONDecodeError:
        # Store failed raw JSON to debug file
        try:
            _write_debug(response.text)
        except OSError:
            pass
        return [], {}
    products = _normalize_products(raw_response_data)
    return products, raw_response_data


def main() -> None:
    """Demo: list products (name + id) using the env-provided access token."""
    load_dotenv()
    try:
        products, raw_response_data = list_products()
        print(f"Fetched {len(products)} product(s) from Gumroad")
        for product in products:
            print(f"- {product.name} ({product.id})")
    except RuntimeError as configuration_error:
        print(f"Configuration error: {configuration_error}")
    except requests.HTTPError as http_error:
        print(f"Gumroad API error: {http_error.response.status_code} {http_error.response.text}")


if __name__ == "__main__":
    main()
