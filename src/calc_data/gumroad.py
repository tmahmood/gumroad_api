"""Gumroad API client.

Connects to https://api.gumroad.com using an access token provided via the
``GUMROAD_ACCESS_TOKEN`` environment variable.
"""

from __future__ import annotations

import functools
import json
import os
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

from calc_data.products_dataclass import GumroadProduct
from calc_data.s3_upload import upload_presigned_file
from calc_data.upload_dataclass import (
    PresignedFileUpload,
    PresignedUploadPart,
    UploadedFilePart,
)
from calc_data.utilities import (
    CACHE_DIR,
    FileSummary,
    _is_cache_valid,
    _write_debug,
    collect_file_sizes,
)

GUMROAD_BASE_URL = "https://api.gumroad.com"
PRESIGN_ENDPOINT_PATH = "/v2/files/presign"
COMPLETE_ENDPOINT_PATH = "/v2/files/complete"
CACHE_VERSION = "v1"
DUMMY_PRODUCT = "ZiQxH2j2thl6z0P3qti1HQ=="


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
    timeout: float = 30.0,
) -> requests.Response:
    """Make an authenticated request to the Gumroad API.

    Args:
        method: HTTP method (e.g. ``"GET"``, ``"POST"``).
        path: API path, e.g. ``"/v2/products"``. Leading slash is optional.
        content: JSON body to send with the request.
        params: Query parameters to send with the request.
        timeout: Request timeout in seconds.

    Returns:
        The ``requests.Response`` object.

    Raises:
        RuntimeError: If ``GUMROAD_ACCESS_TOKEN`` is not set.
        requests.HTTPError: If the API returns a non-2xx status.
    """
    access_token = _get_access_token()
    request_url = path if path.startswith("http") else GUMROAD_BASE_URL + path

    request_headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }

    response = requests.request(
        method=method,
        url=request_url,
        headers=request_headers,
        params=params,
        json=content,
        timeout=timeout,
    )
    response.raise_for_status()
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


def put(path: str, *, content: dict[str, Any] | None = None, **request_keyword_arguments: Any) -> requests.Response:
    """Convenience wrapper for PUT requests."""
    return gumroad_request("PUT", path, content=content, **request_keyword_arguments)


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


def get_product(product_id: str) -> tuple[GumroadProduct | None, dict[str, Any]]:
    """Retrieve a single product by ID from the Gumroad API.

    Args:
        product_id: The Gumroad product ID, e.g. ``"phRR3J4IO3lBh25O2IV_dQ=="``.

    Returns:
        A tuple of the parsed ``GumroadProduct`` (or ``None`` when the response
        does not contain a product) and the raw API response data.

    Raises:
        ValueError: If ``product_id`` is empty.
        RuntimeError: If ``GUMROAD_ACCESS_TOKEN`` is not set.
        requests.HTTPError: If the API returns a non-2xx status.
    """
    cleaned_product_id = product_id.strip()
    if not cleaned_product_id:
        raise ValueError("product_id must not be empty")

    response = get(f"/v2/products/{cleaned_product_id}")
    try:
        raw_response_data = response.json()
    except json.JSONDecodeError:
        try:
            _write_debug(response.text)
        except OSError:
            pass
        return None, {}

    product_payload = (
        raw_response_data.get("product")
        if isinstance(raw_response_data, dict)
        else None
    )
    if not isinstance(product_payload, dict):
        return None, raw_response_data

    return GumroadProduct(**product_payload), raw_response_data


def _extract_error_message(response_payload: dict[str, Any]) -> str:
    """Return the error message from a failed Gumroad API response."""
    return str(
        response_payload.get("message")
        or response_payload.get("error")
        or "unknown error"
    )


def presign_file(file_summary: FileSummary) -> PresignedFileUpload:
    """Request presigned multipart upload URLs for a single file.

    Args:
        file_summary: Dict containing the local ``filename`` and its
            ``file_size`` in bytes, as returned by ``collect_file_sizes``.

    Returns:
        The presigned upload details, including the multipart parts.

    Raises:
        RuntimeError: If Gumroad reports that presigning failed.
        requests.HTTPError: If the API returns a non-2xx status.
    """
    source_path = Path(file_summary["filename"])
    response = post(
        PRESIGN_ENDPOINT_PATH,
        content={
            "filename": source_path.name,
            "file_size": file_summary["file_size"],
        },
    )
    response_payload = response.json()
    if not response_payload.get("success"):
        raise RuntimeError(
            f"Failed to presign {source_path}: "
            f"{_extract_error_message(response_payload)}"
        )

    return PresignedFileUpload(
        source_path=str(source_path),
        filename=source_path.name,
        file_size=file_summary["file_size"],
        upload_id=response_payload["upload_id"],
        key=response_payload["key"],
        file_url=response_payload["file_url"],
        parts=[
            PresignedUploadPart(
                part_number=part_payload["part_number"],
                presigned_url=part_payload["presigned_url"],
            )
            for part_payload in response_payload.get("parts", [])
        ],
    )


def presign_files(file_summaries: list[FileSummary]) -> list[PresignedFileUpload]:
    """Request presigned multipart upload URLs for a list of files.

    Args:
        file_summaries: File summaries as returned by ``collect_file_sizes``.

    Returns:
        One presigned upload per input file, in the same order.

    Raises:
        RuntimeError: If Gumroad reports that presigning failed for any file.
        requests.HTTPError: If the API returns a non-2xx status.
    """
    return [presign_file(file_summary) for file_summary in file_summaries]


def complete_file_upload(
    presigned_upload: PresignedFileUpload,
    uploaded_parts: list[UploadedFilePart],
) -> dict[str, Any]:
    """Complete a presigned multipart upload on Gumroad.

    Args:
        presigned_upload: Presigned upload details from ``presign_file``.
        uploaded_parts: Uploaded parts with their S3 ``ETag`` headers, as
            returned by ``upload_presigned_file``.

    Returns:
        The raw Gumroad response payload, including the canonical file URL.

    Raises:
        RuntimeError: If Gumroad does not report ``success: true``.
        requests.HTTPError: If the API returns a non-2xx status.
    """
    response = post(
        COMPLETE_ENDPOINT_PATH,
        content={
            "upload_id": presigned_upload.upload_id,
            "key": presigned_upload.key,
            "parts": [
                {
                    "part_number": uploaded_part.part_number,
                    "etag": uploaded_part.etag,
                }
                for uploaded_part in sorted(
                    uploaded_parts, key=lambda part: part.part_number
                )
            ],
        },
    )
    response_payload = response.json()
    if not response_payload.get("success"):
        raise RuntimeError(
            f"Failed to complete upload for {presigned_upload.source_path}: "
            f"{_extract_error_message(response_payload)}"
        )
    return response_payload


def complete_file_uploads(
    presigned_uploads: list[PresignedFileUpload],
    uploaded_parts_by_file: list[list[UploadedFilePart]],
) -> list[dict[str, Any]]:
    """Complete a list of presigned multipart uploads on Gumroad.

    Args:
        presigned_uploads: Presigned uploads from ``presign_files``.
        uploaded_parts_by_file: Uploaded parts per file, in the same order,
            as returned by ``upload_presigned_files``.

    Returns:
        The raw Gumroad response payload for each completed upload, in the
        same order.

    Raises:
        ValueError: If the number of uploads and part lists differs.
        RuntimeError: If Gumroad does not report ``success: true``.
        requests.HTTPError: If the API returns a non-2xx status.
    """
    if len(presigned_uploads) != len(uploaded_parts_by_file):
        raise ValueError(
            f"Received {len(presigned_uploads)} presigned uploads but "
            f"{len(uploaded_parts_by_file)} part lists"
        )

    return [
        complete_file_upload(presigned_upload, uploaded_parts)
        for presigned_upload, uploaded_parts in zip(
            presigned_uploads, uploaded_parts_by_file
        )
    ]


def attach_file_url_to_product(product_id: str, file_url: str) -> dict[str, Any]:
    """Attach an uploaded file URL to a Gumroad product.

    Note:
        Gumroad treats ``files`` on ``PUT /v2/products/:id`` as a full
        replacement, so files that are not resubmitted are deleted.

    Args:
        product_id: The Gumroad product ID to update.
        file_url: Canonical file URL returned by ``complete_file_upload``.

    Returns:
        The raw Gumroad response payload.

    Raises:
        RuntimeError: If Gumroad does not report ``success: true``.
        requests.HTTPError: If the API returns a non-2xx status.
    """
    response = put(
        f"/v2/products/{product_id}",
        content={"files": [{"url": file_url}]},
    )
    response_payload = response.json()
    if not response_payload.get("success"):
        raise RuntimeError(
            f"Failed to attach {file_url} to product {product_id}: "
            f"{_extract_error_message(response_payload)}"
        )
    return response_payload


def upload_readme_to_dummy_product() -> dict[str, Any]:
    """Upload the project README.md to Gumroad and attach it to DUMMY_PRODUCT.

    Returns:
        The raw Gumroad response payload from the product update.

    Raises:
        RuntimeError: If Gumroad rejects any step of the upload.
        requests.HTTPError: If the API returns a non-2xx status.
        OSError: If README.md cannot be read.
    """
    readme_path = Path(__file__).resolve().parents[2] / "README.md"
    file_summaries = collect_file_sizes([readme_path])
    presigned_upload = presign_files(file_summaries)[0]
    uploaded_parts = upload_presigned_file(presigned_upload)
    completion_payload = complete_file_upload(presigned_upload, uploaded_parts)
    return attach_file_url_to_product(
        DUMMY_PRODUCT, completion_payload["file_url"]
    )


def main() -> None:
    """Demo: list products (name + id) using the env-provided access token."""
    load_dotenv()
    upload_readme_to_dummy_product()
    try:
        products, _raw_response_data = list_products()
        print(f"Fetched {len(products)} product(s) from Gumroad")
        for product in products:
            print(f"- {product.name} ({product.id})")
    except RuntimeError as configuration_error:
        print(f"Configuration error: {configuration_error}")
    except requests.HTTPError as http_error:
        print(f"Gumroad API error: {http_error.response.status_code} {http_error.response.text}")


if __name__ == "__main__":
    main()
