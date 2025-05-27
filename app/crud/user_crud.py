# region 模块导入
import json
import os
import secrets  # 用于生成首次admin的随机密码
import asyncio
import copy # 用于深拷贝
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any

# 使用相对导入
from ..models.user_models import UserInDB, UserCreate, UserTag, UserProfileUpdate, AdminUserUpdate
from ..core.security import get_password_hash, verify_password # 从security模块导入密码工具
from ..core.config import settings # 导入全局配置实例
# endregion

# region 全局变量与初始化
# 获取本模块的logger实例
_user_crud_logger = logging.getLogger(__name__)
# endregion

# region 用户数据管理类 (UserCRUD)
class UserCRUD:
    """
    用户数据管理类 (UserCRUD - Create, Read, Update, Delete)。
    负责用户账户数据的增删改查操作，数据持久化到 users_db.json 文件。
    用户数据在内存中也有一份副本，以提高读取性能。
    写操作会更新内存副本并异步持久化到文件。
    """

    def __init__(self, users_file_path: Optional[Path] = None):
        """
        初始化 UserCRUD。

        参数:
            users_file_path: 用户数据库JSON文件的路径。如果为None，则从全局配置获取。
        """
        if users_file_path is None:
            self.users_file_path: Path = settings.get_db_file_path("users")
        else:
            self.users_file_path: Path = users_file_path
        
        # 内存中的用户数据列表，每个元素是一个 UserInDB 对象的字典表示
        self.in_memory_users: List[Dict[str, Any]] = []
        self.users_file_lock = asyncio.Lock()  # 用于异步文件写入操作的锁
        
        self._load_users_from_file()  # 应用启动时加载用户数据
        self._initialize_admin_user_if_needed()  # 检查并初始化admin用户

    def _load_users_from_file(self) -> None:
        """
        从JSON文件加载用户数据到内存 `self.in_memory_users`。
        在 UserCRUD 实例化时调用。
        """
        try:
            if self.users_file_path.exists() and self.users_file_path.is_file():
                with open(self.users_file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        # 验证加载的数据是否符合 UserInDB 结构 (可选但推荐)
                        valid_users = []
                        for user_data_dict in data:
                            try:
                                # 尝试用Pydantic模型验证加载的每条用户数据
                                UserInDB(**user_data_dict) 
                                valid_users.append(user_data_dict)
                            except Exception as e_val:  # Pydantic ValidationError
                                _user_crud_logger.warning(
                                    f"加载用户数据时发现无效记录: {user_data_dict}, "
                                    f"错误: {e_val}"
                                )
                        self.in_memory_users = valid_users
                        _user_crud_logger.info(
                            f"成功从 '{self.users_file_path}' 加载 "
                            f"{len(self.in_memory_users)} 个有效用户账户到内存。"
                        )
                    else:
                        _user_crud_logger.warning(
                            f"用户数据库文件 '{self.users_file_path}' 内容不是一个列表，"
                            f"内存用户数据库初始化为空。"
                        )
                        self.in_memory_users = [] # 确保类型正确
            else:
                _user_crud_logger.info(
                    f"用户数据库文件 '{self.users_file_path}' 未找到，"
                    f"内存用户数据库初始化为空。"
                )
                self.in_memory_users = []
        except (json.JSONDecodeError, ValueError) as e: # ValueError for Pydantic
            _user_crud_logger.error(
                f"从 '{self.users_file_path}' 加载用户数据失败: {e}。"
                f"内存用户数据库初始化为空。"
            )
            self.in_memory_users = []
        except Exception as e: # 捕获其他潜在的IO错误等
            _user_crud_logger.error(
                f"从 '{self.users_file_path}' 加载用户数据时发生未知错误: {e}。",
                exc_info=True  # 记录堆栈跟踪信息
            )
            self.in_memory_users = []

    async def _persist_users_to_file_async(self) -> None:
        """异步地将内存中的用户数据 (`self.in_memory_users`) 持久化到JSON文件。"""
        async with self.users_file_lock:  # 确保文件写入操作的原子性
            try:
                # 创建数据的深拷贝以进行写入，防止在写入时被其他协程修改
                users_to_write = copy.deepcopy(self.in_memory_users)
                
                # 确保父目录存在
                self.users_file_path.parent.mkdir(parents=True, exist_ok=True)
                
                with open(self.users_file_path, "w", encoding="utf-8") as f:
                    json.dump(users_to_write, f, indent=4, ensure_ascii=False)
                _user_crud_logger.info(
                    f"成功将 {len(users_to_write)} 个用户账户持久化到 "
                    f"'{self.users_file_path}'。"
                )
            except Exception as e:
                _user_crud_logger.error(
                    f"持久化用户数据库到 '{self.users_file_path}' 失败: {e}",
                    exc_info=True
                )

    def _initialize_admin_user_if_needed(self) -> None:
        """
        如果用户数据库为空（通常是首次运行），则创建默认的admin用户。
        密码将优先从配置中读取，否则随机生成并记录到日志。
        """
        if not self.in_memory_users:  # 检查内存中的用户列表是否为空
            admin_uid = "admin"  # 默认管理员用户名
            
            # 优先从 settings.json (通过全局settings对象) 或 .env 获取初始密码
            # settings.default_admin_password_override 来自 settings.json
            # os.getenv("INITIAL_ADMIN_PASSWORD") 来自 .env
            initial_password = settings.default_admin_password_override or \
                               os.getenv("INITIAL_ADMIN_PASSWORD")

            if not initial_password:
                # 如果配置中都没有，则生成一个安全的随机密码
                initial_password = secrets.token_urlsafe(12)  # 生成一个12位的随机安全密码
                _user_crud_logger.warning( # 使用 logger 而不是 print
                    f"未在配置中找到初始Admin密码，已为用户 '{admin_uid}' 生成随机密码: "
                    f"'{initial_password}'。请妥善保管此密码并尽快修改！"
                )
            else:
                 _user_crud_logger.info(f"使用配置中的初始密码为用户 '{admin_uid}' 设置密码。")

            hashed_password = get_password_hash(initial_password)
            admin_user_data_dict = UserInDB(
                uid=admin_uid,
                hashed_password=hashed_password,
                nickname="管理员",
                email=f"{admin_uid}@{settings.app_domain}", # 示例邮箱
                tags=[UserTag.ADMIN, UserTag.USER]  # 赋予 admin 和 user 标签
            ).model_dump()  # 转换为字典以便存储
            
            self.in_memory_users.append(admin_user_data_dict)
            _user_crud_logger.info(f"已自动创建初始管理员账户 '{admin_uid}'。")
            
            # 立即尝试持久化这个初始管理员用户
            # 由于 _initialize_admin_user_if_needed 是在同步的 __init__ 中调用，
            # 而 _persist_users_to_file_async 是异步的，不能直接 await。
            # 解决方案：
            # 1. 标记需要保存，由后台任务统一保存（当前实现）。
            # 2. 如果必须立即保存，可以考虑在 __init__ 中创建一个临时事件循环来运行它，
            #    但这通常不推荐在库代码中做。
            # 3. 或者，使 __init__ 成为异步的（如果FastAPI支持异步依赖项初始化）。
            # 当前选择：依赖于后续的定期保存或关闭时保存。
            # 如果需要立即保存，可以像下面这样（但要注意上下文）：
            # try:
            #     asyncio.run(self._persist_users_to_file_async())
            # except RuntimeError: # 如果已经在运行的循环中
            #     asyncio.create_task(self._persist_users_to_file_async())
            _user_crud_logger.info("初始Admin用户将在下次持久化事件时保存到文件。")


    def get_user_by_uid(self, uid: str) -> Optional[UserInDB]:
        """
        根据UID从内存中获取用户数据，并返回UserInDB模型实例。

        参数:
            uid: 要查找的用户的唯一标识符。

        返回:
            UserInDB 实例如果找到用户，否则返回 None。
        """
        for user_data_dict in self.in_memory_users:
            if user_data_dict.get("uid") == uid:
                try:
                    return UserInDB(**user_data_dict)
                except Exception as e_val:  # Pydantic ValidationError
                    _user_crud_logger.error(
                        f"从内存加载用户 '{uid}' 数据时模型验证失败: {e_val}"
                    )
                    return None  # 数据损坏，视为找不到
        return None

    async def create_user(self, user_create_data: UserCreate) -> Optional[UserInDB]:
        """
        创建新用户。如果UID已存在则返回None。
        成功创建则将新用户数据持久化。

        参数:
            user_create_data: 包含新用户信息 (uid, password, 等) 的 UserCreate 模型实例。

        返回:
            创建成功的 UserInDB 模型实例，如果UID已存在或验证失败则返回 None。
        """
        if self.get_user_by_uid(user_create_data.uid):
            _user_crud_logger.warning(f"尝试创建已存在的用户UID: {user_create_data.uid}")
            return None  # 用户已存在
        
        hashed_password = get_password_hash(user_create_data.password)
        
        # 从 UserCreate 模型创建 UserInDB 所需的数据字典
        new_user_data_for_db = user_create_data.model_dump(exclude={"password"}) # 排除明文密码
        new_user_data_for_db["hashed_password"] = hashed_password
        new_user_data_for_db["tags"] = [tag.value for tag in UserTag.get_default_tags()] # 使用默认标签
        
        try:
            # 使用 UserInDB 模型验证并创建实例
            new_user_in_db = UserInDB(**new_user_data_for_db)
        except Exception as e_val:  # Pydantic ValidationError
            _user_crud_logger.error(
                f"创建用户 '{user_create_data.uid}' 时模型验证失败: {e_val}"
            )
            return None

        self.in_memory_users.append(new_user_in_db.model_dump()) # 存入内存的是字典
        await self._persist_users_to_file_async()  # 持久化用户列表
        _user_crud_logger.info(f"新用户 '{new_user_in_db.uid}' 创建成功。")
        return new_user_in_db # 返回Pydantic模型实例

    async def update_user_profile(
        self,
        user_uid: str,
        profile_update_data: UserProfileUpdate
    ) -> Optional[UserInDB]:
        """
        更新指定用户的个人资料（昵称、邮箱、QQ）。

        参数:
            user_uid: 要更新资料的用户的UID。
            profile_update_data: 包含要更新的个人资料字段的 UserProfileUpdate 模型实例。

        返回:
            更新后的 UserInDB 模型实例，如果用户未找到则返回 None。
        """
        user_found_index: Optional[int] = None
        current_user_data_dict: Optional[Dict[str, Any]] = None

        for i, user_data_dict_loop in enumerate(self.in_memory_users):
            if user_data_dict_loop.get("uid") == user_uid:
                user_found_index = i
                current_user_data_dict = user_data_dict_loop
                break
        
        if user_found_index is None or current_user_data_dict is None:
            _user_crud_logger.warning(f"尝试更新不存在的用户 '{user_uid}' 的个人资料。")
            return None

        # 使用 Pydantic 模型的 model_copy(update=...) 方法进行安全更新
        try:
            current_user_model = UserInDB(**current_user_data_dict)
            # exclude_unset=True确保只用实际提供的字段进行更新
            update_data_dict = profile_update_data.model_dump(exclude_unset=True)
            
            if not update_data_dict: # 如果没有提供任何要更新的字段
                _user_crud_logger.info(f"用户 '{user_uid}' 更新个人资料请求未包含任何更改。")
                return current_user_model # 返回当前用户数据

            updated_user_model = current_user_model.model_copy(update=update_data_dict)
            self.in_memory_users[user_found_index] = updated_user_model.model_dump() # 更新内存中的字典
            
            await self._persist_users_to_file_async()
            _user_crud_logger.info(f"用户 '{user_uid}' 的个人资料已更新。")
            return updated_user_model
        except Exception as e_val: # Pydantic ValidationError
            _user_crud_logger.error(f"更新用户 '{user_uid}' 个人资料时模型验证失败: {e_val}")
            return None # 或重新抛出异常

    async def update_user_password(self, user_uid: str, new_password_hashed: str) -> bool:
        """
        更新指定用户的密码（传入的是已哈希的新密码）。

        参数:
            user_uid: 要更新密码的用户的UID。
            new_password_hashed: 已哈希的新密码字符串。

        返回:
            True 如果密码更新成功，否则 False (例如用户未找到)。
        """
        user_found = False
        for user_data_dict in self.in_memory_users:
            if user_data_dict.get("uid") == user_uid:
                user_data_dict["hashed_password"] = new_password_hashed
                user_found = True
                break
        
        if user_found:
            await self._persist_users_to_file_async()
            _user_crud_logger.info(f"用户 '{user_uid}' 的密码已更新。")
            return True
        
        _user_crud_logger.warning(f"尝试更新不存在的用户 '{user_uid}' 的密码。")
        return False

    # --- Admin 操作 ---
    def admin_get_all_users(self, skip: int = 0, limit: int = 100) -> List[UserInDB]:
        """
        管理员获取所有用户列表（分页）。
        返回 UserInDB 模型实例列表。
        """
        # 返回内存数据的副本以防外部修改，并进行分页
        users_copy = copy.deepcopy(self.in_memory_users)
        # 可以添加排序逻辑，例如按UID排序
        # sorted_users = sorted(users_copy, key=lambda u: u.get("uid", ""))
        paginated_users_data = users_copy[skip : skip + limit]
        
        result_users = []
        for user_data in paginated_users_data:
            try:
                result_users.append(UserInDB(**user_data))
            except Exception as e_val: # Pydantic ValidationError
                 _user_crud_logger.warning(f"管理员获取用户列表时，用户数据 '{user_data.get('uid')}' 验证失败: {e_val}")
        return result_users

    async def admin_update_user(
        self,
        user_uid: str,
        update_data: AdminUserUpdate
    ) -> Optional[UserInDB]:
        """
        管理员更新指定用户信息（昵称、邮箱、QQ、标签、密码）。

        参数:
            user_uid: 要更新的用户的UID。
            update_data: 包含要更新字段的 AdminUserUpdate 模型实例。

        返回:
            更新后的 UserInDB 模型实例，如果用户未找到则返回 None。
        """
        user_found_index: Optional[int] = None
        current_user_data_dict: Optional[Dict[str, Any]] = None

        for i, user_data_dict_loop in enumerate(self.in_memory_users):
            if user_data_dict_loop.get("uid") == user_uid:
                user_found_index = i
                current_user_data_dict = user_data_dict_loop
                break
        
        if user_found_index is None or current_user_data_dict is None:
            _user_crud_logger.warning(f"[Admin] 尝试更新不存在的用户 '{user_uid}'。")
            return None

        try:
            current_user_model = UserInDB(**current_user_data_dict)
            
            # 准备要更新的数据字典，只包含已在 update_data 中设置的字段
            update_payload_dict = update_data.model_dump(exclude_unset=True)
            
            # 如果提供了新密码，则哈希它
            if "new_password" in update_payload_dict and update_payload_dict["new_password"]:
                update_payload_dict["hashed_password"] = get_password_hash(
                    update_payload_dict["new_password"]
                )
            update_payload_dict.pop("new_password", None) # 移除明文密码字段，无论是否提供

            # 如果提供了标签，确保它们是字符串列表 (UserTag.value)
            if "tags" in update_payload_dict and update_payload_dict["tags"] is not None:
                # AdminUserUpdate 中的 tags 已经是 List[UserTag]
                # model_dump() 会自动将其转换为字符串列表（如果UserTag是str枚举）
                # 如果需要，这里可以再次确认
                update_payload_dict["tags"] = [
                    tag.value if isinstance(tag, Enum) else str(tag) 
                    for tag in update_payload_dict["tags"]
                ]

            updated_user_model = current_user_model.model_copy(update=update_payload_dict)
            self.in_memory_users[user_found_index] = updated_user_model.model_dump()
            
            await self._persist_users_to_file_async()
            _user_crud_logger.info(f"[Admin] 用户 '{user_uid}' 的信息已更新。")
            return updated_user_model
        except Exception as e_val: # Pydantic ValidationError or other
            _user_crud_logger.error(f"[Admin] 更新用户 '{user_uid}' 信息时失败: {e_val}", exc_info=True)
            return None # 或重新抛出异常

# endregion
