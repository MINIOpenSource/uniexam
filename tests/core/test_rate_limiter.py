# -*- coding: utf-8 -*-
import time
import pytest
from unittest.mock import patch, MagicMock

# Module to test
from app.core import rate_limiter
from app.core.config import Settings, RateLimitConfig, UserRateLimits
from app.models.user_models import UserTag

# Helper to reset global state between tests
def reset_rate_limiter_state():
    rate_limiter.ip_exam_request_timestamps.clear()
    rate_limiter.ip_auth_attempt_timestamps.clear()

@pytest.fixture(autouse=True)
def auto_reset_state():
    reset_rate_limiter_state()
    yield
    reset_rate_limiter_state()

@pytest.fixture
def mock_settings_rate_limits(monkeypatch):
    # Define some default rate limits for testing
    mock_config = Settings(
        rate_limits={
            "default_user": UserRateLimits(
                get_exam=RateLimitConfig(limit=3, window=60),      # 3 requests per 60s
                auth_attempts=RateLimitConfig(limit=5, window=300) # 5 attempts per 300s
            ),
            "limited_user": UserRateLimits(
                get_exam=RateLimitConfig(limit=1, window=60),      # 1 request per 60s
                auth_attempts=RateLimitConfig(limit=2, window=300) # 2 attempts per 300s
            )
        }
        # Add other necessary Settings fields if they are accessed by the module directly
        # For now, rate_limiter only seems to access settings.rate_limits
    )
    monkeypatch.setattr(rate_limiter, "settings", mock_config)
    return mock_config

# --- Test Cases ---

def test_is_rate_limited_under_limit(mock_settings_rate_limits):
    client_ip = "1.2.3.4"
    action = "get_exam"

    assert not rate_limiter.is_rate_limited(client_ip, action), "First request should not be limited."
    assert not rate_limiter.is_rate_limited(client_ip, action), "Second request should not be limited."
    assert not rate_limiter.is_rate_limited(client_ip, action), "Third request should not be limited."

    # Timestamps dict should be populated
    assert client_ip in rate_limiter.ip_exam_request_timestamps
    assert len(rate_limiter.ip_exam_request_timestamps[client_ip]) == 3

def test_is_rate_limited_exceeds_limit(mock_settings_rate_limits):
    client_ip = "1.2.3.5"
    action = "get_exam" # Default limit is 3 per 60s

    rate_limiter.is_rate_limited(client_ip, action) # 1
    rate_limiter.is_rate_limited(client_ip, action) # 2
    rate_limiter.is_rate_limited(client_ip, action) # 3
    assert rate_limiter.is_rate_limited(client_ip, action), "Fourth request should be limited."

    # Check state
    assert len(rate_limiter.ip_exam_request_timestamps[client_ip]) == 3 # Should not grow beyond limit once limited, or should be 4 then cleaned. The code appends then checks.
                                                                        # The current implementation stores 3, then the 4th call returns True but doesn't store if it would exceed.
                                                                        # Let's re-check the logic:
                                                                        # valid_timestamps = [...]
                                                                        # if len(valid_timestamps) >= limit: return True
                                                                        # valid_timestamps.append(current_time)
                                                                        # So, if limit is 3, after 3 calls, len is 3. 4th call, len is still 3 (from previous calls),
                                                                        # len >= limit is true. It does not append the 4th timestamp.
    # The log message says "len(valid_timestamps)} 次 (requests) >= {action_limit_config.limit}",
    # if valid_timestamps has 3, and limit is 3, it's 3 >= 3, so it's limited.
    # The timestamp list will contain the 3 valid timestamps.

def test_is_rate_limited_time_window_expiry(mock_settings_rate_limits):
    client_ip = "1.2.3.6"
    action = "get_exam" # Default: 3 per 60s

    with patch.object(time, 'time') as mock_time:
        # First request
        mock_time.return_value = 1000.0
        assert not rate_limiter.is_rate_limited(client_ip, action), "Request 1"

        # Second request
        mock_time.return_value = 1010.0
        assert not rate_limiter.is_rate_limited(client_ip, action), "Request 2"

        # Third request, still within window
        mock_time.return_value = 1030.0
        assert not rate_limiter.is_rate_limited(client_ip, action), "Request 3"

        # Fourth request, should be limited
        mock_time.return_value = 1040.0
        assert rate_limiter.is_rate_limited(client_ip, action), "Request 4 should be limited"

        # Fifth request, after window expiry for the first request (1000 + 60 = 1060)
        mock_time.return_value = 1065.0 # 1065 is > 1000 + 60
        assert not rate_limiter.is_rate_limited(client_ip, action), "Request 5 (after window expiry for req 1) should not be limited."

        # Timestamps list should now contain [1010.0, 1030.0, 1065.0]
        assert rate_limiter.ip_exam_request_timestamps[client_ip] == [1010.0, 1030.0, 1065.0]

def test_is_rate_limited_different_actions_separate_limits(mock_settings_rate_limits):
    client_ip = "1.2.3.7"
    action_exam = "get_exam"       # 3 per 60s
    action_auth = "auth_attempts"  # 5 per 300s

    # Exhaust get_exam limit
    for _ in range(3):
        assert not rate_limiter.is_rate_limited(client_ip, action_exam)
    assert rate_limiter.is_rate_limited(client_ip, action_exam), "get_exam should be limited."

    # auth_attempts should still be allowed
    assert not rate_limiter.is_rate_limited(client_ip, action_auth), "auth_attempts should not be limited by get_exam limit."
    assert client_ip in rate_limiter.ip_exam_request_timestamps
    assert client_ip in rate_limiter.ip_auth_attempt_timestamps
    assert len(rate_limiter.ip_auth_attempt_timestamps[client_ip]) == 1

def test_is_rate_limited_different_ips_separate_limits(mock_settings_rate_limits):
    client_ip1 = "1.2.3.8"
    client_ip2 = "1.2.3.9"
    action = "get_exam"

    # IP1 makes 2 requests
    assert not rate_limiter.is_rate_limited(client_ip1, action)
    assert not rate_limiter.is_rate_limited(client_ip1, action)

    # IP2 makes 1 request
    assert not rate_limiter.is_rate_limited(client_ip2, action)

    assert len(rate_limiter.ip_exam_request_timestamps[client_ip1]) == 2
    assert len(rate_limiter.ip_exam_request_timestamps[client_ip2]) == 1

    # IP1 makes 3rd request (limit for IP1)
    assert not rate_limiter.is_rate_limited(client_ip1, action)
    assert rate_limiter.is_rate_limited(client_ip1, action), "IP1 should now be limited."

    # IP2 should still be able to make requests
    assert not rate_limiter.is_rate_limited(client_ip2, action), "IP2 should not be affected by IP1's limit."
    assert len(rate_limiter.ip_exam_request_timestamps[client_ip2]) == 2


def test_is_rate_limited_limited_user_tag(mock_settings_rate_limits):
    client_ip = "1.2.3.10"
    action = "get_exam" # limited_user: 1 per 60s

    # First request for limited user
    assert not rate_limiter.is_rate_limited(client_ip, action, user_tags=[UserTag.LIMITED, UserTag.USER])
    # Second request for limited user should be limited
    assert rate_limiter.is_rate_limited(client_ip, action, user_tags=[UserTag.LIMITED, UserTag.USER]), "Limited user should be limited on 2nd request."

    # Check state for this IP
    assert len(rate_limiter.ip_exam_request_timestamps[client_ip]) == 1

    # Another IP, default user, should have different limits
    client_ip_default = "1.2.3.11"
    assert not rate_limiter.is_rate_limited(client_ip_default, action, user_tags=[UserTag.USER]), "Default user, 1st req"
    assert not rate_limiter.is_rate_limited(client_ip_default, action, user_tags=[UserTag.USER]), "Default user, 2nd req"
    assert len(rate_limiter.ip_exam_request_timestamps[client_ip_default]) == 2


def test_is_rate_limited_missing_user_type_config(monkeypatch):
    client_ip = "1.2.3.12"
    action = "get_exam"

    # Settings that are missing the 'default_user' configuration
    mock_config_missing_type = Settings(rate_limits={}) # Empty rate_limits
    monkeypatch.setattr(rate_limiter, "settings", mock_config_missing_type)

    with patch.object(rate_limiter._rate_limiter_logger, 'error') as mock_log_error:
        assert not rate_limiter.is_rate_limited(client_ip, action), "Should not limit if user type config is missing."
        mock_log_error.assert_called_once()
        assert "未找到用户类型 'default_user' 的速率限制配置" in mock_log_error.call_args[0][0] or                "Rate limit config not found for user type 'default_user'" in mock_log_error.call_args[0][0]


def test_is_rate_limited_missing_action_config(mock_settings_rate_limits, monkeypatch):
    client_ip = "1.2.3.13"
    unknown_action = "unknown_action_type"

    # mock_settings_rate_limits already set by fixture

    with patch.object(rate_limiter._rate_limiter_logger, 'error') as mock_log_error:
        assert not rate_limiter.is_rate_limited(client_ip, unknown_action), "Should not limit if action config is missing."
        mock_log_error.assert_called_once()
        assert f"未在用户类型 'default_user' 中找到操作 '{unknown_action}' 的速率限制配置" in mock_log_error.call_args[0][0] or                f"Rate limit config not found for action '{unknown_action}' in user type 'default_user'" in mock_log_error.call_args[0][0]


def test_is_rate_limited_unknown_action_type_for_storage(mock_settings_rate_limits):
    client_ip = "1.2.3.14"
    # This action is configured in settings but not mapped to a global timestamp dict in the module
    action_misconfigured_storage = "newly_added_action_in_config_only"

    # Add this action to the mock settings
    mock_settings_rate_limits.rate_limits["default_user"].newly_added_action_in_config_only = RateLimitConfig(limit=1, window=10)

    with patch.object(rate_limiter._rate_limiter_logger, 'warning') as mock_log_warning:
        assert not rate_limiter.is_rate_limited(client_ip, action_misconfigured_storage), "Should not limit if action has no internal timestamp dict."
        mock_log_warning.assert_called_once()
        assert f"未知的速率限制操作类型 (Unknown rate limit action type): {action_misconfigured_storage}" in mock_log_warning.call_args[0][0]
