# -*- coding: utf-8 -*-
"""
app.crud.user.UserCRUD 类的单元测试。
(Unit tests for the app.crud.user.UserCRUD class.)
"""

from unittest.mock import AsyncMock

import pytest

from app.core.config import (
    settings,
)  # 用于默认管理员密码等 (For default admin password etc.)
from app.core.interfaces import IDataStorageRepository
from app.core.security import verify_password
from app.crud.user import USER_ENTITY_TYPE, UserCRUD
from app.models.user_models import (
    AdminUserUpdate,
    UserCreate,
    UserInDB,
    UserProfileUpdate,
    UserTag,
)

# 全局测试数据 (Global test data)
TEST_USER_UID = "test_user_01"
TEST_USER_PASSWORD = "SecurePassword123!"
TEST_USER_NICKNAME = "测试用户昵称"
TEST_USER_EMAIL = "test@example.com"
TEST_USER_QQ = "123456789"


@pytest.fixture
def mock_repo(mocker) -> AsyncMock:
    """提供一个被模拟的 IDataStorageRepository 实例的Fixture。"""
    # 使用 AsyncMock 替代 MagicMock 来正确模拟异步方法
    # (Use AsyncMock instead of MagicMock to correctly mock async methods)
    repo = AsyncMock(spec=IDataStorageRepository)
    repo.get_by_id = AsyncMock()
    repo.get_all = AsyncMock()
    repo.create = AsyncMock()
    repo.update = AsyncMock()
    repo.delete = AsyncMock()  # 虽然本测试集可能不直接用，但完整模拟是好的
    # (Although not directly used in this test suite, full mocking is good)
    repo.init_storage_if_needed = AsyncMock()
    return repo


@pytest.fixture
def user_crud_instance(mock_repo: AsyncMock) -> UserCRUD:
    """提供一个 UserCRUD 实例，并注入模拟的仓库。"""
    return UserCRUD(repository=mock_repo)


# region 初始化测试 (Initialization Tests)


@pytest.mark.asyncio
async def test_initialize_storage_and_admin_user_admin_does_not_exist(
    user_crud_instance: UserCRUD, mock_repo: AsyncMock
):
    """测试首次初始化时，如果管理员用户不存在，则创建管理员用户。"""
    mock_repo.get_all.return_value = []  # 模拟系统中没有用户 (Simulate no users in system)
    # get_by_id 用于检查 settings.admin_username 是否已存在
    # (get_by_id used to check if settings.admin_username already exists)
    mock_repo.get_by_id.return_value = None

    # 模拟 create 方法，用于捕获传递给它的数据
    # (Mock create method to capture data passed to it)
    async def mock_create_effect(entity_type, data):
        return data  # 直接返回传入的数据，以便后续断言 (Return passed data directly for later assertion)

    mock_repo.create.side_effect = mock_create_effect

    await user_crud_instance.initialize_storage()

    mock_repo.init_storage_if_needed.assert_called_once_with(USER_ENTITY_TYPE, [])
    mock_repo.get_by_id.assert_called_once_with(
        USER_ENTITY_TYPE, settings.admin_username
    )

    mock_repo.create.assert_called_once()
    args, _ = mock_repo.create.call_args
    created_admin_data = args[
        1
    ]  # 第二个参数是 entity_data (Second argument is entity_data)

    assert created_admin_data["uid"] == settings.admin_username, (
        "创建的管理员UID不正确。"
    )
    assert verify_password(
        settings.default_admin_password_override, created_admin_data["hashed_password"]
    ), "管理员密码哈希不正确。"
    expected_admin_tags = {
        UserTag.ADMIN.value,
        UserTag.USER.value,
        UserTag.MANAGER.value,
    }
    assert set(created_admin_data["tags"]) == expected_admin_tags, (
        "管理员默认标签不正确。"
    )


@pytest.mark.asyncio
async def test_initialize_storage_admin_user_already_exists(
    user_crud_instance: UserCRUD, mock_repo: AsyncMock
):
    """测试初始化时，如果管理员用户已存在，则不重复创建。"""
    # 模拟管理员用户已存在 (Simulate admin user already exists)
    existing_admin_data = {
        "uid": settings.admin_username,
        "hashed_password": "some_existing_hash",
        "tags": [UserTag.ADMIN.value, UserTag.USER.value, UserTag.MANAGER.value],
    }
    mock_repo.get_all.return_value = [
        existing_admin_data
    ]  # 模拟系统中有用户 (Simulate users in system)
    mock_repo.get_by_id.return_value = (
        existing_admin_data  # 模拟 get_by_id 返回已存在的管理员
    )
    # (Simulate get_by_id returns existing admin)

    await user_crud_instance.initialize_storage()

    mock_repo.init_storage_if_needed.assert_called_once_with(USER_ENTITY_TYPE, [])
    mock_repo.get_by_id.assert_called_once_with(
        USER_ENTITY_TYPE, settings.admin_username
    )
    mock_repo.create.assert_not_called(), "管理员已存在时不应再次调用 create。"


# endregion

# region get_user_by_uid 测试 (get_user_by_uid Tests)


@pytest.mark.asyncio
async def test_get_user_by_uid_found(
    user_crud_instance: UserCRUD, mock_repo: AsyncMock
):
    """测试 get_user_by_uid 在用户存在时返回正确的 UserInDB 实例。"""
    user_data = {
        "uid": TEST_USER_UID,
        "hashed_password": "hashed_pw",
        "nickname": TEST_USER_NICKNAME,
        "email": TEST_USER_EMAIL,
        "qq": TEST_USER_QQ,
        "tags": [UserTag.USER.value],
    }
    mock_repo.get_by_id.return_value = user_data

    user = await user_crud_instance.get_user_by_uid(TEST_USER_UID)

    assert user is not None, "未能找到用户。"
    assert isinstance(user, UserInDB), "返回的不是 UserInDB 实例。"
    assert user.uid == TEST_USER_UID, "返回的用户UID不匹配。"
    assert user.nickname == TEST_USER_NICKNAME, "返回的用户昵称不匹配。"
    mock_repo.get_by_id.assert_called_once_with(USER_ENTITY_TYPE, TEST_USER_UID)


@pytest.mark.asyncio
async def test_get_user_by_uid_not_found(
    user_crud_instance: UserCRUD, mock_repo: AsyncMock
):
    """测试 get_user_by_uid 在用户不存在时返回 None。"""
    mock_repo.get_by_id.return_value = None

    user = await user_crud_instance.get_user_by_uid("unknown_user")

    assert user is None, "对不存在的用户，get_user_by_uid 未返回 None。"
    mock_repo.get_by_id.assert_called_once_with(USER_ENTITY_TYPE, "unknown_user")


# endregion

# region create_user 测试 (create_user Tests)


@pytest.mark.asyncio
async def test_create_user_success(
    user_crud_instance: UserCRUD, mock_repo: AsyncMock, mocker
):
    """测试 create_user 成功创建新用户。"""
    # 模拟 get_user_by_uid (内部调用 repository.get_by_id) 返回 None
    # (Simulate get_user_by_uid (internally calls repository.get_by_id) returns None)
    mocker.patch.object(user_crud_instance, "get_user_by_uid", return_value=None)

    user_create_payload = UserCreate(
        uid=TEST_USER_UID,
        password=TEST_USER_PASSWORD,
        nickname=TEST_USER_NICKNAME,
        email=TEST_USER_EMAIL,
        qq=TEST_USER_QQ,
    )

    # 模拟 repository.create 返回创建的用户数据
    # (Simulate repository.create returns created user data)
    async def mock_create_effect(entity_type, data):
        # 确保数据包含 UserInDB 所需的所有字段，特别是 hashed_password 和 tags
        # (Ensure data contains all fields required by UserInDB, especially hashed_password and tags)
        return {
            **data,
            "hashed_password": data.get(
                "hashed_password", "dummy_hash"
            ),  # create_user 应该已哈希
            # (create_user should have hashed)
            "tags": data.get(
                "tags", [UserTag.USER.value]
            ),  # create_user 应该已添加默认标签
            # (create_user should have added default tags)
        }

    mock_repo.create.side_effect = mock_create_effect

    created_user = await user_crud_instance.create_user(user_create_payload)

    assert created_user is not None, "创建用户失败。"
    assert isinstance(created_user, UserInDB), "返回的不是 UserInDB 实例。"
    assert created_user.uid == TEST_USER_UID, "创建的用户UID不正确。"
    assert created_user.nickname == TEST_USER_NICKNAME, "创建的用户昵称不正确。"
    assert UserTag.USER in created_user.tags, (
        "新用户缺少默认的 USER 标签。"
    )  # 检查枚举成员
    # (Check enum member)

    user_crud_instance.get_user_by_uid.assert_called_once_with(TEST_USER_UID)
    mock_repo.create.assert_called_once()
    created_data_args = mock_repo.create.call_args[0][
        1
    ]  # 获取传递给 repo.create 的数据
    # (Get data passed to repo.create)
    assert "password" not in created_data_args, "明文密码不应传递给仓库。"
    # (Plaintext password should not be passed to repository.)
    assert "hashed_password" in created_data_args, "哈希密码未传递给仓库。"
    # (Hashed password not passed to repository.)
    assert verify_password(TEST_USER_PASSWORD, created_data_args["hashed_password"]), (
        "密码哈希不正确。"
    )


@pytest.mark.asyncio
async def test_create_user_already_exists(
    user_crud_instance: UserCRUD, mock_repo: AsyncMock, mocker
):
    """测试 create_user 在用户已存在时返回 None 且不调用仓库创建。"""
    existing_user_data = UserInDB(
        uid=TEST_USER_UID,
        hashed_password="some_hash",
        nickname=TEST_USER_NICKNAME,
        tags=[UserTag.USER],
    )
    mocker.patch.object(
        user_crud_instance, "get_user_by_uid", return_value=existing_user_data
    )

    user_create_payload = UserCreate(uid=TEST_USER_UID, password="any_password")

    created_user = await user_crud_instance.create_user(user_create_payload)

    assert created_user is None, "用户已存在时，create_user 未返回 None。"
    user_crud_instance.get_user_by_uid.assert_called_once_with(TEST_USER_UID)
    mock_repo.create.assert_not_called(), "用户已存在时，不应调用 repository.create。"


# endregion


# region update_user_profile 测试 (update_user_profile Tests)
@pytest.mark.asyncio
async def test_update_user_profile_success(
    user_crud_instance: UserCRUD, mock_repo: AsyncMock, mocker
):
    """测试 update_user_profile 成功更新用户信息。"""
    original_user_data = {
        "uid": TEST_USER_UID,
        "nickname": "旧昵称",
        "email": "old@example.com",
        "qq": "111",
        "hashed_password": "pw",
        "tags": [UserTag.USER.value],
    }
    # get_user_by_uid 用于获取当前用户数据
    # (get_user_by_uid used to get current user data)
    mocker.patch.object(
        user_crud_instance,
        "get_user_by_uid",
        return_value=UserInDB(**original_user_data),
    )

    profile_update_payload = UserProfileUpdate(
        nickname="新昵称", email="new@example.com", qq="222"
    )

    # 模拟 repository.update 返回更新后的完整用户数据
    # (Simulate repository.update returns full updated user data)
    async def mock_update_effect(entity_type, uid, data_to_update):
        updated_data_copy = {**original_user_data, **data_to_update}
        return updated_data_copy

    mock_repo.update.side_effect = mock_update_effect

    updated_user = await user_crud_instance.update_user_profile(
        TEST_USER_UID, profile_update_payload
    )

    assert updated_user is not None, "更新用户资料失败。"
    assert isinstance(updated_user, UserInDB), "返回的不是 UserInDB 实例。"
    assert updated_user.nickname == "新昵称", "昵称未更新。"
    assert updated_user.email == "new@example.com", "邮箱未更新。"
    assert updated_user.qq == "222", "QQ未更新。"

    user_crud_instance.get_user_by_uid.assert_called_once_with(TEST_USER_UID)
    mock_repo.update.assert_called_once_with(
        USER_ENTITY_TYPE,
        TEST_USER_UID,
        profile_update_payload.model_dump(exclude_unset=True),  # 确保只传递有值的字段
        # (Ensure only fields with values are passed)
    )


@pytest.mark.asyncio
async def test_update_user_profile_no_changes(
    user_crud_instance: UserCRUD, mock_repo: AsyncMock, mocker
):
    """测试 update_user_profile 在没有实际更改时，不调用仓库更新并返回原用户。"""
    original_user_data = UserInDB(
        uid=TEST_USER_UID,
        nickname=TEST_USER_NICKNAME,
        email=TEST_USER_EMAIL,
        hashed_password="pw",
        tags=[UserTag.USER],
    )
    mocker.patch.object(
        user_crud_instance, "get_user_by_uid", return_value=original_user_data
    )

    empty_payload = UserProfileUpdate()  # 无任何更改 (No changes)

    user_after_update = await user_crud_instance.update_user_profile(
        TEST_USER_UID, empty_payload
    )

    assert user_after_update is not None
    assert (
        user_after_update.uid == original_user_data.uid
    )  # 确保返回的是原始用户数据（或其副本）
    # (Ensure original user data (or its copy) is returned)
    assert user_after_update.nickname == original_user_data.nickname
    mock_repo.update.assert_not_called(), "没有更改时不应调用 repository.update。"


# endregion


# region update_user_password 测试 (update_user_password Tests)
@pytest.mark.asyncio
async def test_update_user_password_success(
    user_crud_instance: UserCRUD, mock_repo: AsyncMock
):
    """测试 update_user_password 成功更新密码。"""
    new_hashed_password = "new_super_secret_hashed_password"

    # 模拟 repository.update 返回 True 或更新后的数据
    # (Simulate repository.update returns True or updated data)
    # UserCRUD.update_user_password 内部不依赖 get_user_by_id，直接调用 repo.update
    # (UserCRUD.update_user_password internally does not depend on get_user_by_id, directly calls repo.update)
    async def mock_update_effect(entity_type, uid, data_to_update):
        # 模拟返回更新后的用户字典 (Simulate returning updated user dict)
        return {
            "uid": uid,
            "hashed_password": data_to_update["hashed_password"],
            "tags": [UserTag.USER.value],
        }

    mock_repo.update.side_effect = (
        mock_update_effect  # 使得返回一个字典，即使CRUD只检查真值
    )
    # (Make it return a dict, even if CRUD only checks truthiness)

    success = await user_crud_instance.update_user_password(
        TEST_USER_UID, new_hashed_password
    )

    assert success is True, "更新密码操作失败。"
    mock_repo.update.assert_called_once_with(
        USER_ENTITY_TYPE, TEST_USER_UID, {"hashed_password": new_hashed_password}
    )


# endregion


# region admin_get_all_users 测试 (admin_get_all_users Tests)
@pytest.mark.asyncio
async def test_admin_get_all_users(user_crud_instance: UserCRUD, mock_repo: AsyncMock):
    """测试 admin_get_all_users 返回用户列表。"""
    users_data_from_repo = [
        {"uid": "user1", "hashed_password": "p1", "tags": [UserTag.USER.value]},
        {
            "uid": "user2",
            "hashed_password": "p2",
            "tags": [UserTag.ADMIN.value, UserTag.USER.value],
        },
    ]
    mock_repo.get_all.return_value = users_data_from_repo

    users_list = await user_crud_instance.admin_get_all_users(skip=0, limit=10)

    assert len(users_list) == 2, "返回的用户数量不正确。"
    assert isinstance(users_list[0], UserInDB), "列表元素不是 UserInDB 实例。"
    assert users_list[1].uid == "user2", "用户数据不正确。"
    mock_repo.get_all.assert_called_once_with(USER_ENTITY_TYPE, skip=0, limit=10)


# endregion

# region admin_update_user 测试 (admin_update_user Tests)


@pytest.mark.asyncio
async def test_admin_update_user_success_no_password(
    user_crud_instance: UserCRUD, mock_repo: AsyncMock, mocker
):
    """测试 admin_update_user 成功更新用户信息（不包括密码）。"""
    original_user_data = {
        "uid": TEST_USER_UID,
        "nickname": "旧昵称",
        "email": "old@example.com",
        "hashed_password": "old_hashed_pw",
        "tags": [UserTag.USER.value],
    }
    mocker.patch.object(
        user_crud_instance,
        "get_user_by_uid",
        return_value=UserInDB(**original_user_data),
    )

    admin_update_payload = AdminUserUpdate(
        nickname="管理员更新昵称",
        tags=[UserTag.USER, UserTag.EXAMINER],  # 标签应为枚举列表
        # (Tags should be list of enums)
    )

    # 模拟 repository.update
    # (Simulate repository.update)
    async def mock_admin_update_effect(entity_type, uid, data_to_update):
        # data_to_update 应该包含转换后的标签值 (data_to_update should contain converted tag values)
        return {**original_user_data, **data_to_update}

    mock_repo.update.side_effect = mock_admin_update_effect

    updated_user = await user_crud_instance.admin_update_user(
        TEST_USER_UID, admin_update_payload
    )

    assert updated_user is not None
    assert updated_user.nickname == "管理员更新昵称"
    assert UserTag.EXAMINER in updated_user.tags  # 检查枚举成员 (Check enum member)
    assert UserTag.USER in updated_user.tags  # 检查枚举成员 (Check enum member)

    mock_repo.update.assert_called_once()
    update_args = mock_repo.update.call_args[0][2]  # 第三个参数是 data_to_update
    # (Third argument is data_to_update)
    assert "new_password" not in update_args, "不应包含 new_password 字段。"
    assert "hashed_password" not in update_args, (
        "不应包含旧的 hashed_password，除非密码更新。"
    )
    # (Should not contain old hashed_password unless password update.)
    assert set(update_args["tags"]) == {
        UserTag.USER.value,
        UserTag.EXAMINER.value,
    }, "传递给仓库的标签值不正确。"


@pytest.mark.asyncio
async def test_admin_update_user_with_password_change(
    user_crud_instance: UserCRUD, mock_repo: AsyncMock, mocker
):
    """测试 admin_update_user 成功更新用户信息，包括密码。"""
    original_user_data = {
        "uid": TEST_USER_UID,
        "hashed_password": "old_pw",
        "tags": [UserTag.USER.value],
    }
    mocker.patch.object(
        user_crud_instance,
        "get_user_by_uid",
        return_value=UserInDB(**original_user_data),
    )

    new_plain_password = "NewPasswordByAdmin123"
    admin_update_payload_with_pw = AdminUserUpdate(
        new_password=new_plain_password, nickname="密码已更新昵称"
    )

    async def mock_admin_update_effect_pw(entity_type, uid, data_to_update):
        # 确保 data_to_update 包含 hashed_password
        # (Ensure data_to_update contains hashed_password)
        assert "hashed_password" in data_to_update
        assert verify_password(new_plain_password, data_to_update["hashed_password"])
        return {**original_user_data, **data_to_update, "nickname": "密码已更新昵称"}

    mock_repo.update.side_effect = mock_admin_update_effect_pw

    updated_user = await user_crud_instance.admin_update_user(
        TEST_USER_UID, admin_update_payload_with_pw
    )

    assert updated_user is not None
    assert updated_user.nickname == "密码已更新昵称"

    mock_repo.update.assert_called_once()
    update_args_pw = mock_repo.update.call_args[0][2]
    assert "new_password" not in update_args_pw, "new_password 字段不应直接传递给仓库。"
    # (new_password field should not be passed directly to repository.)
    assert "hashed_password" in update_args_pw, "hashed_password 未包含在更新数据中。"
    # (hashed_password not included in update data.)
    assert verify_password(new_plain_password, update_args_pw["hashed_password"]), (
        "新密码哈希不正确。"
    )


# endregion
