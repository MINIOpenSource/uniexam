# -*- coding: utf-8 -*-
"""
用户数据 CRUD (创建、读取、更新、删除) 操作模块。
(User Data CRUD (Create, Read, Update, Delete) Operations Module.)

此模块定义了 `UserCRUD` 类，它封装了与用户数据相关的持久化操作逻辑。
此类依赖于一个实现了 `IDataStorageRepository` 接口的存储库实例来与底层数据存储进行交互，
从而实现了数据访问逻辑与具体存储方式（如JSON文件、数据库等）的解耦。
(This module defines the `UserCRUD` class, which encapsulates the persistence operations
logic related to user data. This class relies on a repository instance that implements
the `IDataStorageRepository` interface to interact with the underlying data storage,
thus decoupling data access logic from specific storage methods (e.g., JSON files, databases).)
"""

# region 模块导入 (Module Imports)
import logging
import os
import secrets  # 用于生成首次admin的随机密码 (For generating random password for initial admin)
from enum import Enum  # 确保导入 Enum (Ensure Enum is imported)
from typing import List, Optional

from ..core.config import settings  # 导入全局配置实例 (Import global settings instance)
from ..core.interfaces import (
    IDataStorageRepository,
)  # 导入数据存储库接口 (Import data storage repository interface)
from ..core.security import (
    get_password_hash,
)  # 导入密码哈希工具 (Import password hashing utility)
from ..models.user_models import (  # 用户相关的Pydantic模型 (User-related Pydantic models)
    AdminUserUpdate,
    UserCreate,
    UserInDB,
    UserProfileUpdate,
    UserTag,
)

# endregion

# region 全局变量与初始化 (Global Variables & Initialization)
_user_crud_logger = logging.getLogger(
    __name__
)  # 本模块专用的logger实例 (Logger instance for this module)
USER_ENTITY_TYPE = "user"  # 定义此CRUD操作对应的实体类型字符串 (Entity type string for this CRUD operation)
# endregion


# region 用户数据管理类 (UserCRUD Class)
class UserCRUD:
    """
    用户数据管理类 (UserCRUD)。
    此类封装了所有与用户账户相关的创建、读取、更新和删除操作。
    它通过一个遵循 `IDataStorageRepository` 接口的存储库实例与数据持久化层交互。
    (User Data Management Class (UserCRUD).
    This class encapsulates all create, read, update, and delete operations related to user accounts.
    It interacts with the data persistence layer through a repository instance that adheres
    to the `IDataStorageRepository` interface.)
    """

    def __init__(self, repository: IDataStorageRepository):
        """
        初始化 UserCRUD。
        (Initializes UserCRUD.)

        参数 (Args):
            repository (IDataStorageRepository): 一个实现了 `IDataStorageRepository` 接口的存储库实例，
                                                 将用于所有用户数据的持久化操作。
                                                 (An instance of a repository implementing the `IDataStorageRepository`
                                                  interface, which will be used for all user data persistence operations.)
        """
        self.repository: IDataStorageRepository = repository
        _user_crud_logger.info(
            "UserCRUD 已初始化并注入存储库。 (UserCRUD initialized with injected repository.)"
        )

    async def initialize_storage(self) -> None:
        """
        初始化用户实体的存储。如果需要，这会创建相应的表或确保文件/集合存在。
        同时，它会尝试创建初始的管理员用户（如果尚不存在）。
        此方法应在应用启动序列中被调用一次。
        (Initializes storage for user entities. If needed, this creates the corresponding table
        or ensures the file/collection exists. It also attempts to create an initial admin user
        if one does not already exist. This method should be called once during the application
        startup sequence.)
        """
        await self.repository.init_storage_if_needed(USER_ENTITY_TYPE, initial_data=[])
        _user_crud_logger.info(
            f"实体类型 '{USER_ENTITY_TYPE}' 的存储已初始化（如果需要）。 (Storage for entity type '{USER_ENTITY_TYPE}' initialized if needed.)"
        )
        await self._initialize_admin_user_if_needed()

    async def _initialize_admin_user_if_needed(self) -> None:
        """
        检查是否存在任何用户，如果数据库为空，则创建默认的管理员用户。
        密码优先从配置读取，否则生成随机密码并记录。
        (Checks if any users exist; if the database is empty, creates a default admin user.
        Password is preferentially read from config, otherwise a random password is generated and logged.)
        """
        _user_crud_logger.debug(
            "正在检查是否需要初始化管理员用户... (Checking if admin user initialization is needed...)"
        )
        existing_users = await self.repository.get_all(USER_ENTITY_TYPE, limit=1)
        if not existing_users:
            admin_uid = "admin"
            existing_admin = await self.repository.get_by_id(
                USER_ENTITY_TYPE, admin_uid
            )
            if existing_admin:
                _user_crud_logger.info(
                    f"管理员用户 '{admin_uid}' 已存在。跳过创建。 (Admin user '{admin_uid}' already exists. Skipping creation.)"
                )
                return

            initial_password = settings.default_admin_password_override or os.getenv(
                "INITIAL_ADMIN_PASSWORD"
            )
            if not initial_password:
                initial_password = secrets.token_urlsafe(12)
                _user_crud_logger.warning(
                    f"配置中未指定初始Admin密码。已为用户 '{admin_uid}' 生成随机密码: '{initial_password}'。请务必记录并更改此密码！"
                    f"(Initial admin password not specified in config. Generated random password for user '{admin_uid}': '{initial_password}'. Please record and change this password!)"
                )
            else:
                _user_crud_logger.info(
                    f"将使用配置中提供的初始密码为用户 '{admin_uid}' 设置密码。 (Using initial password from config for user '{admin_uid}'.)"
                )

            hashed_password = get_password_hash(initial_password)
            admin_user_data_dict = UserInDB(
                uid=admin_uid,
                hashed_password=hashed_password,
                nickname="管理员 (Admin)",
                email=f"{admin_uid}@{settings.app_domain}",
                tags=[UserTag.ADMIN, UserTag.USER],
            ).model_dump()
            await self.repository.create(USER_ENTITY_TYPE, admin_user_data_dict)
            _user_crud_logger.info(
                f"已自动创建初始管理员账户 '{admin_uid}' 并持久化。 (Initial admin account '{admin_uid}' auto-created and persisted.)"
            )
        else:
            _user_crud_logger.debug(
                "数据库中已存在用户，跳过管理员初始化。 (Users already exist in DB, skipping admin initialization.)"
            )

    async def get_user_by_uid(self, uid: str) -> Optional[UserInDB]:
        """
        根据用户唯一标识符 (UID) 从存储库获取用户数据。
        (Retrieves user data from the repository by User ID (UID).)

        返回 (Returns): `UserInDB` 模型实例或 `None`。(UserInDB model instance or `None`.)
        """
        _user_crud_logger.debug(
            f"正在通过UID '{uid}' 获取用户... (Fetching user by UID '{uid}'...)"
        )
        user_data_dict = await self.repository.get_by_id(USER_ENTITY_TYPE, uid)
        if user_data_dict:
            try:
                return UserInDB(**user_data_dict)
            except Exception as e_val:
                _user_crud_logger.error(
                    f"从存储库加载用户 '{uid}' 的数据时，模型验证失败 (Model validation failed for user '{uid}'): {e_val}"
                )
                return None
        return None

    async def create_user(self, user_create_data: UserCreate) -> Optional[UserInDB]:
        """
        创建新用户。如果UID已存在，则失败。成功则持久化。
        (Creates a new user. Fails if UID exists. Persists on success.)

        返回 (Returns): `UserInDB` 模型实例或 `None`。(UserInDB model instance or `None`.)
        """
        _user_crud_logger.info(
            f"尝试创建用户UID: {user_create_data.uid} (Attempting to create user UID: {user_create_data.uid})"
        )
        if await self.get_user_by_uid(user_create_data.uid):
            _user_crud_logger.warning(
                f"尝试创建已存在的用户UID: {user_create_data.uid} (Attempted to create existing user UID: {user_create_data.uid})"
            )
            return None

        hashed_password = get_password_hash(user_create_data.password)
        new_user_data_for_db = user_create_data.model_dump(exclude={"password"})
        new_user_data_for_db.update(
            {
                "uid": user_create_data.uid,  # 确保主键 'uid' 存在 (Ensure primary key 'uid' exists)
                "hashed_password": hashed_password,
                "tags": [tag.value for tag in UserTag.get_default_tags()],
            }
        )
        try:
            validated_user_data = UserInDB(**new_user_data_for_db).model_dump()
        except Exception as e_val:
            _user_crud_logger.error(
                f"创建用户 '{user_create_data.uid}' 时，数据模型验证失败 (Data model validation failed for user '{user_create_data.uid}'): {e_val}"
            )
            return None

        created_user_dict = await self.repository.create(
            USER_ENTITY_TYPE, validated_user_data
        )
        _user_crud_logger.info(
            f"新用户 '{created_user_dict.get('uid')}' 创建成功。 (New user '{created_user_dict.get('uid')}' created successfully.)"
        )
        return UserInDB(**created_user_dict)

    async def update_user_profile(
        self, user_uid: str, profile_update_data: UserProfileUpdate
    ) -> Optional[UserInDB]:
        """
        更新指定用户的个人资料（例如昵称、邮箱、QQ号）。
        (Updates a specified user's profile (e.g., nickname, email, QQ number).)

        返回 (Returns): 更新后的 `UserInDB` 模型实例或 `None`。(Updated UserInDB model instance or `None`.)
        """
        update_dict = profile_update_data.model_dump(exclude_unset=True)
        if not update_dict:
            _user_crud_logger.info(
                f"用户 '{user_uid}' 的个人资料更新请求未包含任何有效更改。 (Profile update request for user '{user_uid}' contained no effective changes.)"
            )
            return await self.get_user_by_uid(user_uid)

        _user_crud_logger.info(
            f"正在更新用户 '{user_uid}' 的个人资料... (Updating profile for user '{user_uid}'...)"
        )
        updated_user_dict = await self.repository.update(
            USER_ENTITY_TYPE, user_uid, update_dict
        )
        if updated_user_dict:
            _user_crud_logger.info(
                f"用户 '{user_uid}' 的个人资料已成功更新。 (Profile for user '{user_uid}' updated successfully.)"
            )
            return UserInDB(**updated_user_dict)
        _user_crud_logger.warning(
            f"尝试更新用户 '{user_uid}' 的个人资料失败。 (Failed to update profile for user '{user_uid}'.)"
        )
        return None

    async def update_user_password(
        self, user_uid: str, new_password_hashed: str
    ) -> bool:
        """
        更新指定用户的密码。传入的密码应为已哈希处理过的新密码。
        (Updates a specified user's password. The provided password should be the new, already hashed password.)

        返回 (Returns): `True` 如果成功，否则 `False`。( `True` if successful, `False` otherwise.)
        """
        _user_crud_logger.info(
            f"正在更新用户 '{user_uid}' 的密码... (Updating password for user '{user_uid}'...)"
        )
        update_data = {"hashed_password": new_password_hashed}
        updated_user = await self.repository.update(
            USER_ENTITY_TYPE, user_uid, update_data
        )
        if updated_user:
            _user_crud_logger.info(
                f"用户 '{user_uid}' 的密码已成功更新。 (Password for user '{user_uid}' updated successfully.)"
            )
            return True
        _user_crud_logger.warning(
            f"尝试更新用户 '{user_uid}' 的密码失败。 (Failed to update password for user '{user_uid}'.)"
        )
        return False

    # --- Admin 管理员操作 (Admin Operations) ---
    async def admin_get_all_users(
        self, skip: int = 0, limit: int = 100
    ) -> List[UserInDB]:
        """
        管理员接口：获取所有用户列表（支持分页）。
        (Admin Interface: Gets a list of all users (supports pagination).)

        返回 (Returns): `UserInDB` 模型实例的列表。(List of UserInDB model instances.)
        """
        _user_crud_logger.debug(
            f"管理员请求用户列表，skip={skip}, limit={limit}。(Admin requesting user list, skip={skip}, limit={limit}.)"
        )
        users_data_list = await self.repository.get_all(
            USER_ENTITY_TYPE, skip=skip, limit=limit
        )
        result_users = []
        for user_data in users_data_list:
            try:
                result_users.append(UserInDB(**user_data))
            except Exception as e_val:
                _user_crud_logger.warning(
                    f"管理员获取用户列表时，用户数据 '{user_data.get('uid')}' 模型验证失败 (User data '{user_data.get('uid')}' validation failed for admin): {e_val}"
                )
        return result_users

    async def admin_update_user(
        self, user_uid: str, update_data: AdminUserUpdate
    ) -> Optional[UserInDB]:
        """
        管理员接口：更新指定用户信息，包括个人资料、标签和可选的密码重置。
        (Admin Interface: Updates specified user information, including profile, tags, and optional password reset.)

        返回 (Returns): 更新后的 `UserInDB` 模型实例或 `None`。(Updated UserInDB model instance or `None`.)
        """
        _user_crud_logger.info(
            f"[Admin] 尝试更新用户 '{user_uid}' 的信息... (Attempting to update info for user '{user_uid}'...)"
        )
        update_payload_dict = update_data.model_dump(exclude_unset=True)

        if (
            "new_password" in update_payload_dict
            and update_payload_dict["new_password"]
        ):  # 如果提供了新密码
            update_payload_dict["hashed_password"] = get_password_hash(
                update_payload_dict["new_password"]
            )
        update_payload_dict.pop("new_password", None)  # 移除明文密码字段

        if (
            "tags" in update_payload_dict and update_payload_dict["tags"] is not None
        ):  # 处理标签
            update_payload_dict["tags"] = [
                tag.value if isinstance(tag, Enum) else str(tag)
                for tag in update_payload_dict["tags"]
            ]

        if not update_payload_dict:
            _user_crud_logger.info(
                f"[Admin] 更新用户 '{user_uid}' 的请求未包含任何有效更改。 (Update request for user '{user_uid}' by admin contained no effective changes.)"
            )
            return await self.get_user_by_uid(user_uid)

        updated_user_dict = await self.repository.update(
            USER_ENTITY_TYPE, user_uid, update_payload_dict
        )
        if updated_user_dict:
            _user_crud_logger.info(
                f"[Admin] 用户 '{user_uid}' 的信息已成功更新。 (Info for user '{user_uid}' updated successfully by admin.)"
            )
            return UserInDB(**updated_user_dict)
        _user_crud_logger.warning(
            f"[Admin] 尝试更新用户 '{user_uid}' 失败。 (Failed to update user '{user_uid}' by admin.)"
        )
        return None

    async def cleanup_expired_tokens(self) -> None:  # 新增方法，用于清理过期Token
        """
        清理内存中（或配置的Token存储中）所有已过期的用户访问Token。
        此方法应由后台任务周期性调用。
        (Cleans up all expired user access tokens from memory (or configured token storage).
        This method should be called periodically by a background task.)
        """
        # 注意：当前的Token管理在 app.core.security 模块中，是内存方案。
        # 如果UserCRUD需要直接参与Token清理（例如，如果Token存储在与用户数据相同的DB中），
        # 则需要将Token管理逻辑移至此处或提供接口。
        # 目前，此方法是一个占位符，实际清理逻辑在 security.py 的 cleanup_expired_tokens_periodically。
        # 如果未来Token存储与用户数据紧密相关，则此方法应实现具体逻辑。
        _user_crud_logger.debug(
            "UserCRUD.cleanup_expired_tokens 被调用，但当前Token清理由 app.core.security 处理。 (UserCRUD.cleanup_expired_tokens called, but current token cleanup is handled by app.core.security.)"
        )
        # 调用 security 模块的清理函数 (如果需要 UserCRUD 主动触发)
        # from ..core.security import cleanup_expired_tokens_periodically as security_cleanup
        # await security_cleanup()
        pass


# endregion

__all__ = [
    "UserCRUD",  # 导出UserCRUD类 (Export UserCRUD class)
    "USER_ENTITY_TYPE",  # 导出用户实体类型常量 (Export user entity type constant)
]

if __name__ == "__main__":
    # 此模块不应作为主脚本执行。它定义了用户数据的CRUD操作类。
    # (This module should not be executed as the main script. It defines the CRUD operations class for user data.)
    _user_crud_logger.info(
        f"模块 {__name__} 提供了用户数据的CRUD操作类，不应直接执行。"
    )
    print(
        f"模块 {__name__} 提供了用户数据的CRUD操作类，不应直接执行。 (This module provides CRUD operations class for user data and should not be executed directly.)"
    )
