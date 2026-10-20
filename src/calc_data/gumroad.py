"""Gumroad API client.

Connects to https://api.gumroad.com using an access token provided via the
``GUMROAD_ACCESS_TOKEN`` environment variable.
"""

from __future__ import annotations

import functools
import json
import os
from typing import Any

from calc_data.products_dataclass import GumroadProduct

import requests
from dotenv import load_dotenv

from calc_data.utilities import _is_cache_valid, _write_debug, CACHE_DIR

GUMROAD_BASE_URL = "https://api.gumroad.com"
CACHE_VERSION = "v1"


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
