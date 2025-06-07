# -*- coding: utf-8 -*-
"""
app.core.security 模块的单元测试。
(Unit tests for the app.core.security module.)
"""

import time

import pytest
from fastapi import HTTPException

from app.core.config import settings  # 需要settings来获取token有效期等配置

# 被测试模块的导入 (Imports from the module under test)
from app.core.security import (
    RequireTags,
    create_access_token,
    get_all_active_token_info,
    get_password_hash,
    invalidate_all_tokens_for_user,
    invalidate_token,
    validate_token_and_get_user_info,
    verify_password,
)
from app.models.user_models import UserTag

# (Need settings for token expiry config etc.)


# region 密码工具函数测试 (Password Utility Function Tests)


def test_verify_password_correct():
    """测试 verify_password 函数能否正确验证匹配的密码。"""
    plain_password = "测试密码123!@#"
    hashed_password = get_password_hash(plain_password)
    assert verify_password(plain_password, hashed_password) is True, (
        "正确密码未能通过验证。"
    )


def test_verify_password_incorrect():
    """测试 verify_password 函数能否正确拒绝不匹配的密码。"""
    plain_password = "测试密码123!@#"
    wrong_password = "错误密码WrongPassword"
    hashed_password = get_password_hash(plain_password)
    assert verify_password(wrong_password, hashed_password) is False, (
        "错误密码通过了验证。"
    )


def test_get_password_hash_generates_valid_hash():
    """
    测试 get_password_hash 生成的哈希值能被 verify_password 验证。
    并检查同一密码两次哈希生成不同结果（由于盐值）。
    """
    password = "这是一个健壮的密码StrongPassword1"
    hash1 = get_password_hash(password)
    hash2 = get_password_hash(password)

    assert verify_password(password, hash1) is True, "哈希1未能通过验证。"
    assert verify_password(password, hash2) is True, "哈希2未能通过验证。"
    assert hash1 != hash2, "同一密码生成的两个哈希值相同，盐值可能未生效。"


# endregion

# region Token 工具函数测试 (Token Utility Function Tests)
# 这些测试将使用 pytest-mock 的 mocker fixture 来模拟全局的 _active_tokens 和 _token_lock
# (These tests will use pytest-mock's mocker fixture to mock global _active_tokens and _token_lock)


@pytest.mark.asyncio
async def test_create_access_token_successful(mocker):
    """测试 create_access_token 能否成功创建并存储Token。"""
    # 模拟全局变量 _active_tokens
    # (Mock the global variable _active_tokens)
    mocked_active_tokens = {}
    mocker.patch("app.core.security._active_tokens", mocked_active_tokens)

    # _token_lock 是 asyncio.Lock，通常不需要模拟其行为，除非要测试并发细节
    # ( _token_lock is an asyncio.Lock, usually no need to mock its behavior unless testing concurrency details)

    user_uid = "test_user_token"
    user_tags = [UserTag.USER, UserTag.EXAMINER]

    token_str = await create_access_token(user_uid, user_tags)

    assert isinstance(token_str, str), "创建的Token不是字符串类型。"
    assert len(token_str) == settings.token_length_bytes * 2, "Token长度不符合配置。"

    assert token_str in mocked_active_tokens, "Token未添加到 _active_tokens。"
    token_data = mocked_active_tokens[token_str]
    assert token_data["user_uid"] == user_uid, "存储的 user_uid 不正确。"
    assert set(token_data["tags"]) == set([tag.value for tag in user_tags]), (
        "存储的 tags 不正确。"
    )
    assert "expires_at" in token_data, "Token数据中缺少 expires_at 字段。"
    assert token_data["expires_at"] > time.time(), "Token的过期时间不正确（应在未来）。"


@pytest.mark.asyncio
async def test_validate_token_and_get_user_info_valid_token(mocker):
    """测试 validate_token_and_get_user_info 对有效Token的验证。"""
    user_uid = "valid_user"
    user_tags_enum = [UserTag.USER]
    user_tags_value = [tag.value for tag in user_tags_enum]
    valid_token = "valid_token_string_example"

    mocked_active_tokens = {
        valid_token: {
            "user_uid": user_uid,
            "tags": user_tags_value,
            "expires_at": time.time() + settings.token_expiry_hours * 3600,
        }
    }
    mocker.patch("app.core.security._active_tokens", mocked_active_tokens)

    user_info = await validate_token_and_get_user_info(valid_token)

    assert user_info is not None, "有效Token未能通过验证。"
    assert user_info["user_uid"] == user_uid, "返回的 user_uid 不正确。"
    assert set(user_info["tags"]) == set(user_tags_enum), "返回的 tags 不正确。"


@pytest.mark.asyncio
async def test_validate_token_and_get_user_info_invalid_token(mocker):
    """测试 validate_token_and_get_user_info 对无效Token的处理。"""
    mocked_active_tokens = {}  # 确保Token不存在 (Ensure token doesn't exist)
    mocker.patch("app.core.security._active_tokens", mocked_active_tokens)

    invalid_token = "this_token_does_not_exist"
    user_info = await validate_token_and_get_user_info(invalid_token)

    assert user_info is None, "无效Token错误地通过了验证。"


@pytest.mark.asyncio
async def test_validate_token_and_get_user_info_expired_token(mocker):
    """测试 validate_token_and_get_user_info 对过期Token的处理，并检查是否被清理。"""
    user_uid = "expired_user"
    expired_token = "token_that_has_expired"

    mocked_active_tokens = {
        expired_token: {
            "user_uid": user_uid,
            "tags": [UserTag.USER.value],
            "expires_at": time.time() - 3600,  # 1小时前过期 (Expired 1 hour ago)
        }
    }
    mocker.patch("app.core.security._active_tokens", mocked_active_tokens)

    user_info = await validate_token_and_get_user_info(expired_token)

    assert user_info is None, "过期Token错误地通过了验证。"
    assert expired_token not in mocked_active_tokens, (
        "过期Token未从 _active_tokens 中移除。"
    )


@pytest.mark.asyncio
async def test_invalidate_token_removes_token(mocker):
    """测试 invalidate_token 是否能成功移除Token。"""
    token_to_invalidate = "token_to_be_invalidated_soon"
    mocked_active_tokens = {
        token_to_invalidate: {
            "user_uid": "some_user",
            "tags": [UserTag.USER.value],
            "expires_at": time.time() + 3600,
        }
    }
    mocker.patch("app.core.security._active_tokens", mocked_active_tokens)

    await invalidate_token(token_to_invalidate)

    assert token_to_invalidate not in mocked_active_tokens, (
        "invalidate_token 未能移除Token。"
    )


@pytest.mark.asyncio
async def test_get_all_active_token_info_empty(mocker):
    """测试 get_all_active_token_info 在没有活动Token时返回空列表。"""
    mocked_active_tokens = {}
    mocker.patch("app.core.security._active_tokens", mocked_active_tokens)

    tokens_info = await get_all_active_token_info()
    assert tokens_info == [], "当没有活动Token时，未返回空列表。"


@pytest.mark.asyncio
async def test_get_all_active_token_info_with_data(mocker):
    """测试 get_all_active_token_info 能否正确返回活动Token的信息。"""
    uid1, uid2 = "user1_active", "user2_active"
    token1, token2 = "active_token_01", "active_token_02"
    tags1_val, tags2_val = (
        [UserTag.USER.value],
        [
            UserTag.ADMIN.value,
            UserTag.USER.value,
        ],
    )
    expires_at1 = time.time() + 3600
    expires_at2 = time.time() + 7200

    mocked_active_tokens = {
        token1: {"user_uid": uid1, "tags": tags1_val, "expires_at": expires_at1},
        token2: {"user_uid": uid2, "tags": tags2_val, "expires_at": expires_at2},
        "expired_token": {
            "user_uid": "user3",
            "tags": [],
            "expires_at": time.time() - 100,
        },  # 已过期
    }
    mocker.patch("app.core.security._active_tokens", mocked_active_tokens)

    tokens_info = await get_all_active_token_info()

    assert len(tokens_info) == 2, "返回的活动Token数量不正确 (应排除过期Token)。"

    # 校验返回的Token信息 (顺序可能不定，所以需要查找)
    # (Verify returned token info (order might vary, so lookup is needed))
    info1 = next((t for t in tokens_info if t["user_uid"] == uid1), None)
    info2 = next((t for t in tokens_info if t["user_uid"] == uid2), None)

    assert info1 is not None, f"未能找到用户 {uid1} 的Token信息。"
    assert info1["token_prefix"].startswith(token1[:8]), "Token前缀不匹配。"
    assert info1["tags"] == tags1_val, "用户1的标签不匹配。"
    assert "expires_at" in info1, "缺少 expires_at 字段。"  # 具体时间转换已在函数内完成

    assert info2 is not None, f"未能找到用户 {uid2} 的Token信息。"
    assert info2["token_prefix"].startswith(token2[:8]), "Token前缀不匹配。"
    assert info2["tags"] == tags2_val, "用户2的标签不匹配。"


@pytest.mark.asyncio
async def test_invalidate_all_tokens_for_user(mocker):
    """测试 invalidate_all_tokens_for_user 能否正确吊销特定用户的所有Token。"""
    user_to_logout = "logout_user"
    other_user = "other_user_active"
    token1 = "logout_user_token1"
    token2 = "logout_user_token2"
    token3_other = "other_user_token1"

    mocked_active_tokens = {
        token1: {
            "user_uid": user_to_logout,
            "tags": [],
            "expires_at": time.time() + 3600,
        },
        token2: {
            "user_uid": user_to_logout,
            "tags": [],
            "expires_at": time.time() + 7200,
        },
        token3_other: {
            "user_uid": other_user,
            "tags": [],
            "expires_at": time.time() + 3600,
        },
    }
    mocker.patch("app.core.security._active_tokens", mocked_active_tokens)

    invalidated_count = await invalidate_all_tokens_for_user(user_to_logout)

    assert invalidated_count == 2, "吊销的Token数量不正确。"
    assert token1 not in mocked_active_tokens, f"{user_to_logout} 的 Token1 未被吊销。"
    assert token2 not in mocked_active_tokens, f"{user_to_logout} 的 Token2 未被吊销。"
    assert token3_other in mocked_active_tokens, f"{other_user} 的Token被错误吊销。"


@pytest.mark.asyncio
async def test_invalidate_all_tokens_for_user_no_tokens(mocker):
    """测试 invalidate_all_tokens_for_user 在用户没有活动Token时的行为。"""
    mocked_active_tokens = {
        "some_other_token": {
            "user_uid": "another_user",
            "tags": [],
            "expires_at": time.time() + 3600,
        }
    }
    mocker.patch("app.core.security._active_tokens", mocked_active_tokens)

    invalidated_count = await invalidate_all_tokens_for_user("user_with_no_tokens")

    assert invalidated_count == 0, "对没有Token的用户进行吊销操作，返回数量不为0。"
    assert len(mocked_active_tokens) == 1, "活动Token列表被错误修改。"


# endregion

# region RequireTags 依赖项测试 (RequireTags Dependency Tests)


@pytest.mark.asyncio
async def test_require_tags_success():
    """测试 RequireTags 在用户拥有所有必需标签时成功。"""
    required_tags_set = {UserTag.ADMIN, UserTag.MANAGER}
    checker = RequireTags(required_tags_set)

    # 模拟 get_current_user_info_from_token 的成功返回
    # (Simulate successful return from get_current_user_info_from_token)
    mock_user_info = {
        "user_uid": "test_admin_manager",
        "tags": [UserTag.ADMIN, UserTag.MANAGER, UserTag.USER],
    }

    # 直接调用 __call__ 方法进行测试
    # (Directly call __call__ method for testing)
    # 注意: Depends() 本身不会在这里被执行，我们模拟的是它解析后的行为
    # (Note: Depends() itself won't be executed here; we simulate its resolved behavior)
    result_user_info = await checker(user_info=mock_user_info)

    assert result_user_info == mock_user_info, "RequireTags 成功时不应修改用户信息。"


@pytest.mark.asyncio
async def test_require_tags_failure_missing_tags():
    """测试 RequireTags 在用户缺少必需标签时引发 HTTPException。"""
    required_tags_set = {
        UserTag.ADMIN,
        UserTag.MANAGER,
    }  # 需要管理员和经理 (Need ADMIN and MANAGER)
    checker = RequireTags(required_tags_set)

    # 用户只有 ADMIN 标签，缺少 MANAGER (User only has ADMIN tag, missing MANAGER)
    mock_user_info_missing_manager = {
        "user_uid": "test_admin_only",
        "tags": [UserTag.ADMIN, UserTag.USER],
    }

    with pytest.raises(HTTPException) as exc_info:
        await checker(user_info=mock_user_info_missing_manager)

    assert exc_info.value.status_code == 403, "权限不足时状态码应为403。"
    assert "权限不足" in exc_info.value.detail, "权限不足时的错误详情信息不正确。"


@pytest.mark.asyncio
async def test_require_tags_empty_required_succeeds_for_any_user():
    """测试 RequireTags 在没有指定必需标签时允许任何已认证用户通过。"""
    checker = RequireTags(set())  # 空的必需标签集合 (Empty set of required tags)

    mock_user_info_basic = {"user_uid": "test_basic_user", "tags": [UserTag.USER]}

    result_user_info = await checker(user_info=mock_user_info_basic)
    assert result_user_info == mock_user_info_basic, "空必需标签集合应允许用户通过。"


# endregion
