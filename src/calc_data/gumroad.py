"""Gumroad API client.

Connects to https://api.gumroad.com using an access token provided via the
``GUMROAD_ACCESS_TOKEN`` environment variable.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import requests

GUMROAD_BASE_URL = "https://api.gumroad.com"

CACHE_DIR = Path("cache")
CACHE_TTL = 3600  # 1 hour in seconds


def _get_access_token() -> str:
    """Return the Gumroad access token from the environment."""
    token = os.environ.get("GUMROAD_ACCESS_TOKEN")
    if not token:
        raise RuntimeError(
            "GUMROAD_ACCESS_TOKEN environment variable is not set"
        )
    return token


def gumroad_request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> requests.Response:
    """Make an authenticated request to the Gumroad API.

    Args:
        method: HTTP method (e.g. ``"GET"``, ``"POST"``).
        path: API path, e.g. ``"/v2/products"``. Leading slash is optional.
        json: JSON body to send with the request.
        timeout: Request timeout in seconds.

    Returns:
        The ``requests.Response`` object.

    Raises:
        RuntimeError: If ``GUMROAD_ACCESS_TOKEN`` is not set.
        requests.HTTPError: If the API returns a non-2xx status.
    """
    token = _get_access_token()
    url = path if path.startswith("http") else GUMROAD_BASE_URL + path

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    response = requests.request(
        method=method,
        url=url,
        headers=headers,
        params=params,
        json=json,
        timeout=timeout,
    )
    response.raise_for_status()
    return response


def get(path: str, **kwargs: Any) -> requests.Response:
    """Convenience wrapper for GET requests."""
    return gumroad_request("GET", path, **kwargs)


def post(path: str, *, json: dict[str, Any] | None = None, **kwargs: Any) -> requests.Response:
    """Convenience wrapper for POST requests."""
    return gumroad_request("POST", path, json=json, **kwargs)


def _normalize_products(payload: Any) -> list[dict[str, Any]]:
    """Extract a list of product dicts from a Gumroad API response."""
    if isinstance(payload, dict):
        for key in ("products", "data", "results"):
            if isinstance(payload.get(key), list):
                return payload[key]
        return []
    if isinstance(payload, list):
        return payload
    return []


def list_products() -> list[dict[str, Any]]:
    """List all products owned by the authenticated user (raw API data)."""
    response = get("/v2/products")
    return _normalize_products(response.json())


def _cache_path() -> Path:
    """Return the path to the products cache file."""
    return CACHE_DIR / "gumroad_products.json"


def _is_cache_valid(path: Path) -> bool:
    """Return True if the cache file exists and is younger than CACHE_TTL."""
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text())
        fetched_at = data.get("fetched_at", 0)
        return (time.time() - fetched_at) < CACHE_TTL
    except (json.JSONDecodeError, OSError):
        return False


def list_products_cached() -> list[dict[str, str]]:
    """List products, returning only ``name`` and ``id``.

    Results are cached for one hour in the ``cache`` folder under the current
    directory. If a valid cache file exists it is returned; otherwise the Gumroad
    API is queried and the cache is refreshed.
    """
    cache_file = _cache_path()

    if _is_cache_valid(cache_file):
        try:
            data = json.loads(cache_file.read_text())
            return data.get("products", [])
        except (json.JSONDecodeError, OSError):
            pass

    products = list_products()
    result = [
        {"name": str(p.get("name", "")), "id": str(p.get("id", ""))}
        for p in products
    ]

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        json.dumps({"fetched_at": time.time(), "products": result}, indent=2)
    )

    return result


def main() -> None:
    """Demo: list products (name + id) using the env-provided access token."""
    try:
        products = list_products_cached()
        print(f"Fetched {len(products)} product(s) from Gumroad")
        for product in products:
            print(f"- {product['name']} ({product['id']})")
    except RuntimeError as exc:
        print(f"Configuration error: {exc}")
    except requests.HTTPError as exc:
        print(f"Gumroad API error: {exc.response.status_code} {exc.response.text}")


if __name__ == "__main__":
    main()
