import json
import os
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

from calc_data import gumroad
from calc_data.gumroad import _store_response
from calc_data.products_dataclass import (
    GumroadProduct,
    GumroadProductsCache,
    products_from_cache,
    products_to_cache,
)
from calc_data.utilities import _is_cache_valid


def test_store_response_creates_versioned_cache_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gumroad, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(gumroad, "CACHE_VERSION", "v1")

    mock_response = MagicMock(spec=requests.Response)
    mock_response.json.return_value = {"success": True, "products": []}

    dummy_function = MagicMock(return_value=mock_response)
    decorated_endpoint_handler = _store_response(dummy_function)

    result_response = decorated_endpoint_handler("/v2/products")

    assert result_response == mock_response
    expected_cache_file = tmp_path / "gumroad_v2_products_v1.json"
    assert expected_cache_file.exists()

    cache_payload = json.loads(expected_cache_file.read_text())
    assert cache_payload["version"] == "v1"
    assert cache_payload["cache_version"] == "v1"
    assert "fetched_at" not in cache_payload
    assert cache_payload["response"] == {"success": True, "products": []}


def test_store_response_updates_file_name_when_version_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gumroad, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(gumroad, "CACHE_VERSION", "v2")

    mock_response = MagicMock(spec=requests.Response)
    mock_response.json.return_value = {"count": 42}

    dummy_function = MagicMock(return_value=mock_response)
    decorated_endpoint_handler = _store_response(dummy_function)

    decorated_endpoint_handler("custom/endpoint")

    expected_cache_file = tmp_path / "gumroad_custom_endpoint_v2.json"
    assert expected_cache_file.exists()

    cache_payload = json.loads(expected_cache_file.read_text())
    assert cache_payload["version"] == "v2"
    assert cache_payload["cache_version"] == "v2"
    assert cache_payload["response"] == {"count": 42}


def test_store_response_handles_non_json_response_gracefully(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gumroad, "CACHE_DIR", tmp_path)

    mock_response = MagicMock(spec=requests.Response)
    mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "doc", 0)

    dummy_function = MagicMock(return_value=mock_response)
    decorated_endpoint_handler = _store_response(dummy_function)

    result_response = decorated_endpoint_handler("/v2/invalid")

    assert result_response == mock_response
    assert not (tmp_path / "gumroad_v2_invalid_v1.json").exists()


def test_store_response_handles_integer_cache_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gumroad, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(gumroad, "CACHE_VERSION", 3)

    mock_response = MagicMock(spec=requests.Response)
    mock_response.json.return_value = {"status": "ok"}

    dummy_function = MagicMock(return_value=mock_response)
    decorated_endpoint_handler = _store_response(dummy_function)

    decorated_endpoint_handler("/v2/sales")

    expected_cache_file = tmp_path / "gumroad_v2_sales_v3.json"
    assert expected_cache_file.exists()

    cache_payload = json.loads(expected_cache_file.read_text())
    assert cache_payload["version"] == "3"
    assert cache_payload["cache_version"] == "3"


def test_store_response_passes_keyword_arguments(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gumroad, "CACHE_DIR", tmp_path)

    mock_response = MagicMock(spec=requests.Response)
    mock_response.json.return_value = {"page": 2}

    dummy_function = MagicMock(return_value=mock_response)
    decorated_endpoint_handler = _store_response(dummy_function)

    decorated_endpoint_handler("/v2/products", params={"page": 2}, timeout=15.0)

    dummy_function.assert_called_once_with("/v2/products", params={"page": 2}, timeout=15.0)


def test_list_products_triggers_single_versioned_cache_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gumroad, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(gumroad, "CACHE_VERSION", "v1")

    sample_product_payload = {
        "success": True,
        "products": [
            {
                "name": "Sample Product",
                "id": "prod_123",
                "price": 1000,
                "currency": "usd",
            }
        ],
    }

    mock_response = MagicMock(spec=requests.Response)
    mock_response.json.return_value = sample_product_payload

    monkeypatch.setattr(gumroad, "gumroad_request", MagicMock(return_value=mock_response))

    products, raw_response_data = gumroad.list_products()

    assert len(products) == 1
    assert products[0].name == "Sample Product"
    assert products[0].id == "prod_123"
    assert raw_response_data == sample_product_payload

    versioned_cache_file = tmp_path / "gumroad_v2_products_v1.json"
    assert versioned_cache_file.exists()

    unversioned_cache_file = tmp_path / "gumroad_products.json"
    assert not unversioned_cache_file.exists()


def test_list_products_handles_invalid_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gumroad, "CACHE_DIR", tmp_path)

    mock_response = MagicMock(spec=requests.Response)
    mock_response.text = "invalid json payload"
    mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "doc", 0)

    monkeypatch.setattr(gumroad, "gumroad_request", MagicMock(return_value=mock_response))

    products, raw_response_data = gumroad.list_products()

    assert products == []
    assert raw_response_data == {}


def test_get_product_returns_parsed_product(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gumroad, "CACHE_DIR", tmp_path)

    product_payload = {
        "success": True,
        "product": {
            "name": "Sample Product",
            "id": "prod_123",
            "price": 1000,
            "currency": "usd",
        },
    }

    mock_response = MagicMock(spec=requests.Response)
    mock_response.json.return_value = product_payload

    monkeypatch.setattr(gumroad, "gumroad_request", MagicMock(return_value=mock_response))

    product, raw_response_data = gumroad.get_product("prod_123")

    assert product is not None
    assert product.name == "Sample Product"
    assert product.id == "prod_123"
    assert raw_response_data == product_payload
    assert (tmp_path / "gumroad_v2_products_prod_123_v1.json").exists()


def test_get_product_returns_none_when_response_has_no_product(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gumroad, "CACHE_DIR", tmp_path)

    mock_response = MagicMock(spec=requests.Response)
    mock_response.json.return_value = {"success": False, "message": "Product not found"}

    monkeypatch.setattr(gumroad, "gumroad_request", MagicMock(return_value=mock_response))

    product, raw_response_data = gumroad.get_product("missing_product")

    assert product is None
    assert raw_response_data == {"success": False, "message": "Product not found"}


def test_get_product_rejects_empty_product_id() -> None:
    with pytest.raises(ValueError):
        gumroad.get_product("   ")


def test_store_response_returns_cached_response_when_cache_is_valid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gumroad, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(gumroad, "CACHE_VERSION", "v1")

    cached_response_data = {"success": True, "products": [{"name": "Cached Product", "id": "cached_123"}]}
    cache_file = tmp_path / "gumroad_v2_products_v1.json"
    cache_payload = {
        "version": "v1",
        "cache_version": "v1",
        "response": cached_response_data,
    }
    cache_file.write_text(json.dumps(cache_payload))

    dummy_function = MagicMock()
    decorated_endpoint_handler = _store_response(dummy_function)

    result_response = decorated_endpoint_handler("/v2/products")

    dummy_function.assert_not_called()
    assert result_response.status_code == 200
    assert result_response.json() == cached_response_data


def test_store_response_invalidates_cache_and_fetches_when_cache_is_expired(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gumroad, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(gumroad, "CACHE_VERSION", "v1")

    expired_cache_file = tmp_path / "gumroad_v2_products_v1.json"
    expired_cache_payload = {
        "version": "v1",
        "cache_version": "v1",
        "response": {"success": True, "products": [{"name": "Old Product", "id": "old_123"}]},
    }
    expired_cache_file.write_text(json.dumps(expired_cache_payload))

    expired_timestamp = time.time() - 3601
    os.utime(expired_cache_file, (expired_timestamp, expired_timestamp))

    fresh_response_data = {"success": True, "products": [{"name": "Fresh Product", "id": "fresh_123"}]}
    mock_response = MagicMock(spec=requests.Response)
    mock_response.json.return_value = fresh_response_data

    dummy_function = MagicMock(return_value=mock_response)
    decorated_endpoint_handler = _store_response(dummy_function)

    result_response = decorated_endpoint_handler("/v2/products")

    dummy_function.assert_called_once_with("/v2/products")
    assert result_response == mock_response

    updated_cache_payload = json.loads(expired_cache_file.read_text())
    assert updated_cache_payload["response"] == fresh_response_data
    assert "fetched_at" not in updated_cache_payload


def test_store_response_refetches_when_cache_file_is_corrupt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gumroad, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(gumroad, "CACHE_VERSION", "v1")

    corrupted_cache_file = tmp_path / "gumroad_v2_products_v1.json"
    corrupted_cache_file.write_text("invalid json content")

    fresh_response_data = {"success": True, "products": []}
    mock_response = MagicMock(spec=requests.Response)
    mock_response.json.return_value = fresh_response_data

    dummy_function = MagicMock(return_value=mock_response)
    decorated_endpoint_handler = _store_response(dummy_function)

    result_response = decorated_endpoint_handler("/v2/products")

    dummy_function.assert_called_once_with("/v2/products")
    assert result_response == mock_response

    updated_cache_payload = json.loads(corrupted_cache_file.read_text())
    assert updated_cache_payload["response"] == fresh_response_data


def test_is_cache_valid_checks_file_modification_time(tmp_path: Path) -> None:
    test_cache_file = tmp_path / "test_cache.json"
    assert not _is_cache_valid(test_cache_file)

    test_cache_file.write_text("{}")
    assert _is_cache_valid(test_cache_file)

    expired_timestamp = time.time() - 3601
    os.utime(test_cache_file, (expired_timestamp, expired_timestamp))
    assert not _is_cache_valid(test_cache_file)


def test_gumroad_product_dataclass_handles_latest_cached_json_fields() -> None:
    sample_product_payload = {
        "name": "NiFt, Simple, Minimalistic, Frictionless Note App",
        "description": "<h1>NiFt [Note It FasT]</h1>",
        "require_shipping": False,
        "preview_url": "https://public-files.gumroad.com/dzjbgjm3otclanv4an3z8tdi2grr",
        "custom_receipt": None,
        "customizable_price": False,
        "custom_permalink": "nift",
        "subscription_duration": None,
        "id": "phRR3J4IO3lBh25O2IV_dQ==",
        "url": None,
        "price": 500,
        "currency": "usd",
        "taxonomy_id": 266,
        "category": "other",
        "category_label": "Other",
        "short_url": "https://tmahmood.gumroad.com/l/nift",
        "landing_url": "https://tmahmood.gumroad.com/l/nift",
        "thumbnail_url": None,
        "tags": ["productivity", "software"],
        "formatted_price": "$5",
        "published": True,
        "file_info": {},
        "max_purchase_count": None,
        "deleted": False,
        "custom_fields": [],
        "custom_summary": "NiFt note app",
        "is_tiered_membership": False,
        "recurrences": None,
        "covers": [{"id": "cover_1", "url": "https://example.com/cover.png"}],
        "main_cover_id": "c362d0f399e8c5700ca9b1809ffdc372",
        "bundle_products": [],
        "variants": [],
        "custom_delivery_url": None,
        "sales_count": 0,
        "sales_usd_cents": 0.0,
    }

    product_instance = GumroadProduct(**sample_product_payload)
    assert product_instance.name == "NiFt, Simple, Minimalistic, Frictionless Note App"
    assert product_instance.landing_url == "https://tmahmood.gumroad.com/l/nift"
    assert product_instance.published is True
    assert product_instance.file_info == {}
    assert product_instance.short_url == "https://tmahmood.gumroad.com/l/nift"

    cache_payload = {
        "version": "v1",
        "cache_version": "v1",
        "response": {"success": True, "products": [sample_product_payload]},
    }
    parsed_cache_container = GumroadProductsCache.from_dict(cache_payload)
    assert len(parsed_cache_container.products) == 1
    assert parsed_cache_container.products[0].landing_url == "https://tmahmood.gumroad.com/l/nift"

    parsed_products = products_from_cache(cache_payload)
    assert len(parsed_products) == 1
    assert parsed_products[0].landing_url == "https://tmahmood.gumroad.com/l/nift"
    assert parsed_products[0].published is True
    assert parsed_products[0].file_info == {}

    serialized_dictionary = product_instance.to_dict()
    assert serialized_dictionary["landing_url"] == "https://tmahmood.gumroad.com/l/nift"
    assert serialized_dictionary["published"] is True
    assert serialized_dictionary["file_info"] == {}
    assert "url" not in serialized_dictionary

    serialized_cache = products_to_cache([product_instance], fetched_at=1234567890.0)
    assert serialized_cache["fetched_at"] == 1234567890.0
    assert len(serialized_cache["products"]) == 1
    assert serialized_cache["products"][0]["landing_url"] == "https://tmahmood.gumroad.com/l/nift"
