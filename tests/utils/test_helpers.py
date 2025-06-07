# -*- coding: utf-8 -*-
import datetime
import ipaddress
import random
import re
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import Request

from app.utils import helpers

# --- Tests for get_current_timestamp_str ---
def test_get_current_timestamp_str():
    ts_str = helpers.get_current_timestamp_str()
    # Check format "YYYY-MM-DD HH:MM:SS"
    assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", ts_str)
    # Check if the time is recent (e.g., within the last 5 seconds)
    parsed_time = datetime.datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
    assert abs((datetime.datetime.now() - parsed_time).total_seconds()) < 5

# --- Tests for format_short_uuid ---
def test_format_short_uuid_valid():
    u = uuid.uuid4()
    s_uuid = str(u)
    short_u = helpers.format_short_uuid(u)
    assert short_u == f"{s_uuid[:4]}....{s_uuid[-4:]}"

    short_s_uuid = helpers.format_short_uuid(s_uuid)
    assert short_s_uuid == f"{s_uuid[:4]}....{s_uuid[-4:]}"

def test_format_short_uuid_short_input():
    short_str = "12345"
    assert helpers.format_short_uuid(short_str) == short_str

def test_format_short_uuid_exactly_8_chars():
    # Based on current logic len(s) > 8, so 8 chars should be returned as is.
    # If it was >= 8, then "1234....78" would be expected.
    # Current: "12345678" -> "12345678"
    # If len(s) >= 8: "12345678" -> "1234....5678" (adjusting expectation based on current code)
    # The code is `if len(s) > 8`, so an 8-char string will be returned as is.
    # A 9-char string "123456789" -> "1234....6789"
    eight_char_str = "12345678"
    assert helpers.format_short_uuid(eight_char_str) == eight_char_str

    nine_char_str = "123456789"
    assert helpers.format_short_uuid(nine_char_str) == f"{nine_char_str[:4]}....{nine_char_str[-4:]}"


# --- Tests for get_client_ip_from_request ---
CLOUDFLARE_IPV4_CIDRS = [ipaddress.ip_network("103.21.244.0/22")]
CLOUDFLARE_IPV6_CIDRS = [ipaddress.ip_network("2400:cb00::/32")]

def mock_fastapi_request(client_host: str = None, headers: dict = None) -> Request:
    scope = {"type": "http"}
    if client_host:
        # FastAPI's Request expects client to be a tuple [host, port] or None
        scope["client"] = (client_host, 12345)
    else:
        scope["client"] = None # Explicitly set to None if no client_host

    # Simulate the _receive_called flag and _receive method for Request
    # This is a workaround for "AttributeError: 'Request' object has no attribute '_receive_called'"
    # when accessing request.headers if no actual receive has happened.
    # A more robust mock might involve deeper FastAPI internals or using TestClient.

    request_mock = Request(scope)

    # Override headers directly if provided
    if headers is not None:
        request_mock._headers = headers # Store as dict for .get()
        # For Starlette/FastAPI, headers are often case-insensitive.
        # A more accurate mock would use `starlette.datastructures.Headers`.
        # For simplicity in this unit test, direct dict assignment and .get works if keys match case.
        # To make it more robust:
        from starlette.datastructures import Headers
        request_mock._headers = Headers(headers=headers)


    return request_mock

def test_get_client_ip_direct_client():
    req = mock_fastapi_request(client_host="50.0.0.1")
    assert helpers.get_client_ip_from_request(req) == "50.0.0.1"

def test_get_client_ip_no_client_host_uses_x_real_ip():
    req = mock_fastapi_request(client_host=None, headers={"x-real-ip": "60.0.0.1"})
    assert helpers.get_client_ip_from_request(req) == "60.0.0.1"

def test_get_client_ip_no_client_host_uses_x_forwarded_for():
    req = mock_fastapi_request(client_host=None, headers={"x-forwarded-for": "70.0.0.1, 70.0.0.2"})
    assert helpers.get_client_ip_from_request(req) == "70.0.0.1" # Takes the first IP

def test_get_client_ip_no_client_host_no_headers():
    req = mock_fastapi_request(client_host=None, headers={})
    assert helpers.get_client_ip_from_request(req) == "Unknown"

def test_get_client_ip_from_cloudflare_uses_cf_connecting_ip():
    cf_ip = CLOUDFLARE_IPV4_CIDRS[0].network_address + 1 # e.g., 103.21.244.1
    req = mock_fastapi_request(client_host=str(cf_ip), headers={"cf-connecting-ip": "80.0.0.1"})
    ip = helpers.get_client_ip_from_request(req, CLOUDFLARE_IPV4_CIDRS, CLOUDFLARE_IPV6_CIDRS)
    assert ip == "80.0.0.1"

def test_get_client_ip_from_cloudflare_cf_invalid_uses_xff():
    cf_ip = str(CLOUDFLARE_IPV4_CIDRS[0].network_address + 2)
    req = mock_fastapi_request(
        client_host=cf_ip,
        headers={"cf-connecting-ip": "not-an-ip", "x-forwarded-for": "90.0.0.1, 90.0.0.2"}
    )
    ip = helpers.get_client_ip_from_request(req, CLOUDFLARE_IPV4_CIDRS, CLOUDFLARE_IPV6_CIDRS)
    assert ip == "90.0.0.1"

def test_get_client_ip_from_cloudflare_cf_and_xff_invalid_uses_cf_host():
    cf_ip_str = str(CLOUDFLARE_IPV4_CIDRS[0].network_address + 3)
    req = mock_fastapi_request(
        client_host=cf_ip_str,
        headers={"cf-connecting-ip": "invalid1", "x-forwarded-for": "invalid2"}
    )
    ip = helpers.get_client_ip_from_request(req, CLOUDFLARE_IPV4_CIDRS, CLOUDFLARE_IPV6_CIDRS)
    assert ip == cf_ip_str

def test_get_client_ip_not_from_cloudflare_ignores_cf_headers():
    non_cf_ip = "10.0.0.1"
    req = mock_fastapi_request(client_host=non_cf_ip, headers={"cf-connecting-ip": "100.0.0.1", "x-forwarded-for": "100.0.0.2"})
    ip = helpers.get_client_ip_from_request(req, CLOUDFLARE_IPV4_CIDRS, CLOUDFLARE_IPV6_CIDRS)
    assert ip == non_cf_ip

def test_get_client_ip_invalid_direct_client_host():
    req = mock_fastapi_request(client_host="not-a-valid-ip-address")
    # The function currently returns the invalid string if ipaddress.ip_address() fails for direct_connecting_ip_str
    assert helpers.get_client_ip_from_request(req) == "not-a-valid-ip-address"


# --- Tests for shuffle_dictionary_items ---
def test_shuffle_dictionary_items_basic():
    original_dict = {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5}
    shuffled = helpers.shuffle_dictionary_items(original_dict)

    assert isinstance(shuffled, dict)
    assert set(original_dict.keys()) == set(shuffled.keys())
    assert all(original_dict[k] == shuffled[k] for k in original_dict)

    # Check if order is different (can fail for small dicts by chance)
    # For a more robust test of "shuffled-ness", one might compare item lists
    # or run multiple times, but for a unit test, checking content is primary.
    if len(original_dict) > 1: # Only makes sense if there's something to shuffle
        original_items = list(original_dict.items())
        shuffled_items = list(shuffled.items())
        # This can still fail by chance, but less likely for larger dicts
        # A better test would be to mock random.shuffle to ensure it's called.
        with patch.object(random, 'shuffle') as mock_shuffle:
            helpers.shuffle_dictionary_items(original_dict)
            mock_shuffle.assert_called_once()


def test_shuffle_dictionary_items_empty():
    assert helpers.shuffle_dictionary_items({}) == {}

def test_shuffle_dictionary_items_invalid_input():
    with pytest.raises(TypeError):
        helpers.shuffle_dictionary_items([1, 2, 3]) # type: ignore

# --- Tests for generate_random_hex_string_of_bytes ---
def test_generate_random_hex_string():
    for length_bytes in [1, 5, 16, 32]:
        hex_str = helpers.generate_random_hex_string_of_bytes(length_bytes)
        assert len(hex_str) == length_bytes * 2
        assert all(c in "0123456789abcdef" for c in hex_str)

def test_generate_random_hex_string_invalid_length():
    with pytest.raises(ValueError):
        helpers.generate_random_hex_string_of_bytes(0)
    with pytest.raises(ValueError):
        helpers.generate_random_hex_string_of_bytes(-1)
