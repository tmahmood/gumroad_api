import json
import os
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

from calc_data import gumroad
from calc_data.gumroad import _store_response
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
