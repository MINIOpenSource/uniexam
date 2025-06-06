# -*- coding: utf-8 -*-
"""
应用配置模块 (Application Configuration Module)。

此模块负责定义应用的配置模型 (使用 Pydantic)，加载来自 .env 文件、
JSON 配置文件 (settings.json) 的配置项，并提供全局可访问的配置实例。
它还包括动态生成 `DifficultyLevel` 枚举和设置日志记录的功能。

(This module is responsible for defining the application's configuration models (using Pydantic),
loading configuration items from .env files and JSON configuration files (settings.json),
and providing a globally accessible configuration instance. It also includes functionality
for dynamically generating the `DifficultyLevel` enum and setting up logging.)
"""

# region 模块导入 (Module Imports)
import asyncio  # 导入 asyncio 用于锁 (Import asyncio for locks)
import json
import logging  # 导入标准日志模块 (Import standard logging module)
import os
from enum import Enum  # 确保 Enum 被导入 (Ensure Enum is imported)
from pathlib import Path  # 用于处理文件路径 (For handling file paths)
from typing import Any, Dict, List, Optional

from dotenv import (
    load_dotenv,
)  # 从 .env 文件加载环境变量 (Load environment variables from .env file)
from pydantic import (
    BaseModel,
    Field,
    ValidationError,
    validator,  # field_validator for Pydantic v2, but validator is fine for v1-like usage too
)  # Pydantic 模型及验证工具

# 导入自定义枚举类型 (Import custom enum type)
from ..models.enums import AuthStatusCodeEnum, LogLevelEnum  # 导入认证状态码枚举

# endregion

# region 全局变量与初始化 (Global Variables & Initialization)
_config_module_logger = logging.getLogger(__name__)  # 获取本模块的日志记录器实例
# endregion

# region 动态难度级别枚举定义 (Dynamic DifficultyLevel Enum Definition)


def _get_difficulty_ids_from_index_json() -> List[str]:
    """
    从题库索引文件 (data/library/index.json) 读取并提取唯一的 'id' 值，
    用于动态创建 `DifficultyLevel` 枚举的成员。
    此函数在模块加载时被调用一次。

    (Reads and extracts unique 'id' values from the question bank index file
    (data/library/index.json) to dynamically create members for the `DifficultyLevel` enum.
    This function is called once when the module is loaded.)

    返回 (Returns):
        List[str]: 从索引文件中提取的有效且唯一的难度ID列表。
                   如果文件不存在、格式错误或未找到有效ID，则返回空列表。
                   (A list of valid and unique difficulty IDs extracted from the index file.
                    Returns an empty list if the file does not exist, is improperly formatted,
                    or no valid IDs are found.)
    """
    ids: List[str] = []
    try:
        # 获取当前工作目录，并构建数据和题库索引文件的路径
        # (Get current working directory and construct paths for data and library index files)
        base_data_path = Path.cwd() / "data"
        library_path_default = "library"  # 题库目录名 (Question library directory name)
        index_file_default = (
            "index.json"  # 题库索引文件名 (Question library index file name)
        )
        index_json_path = base_data_path / library_path_default / index_file_default

        if not index_json_path.exists():
            _config_module_logger.error(
                f"DifficultyLevel: 关键文件 '{index_json_path}' 未找到。"
                "无法从题库索引动态创建 DifficultyLevel 枚举。"
                "(DifficultyLevel: Critical file '{index_json_path}' not found. "
                "Cannot dynamically create DifficultyLevel enum from library index.)"
            )
            return []

        with open(index_json_path, "r", encoding="utf-8") as f:
            index_data = json.load(f)  # 加载JSON数据 (Load JSON data)

        if not isinstance(index_data, list):
            _config_module_logger.error(
                f"DifficultyLevel: 文件 '{index_json_path}' 的内容不是一个列表。"
                "期望的是一个包含题库元数据项的列表。"
                "(DifficultyLevel: Content of file '{index_json_path}' is not a list. "
                "Expected a list of question bank metadata items.)"
            )
            return []

        for item_idx, item in enumerate(index_data):
            if isinstance(item, dict) and "id" in item and isinstance(item["id"], str):
                item_id = item["id"]
                if not item_id:  # ID不应为空 (ID should not be empty)
                    _config_module_logger.warning(
                        f"DifficultyLevel: 文件 '{index_json_path}' 中索引 {item_idx} 处的项目 'id' 为空。已跳过。"
                        f"(DifficultyLevel: Item at index {item_idx} in '{index_json_path}' has an empty 'id'. Skipped.)"
                    )
                    continue
                if (
                    not item_id.isidentifier()
                ):  # ID必须是有效的Python标识符 (ID must be a valid Python identifier)
                    _config_module_logger.error(
                        f"DifficultyLevel: 文件 '{index_json_path}' 中的项目 'id' \"{item_id}\" 不是有效的Python标识符。不能用作枚举成员名。已跳过。"
                        f"(DifficultyLevel: Item 'id' \"{item_id}\" in '{index_json_path}' is not a valid Python identifier. Cannot be used as enum member name. Skipped.)"
                    )
                    continue
                if item_id not in ids:  # 保证ID的唯一性 (Ensure uniqueness of ID)
                    ids.append(item_id)
                else:  # 如果重复，记录警告并使用第一个 (If duplicate, log warning and use the first occurrence)
                    _config_module_logger.warning(
                        f"DifficultyLevel: 在 '{index_json_path}' 中发现重复的 'id' \"{item_id}\"。将使用首次出现的值。"
                        f"(DifficultyLevel: Duplicate 'id' \"{item_id}\" found in '{index_json_path}'. Using the first occurrence.)"
                    )
            else:
                _config_module_logger.warning(
                    f"DifficultyLevel: 文件 '{index_json_path}' 中索引 {item_idx} 处的项目无效或缺少有效的 'id' 字符串: {str(item)[:100]}..."
                    f"(DifficultyLevel: Item at index {item_idx} in '{index_json_path}' is invalid or lacks a valid 'id' string: {str(item)[:100]}...)"
                )

        if (
            not ids
        ):  # 如果最终没有收集到任何有效的ID (If no valid IDs were collected in the end)
            _config_module_logger.warning(
                f"DifficultyLevel: 未能在 '{index_json_path}' 中找到任何有效且唯一的 'id' 来创建 DifficultyLevel 枚举成员。"
                f"(DifficultyLevel: Failed to find any valid and unique 'id' in '{index_json_path}' to create DifficultyLevel enum members.)"
            )
        return ids
    except json.JSONDecodeError as e:
        _config_module_logger.error(
            f"DifficultyLevel: 从 '{index_json_path}' 解码JSON失败: {e}。无法创建动态 DifficultyLevel 枚举。"
            f"(DifficultyLevel: Failed to decode JSON from '{index_json_path}': {e}. Cannot create dynamic DifficultyLevel enum.)"
        )
        return []
    except IOError as e:
        _config_module_logger.error(
            f"DifficultyLevel: 读取 '{index_json_path}' 时发生IOError: {e}。无法创建动态 DifficultyLevel 枚举。"
            f"(DifficultyLevel: IOError occurred while reading '{index_json_path}': {e}. Cannot create dynamic DifficultyLevel enum.)"
        )
        return []
    except Exception as e:  # 捕获其他意外错误 (Catch other unexpected errors)
        _config_module_logger.error(
            f"DifficultyLevel: 为创建枚举读取 '{index_json_path}' 时发生未知错误: {e}",
            exc_info=True,  # 记录完整的异常信息 (Log full exception information)
        )
        return []


# 执行函数以获取难度ID (Execute function to get difficulty IDs)
_difficulty_member_ids = _get_difficulty_ids_from_index_json()

# 根据获取的ID动态创建DifficultyLevel枚举 (Dynamically create DifficultyLevel enum based on fetched IDs)
if not _difficulty_member_ids:
    # 如果未能加载任何难度级别，记录严重错误并使用一个回退的枚举
    # (If failed to load any difficulty levels, log critical error and use a fallback enum)
    _config_module_logger.critical(
        "严重错误：无法从 library/index.json 加载任何难度级别。"
        "应用功能将受到严重影响。"
        "正在使用包含单个 'unknown_difficulty' 成员的回退 DifficultyLevel。"
        "(CRITICAL ERROR: Cannot load any difficulty levels from library/index.json. "
        "Application functionality will be severely affected. "
        "Using a fallback DifficultyLevel with a single 'unknown_difficulty' member.)"
    )
    DifficultyLevel = Enum(
        "DifficultyLevel", {"unknown_difficulty": "unknown_difficulty"}, type=str
    )
else:
    # 使用获取到的ID创建枚举成员 (Use fetched IDs to create enum members)
    enum_members_map = {id_val: id_val for id_val in _difficulty_member_ids}
    DifficultyLevel = Enum("DifficultyLevel", enum_members_map, type=str)
    _config_module_logger.info(
        f"成功动态创建 DifficultyLevel 枚举，成员 (Successfully dynamically created DifficultyLevel enum, members): {list(DifficultyLevel.__members__.keys())}"
    )
# endregion

# region 认证状态码 (Authentication Status Codes)
# 使用 AuthStatusCodeEnum 枚举替代旧的字符串常量
# (Using AuthStatusCodeEnum enum to replace old string constants)
CODE_AUTH_SUCCESS: AuthStatusCodeEnum = AuthStatusCodeEnum.AUTH_SUCCESS
CODE_AUTH_WRONG: AuthStatusCodeEnum = AuthStatusCodeEnum.AUTH_WRONG_CREDENTIALS
CODE_AUTH_DUPLICATE: AuthStatusCodeEnum = AuthStatusCodeEnum.AUTH_DUPLICATE_UID
# endregion

# region 通用API状态码 (General API Status Codes)
# 这些状态码可被CRUD操作或其他API端点用作响应的一部分，以提供更具体的执行结果信息。
# (These status codes can be used by CRUD operations or other API endpoints as part of the response
#  to provide more specific information about the execution result.)
CODE_SUCCESS: int = 200  # 操作成功 (Operation successful)
CODE_NOT_FOUND: int = 404  # 资源未找到 (Resource not found)
CODE_INFO_OR_SPECIFIC_CONDITION: int = (
    299  # 自定义代码，用于表示非错误但需要特别指出的信息或特定条件
)
# (Custom code for informational/specific conditions, not errors)
# endregion

# region Pydantic 配置模型定义 (Pydantic Configuration Model Definitions)


class RateLimitConfig(BaseModel):
    """
    单个接口的速率限制配置模型。
    定义了在特定时间窗口内允许的最大请求次数。
    (Rate limit configuration model for a single interface.
    Defines the maximum number of requests allowed within a specific time window.)
    """

    limit: int = Field(
        description="在时间窗口内的最大请求次数 (Max requests in time window)"
    )
    window: int = Field(description="时间窗口大小（秒）(Time window size in seconds)")


class UserTypeRateLimits(BaseModel):
    """
    特定用户类型的速率限制配置集合。
    允许为不同类型的用户（如默认用户、受限用户）定义不同的接口速率限制。
    (Collection of rate limit configurations for specific user types.
    Allows defining different interface rate limits for different user types
    (e.g., default user, limited user).)
    """

    get_exam: RateLimitConfig = RateLimitConfig(
        limit=3,
        window=120,
        description="获取新试卷接口的速率限制 (Rate limit for get_exam endpoint)",
    )
    auth_attempts: RateLimitConfig = RateLimitConfig(
        limit=5,
        window=60,
        description="认证尝试（登录/注册）的速率限制 (Rate limit for auth attempts (login/signup))",
    )


class CloudflareIPsConfig(BaseModel):
    """
    Cloudflare IP地址范围获取相关的配置模型。
    用于从Cloudflare官方地址获取最新的IP范围，以便更准确地识别通过CF代理的客户端真实IP。
    (Configuration model for Cloudflare IP address range acquisition.
    Used to fetch the latest IP ranges from Cloudflare's official addresses to more
    accurately identify the real client IP for requests proxied through CF.)
    """

    v4_url: str = Field(
        "https://www.cloudflare.com/ips-v4/",
        description="Cloudflare IPv4地址范围列表URL (Cloudflare IPv4 address range list URL)",
    )
    v6_url: str = Field(
        "https://www.cloudflare.com/ips-v6/",
        description="Cloudflare IPv6地址范围列表URL (Cloudflare IPv6 address range list URL)",
    )
    fetch_interval_seconds: int = Field(
        86400,
        description="自动更新Cloudflare IP范围的时间间隔（秒），默认为24小时 (Auto-update interval in seconds, default 24h)",
    )


class DatabaseFilesConfig(BaseModel):
    """
    数据库文件路径配置模型（当使用基于文件的存储时，如JSON）。
    路径相对于 `data_dir` 定义。
    (Database file path configuration model (for file-based storage like JSON).
    Paths are relative to `data_dir`.)
    """

    papers: str = Field(
        "db.json", description="存储试卷数据的文件名 (Filename for paper data)"
    )
    users: str = Field(
        "users_db.json", description="存储用户数据的文件名 (Filename for user data)"
    )


class UserValidationConfig(BaseModel):
    """
    用户注册时的验证规则配置模型。
    定义了用户名和密码的长度及格式要求。
    (Validation rule configuration model for user registration.
    Defines length and format requirements for username and password.)
    """

    uid_min_len: int = Field(
        5, ge=1, description="用户名最小长度 (Min username length)"
    )
    uid_max_len: int = Field(16, description="用户名最大长度 (Max username length)")
    password_min_len: int = Field(
        8, ge=1, description="密码最小长度 (Min password length)"
    )
    password_max_len: int = Field(48, description="密码最大长度 (Max password length)")
    uid_regex: str = Field(
        r"^[a-z0-9_]+$",
        description="用户名的正则表达式，限制为小写字母、数字和下划线 (Regex for username: lowercase letters, numbers, underscore)",
    )


class Settings(BaseModel):
    """
    应用主配置模型 (Application Main Configuration Model)。
    聚合了应用的所有配置项，包括基本信息、安全设置、功能参数、数据库连接等。
    配置项可以从环境变量、JSON文件加载，并具有默认值。
    (Aggregates all application configuration items, including basic info, security settings,
    functional parameters, database connections, etc. Configuration items can be loaded
    from environment variables, JSON files, and have default values.)
    """

    app_name: str = Field("在线考试系统", description="应用名称 (Application name)")
    app_domain: str = Field(
        default_factory=lambda: os.getenv("APP_DOMAIN", "localhost"),
        description="应用主域名 (Main application domain)",
    )
    frontend_domain: str = Field(
        default_factory=lambda: os.getenv("FRONTEND_DOMAIN", "http://localhost:3000"),
        description="前端应用域名，用于CORS配置 (Frontend domain for CORS)",
    )
    listening_port: int = Field(
        default_factory=lambda: int(os.getenv("LISTENING_PORT", "17071")),
        description="应用监听端口 (Application listening port)",
    )

    default_admin_password_override: Optional[str] = Field(
        None,
        description="初始管理员密码（可选，通过环境变量设置，用于首次启动）(Initial admin password (optional, via env var for first run))",
    )
    token_expiry_hours: int = Field(
        24, ge=1, description="用户访问Token的有效小时数 (Token expiry in hours)"
    )
    token_length_bytes: int = Field(
        32,
        ge=16,
        le=64,
        description="生成的Token的字节长度（最终字符串长度为其2倍）(Byte length of generated token (string length is 2x))",
    )

    num_questions_per_paper_default: int = Field(
        50,
        ge=1,
        description="默认情况下，每份试卷包含的题目数量 (Default questions per paper)",
    )
    num_correct_choices_to_select: int = Field(
        1,
        ge=1,
        description="对于单选题或多选题，每道题应选取的正确选项数量（主要用于单选）(Number of correct choices to select (mainly for single choice))",
    )
    num_incorrect_choices_to_select: int = Field(
        3,
        ge=1,
        description="对于选择题，生成试卷时应选取的错误选项数量 (Number of incorrect choices for multiple choice questions)",
    )
    generated_code_length_bytes: int = Field(
        8,
        ge=4,
        le=16,
        description="用于生成选项ID和考试通过码的随机十六进制字符串的字节长度 (Byte length for random hex string for choice IDs & passcodes)",
    )

    passing_score_percentage: float = Field(
        60.0,
        ge=0,
        le=100,
        description="考试通过的百分制分数阈值 (Passing score percentage)",
    )
    db_persist_interval_seconds: int = Field(
        60,
        ge=10,
        description="内存数据定期持久化到文件的时间间隔（秒）(Interval for persisting in-memory data to file (seconds))",
    )

    rate_limits: Dict[str, UserTypeRateLimits] = Field(
        default_factory=lambda: {
            "default_user": UserTypeRateLimits(),
            "limited_user": UserTypeRateLimits(
                get_exam=RateLimitConfig(limit=1, window=300),
                auth_attempts=RateLimitConfig(limit=2, window=300),
            ),
        },
        description="不同用户类型的速率限制配置 (Rate limit configs for different user types)",
    )
    cloudflare_ips: CloudflareIPsConfig = Field(
        default_factory=CloudflareIPsConfig,
        description="Cloudflare IP获取配置 (Cloudflare IP fetching config)",
    )
    log_file_name: str = Field("exam_app.log", description="日志文件名 (Log filename)")
    log_level: LogLevelEnum = Field(  # 使用 LogLevelEnum 类型
        LogLevelEnum.INFO,  # Pydantic将自动使用枚举成员的值 (如 "INFO")
        description="应用日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL) (Application log level)",
    )

    database_files: DatabaseFilesConfig = Field(
        default_factory=DatabaseFilesConfig,
        description="JSON数据库文件名配置 (JSON database filename config)",
    )
    question_library_path: str = Field(
        "library",
        description="题库文件存放的相对路径 (相对于 data_dir) (Relative path for question library (to data_dir))",
    )
    question_library_index_file: str = Field(
        "index.json", description="题库索引文件名 (Question library index filename)"
    )
    user_config: UserValidationConfig = Field(
        default_factory=UserValidationConfig,
        description="用户验证规则配置 (User validation rule config)",
    )

    data_storage_type: str = Field(
        "json",
        description="数据存储类型 ('json', 'sqlite', 'postgres', 'mysql', 'redis') (Data storage type)",
    )

    POSTGRES_HOST: Optional[str] = Field(
        None, env="POSTGRES_HOST", description="PostgreSQL 主机名 (PostgreSQL host)"
    )
    POSTGRES_PORT: Optional[int] = Field(
        default_factory=lambda: int(os.getenv("POSTGRES_PORT", "5432")),
        env="POSTGRES_PORT",
        description="PostgreSQL 端口 (PostgreSQL port)",
    )
    POSTGRES_USER: Optional[str] = Field(
        None, env="POSTGRES_USER", description="PostgreSQL 用户名 (PostgreSQL user)"
    )
    POSTGRES_PASSWORD: Optional[str] = Field(
        None,
        env="POSTGRES_PASSWORD",
        description="PostgreSQL 密码 (PostgreSQL password)",
    )
    POSTGRES_DB: Optional[str] = Field(
        None,
        env="POSTGRES_DB",
        description="PostgreSQL 数据库名 (PostgreSQL database name)",
    )
    POSTGRES_DSN: Optional[str] = Field(
        None,
        env="POSTGRES_DSN",
        description="PostgreSQL DSN 连接字符串 (优先于单独参数) (PostgreSQL DSN (overrides individual params))",
    )

    MYSQL_HOST: Optional[str] = Field(
        None, env="MYSQL_HOST", description="MySQL 主机名 (MySQL host)"
    )
    MYSQL_PORT: Optional[int] = Field(
        default_factory=lambda: int(os.getenv("MYSQL_PORT", "3306")),
        env="MYSQL_PORT",
        description="MySQL 端口 (MySQL port)",
    )
    MYSQL_USER: Optional[str] = Field(
        None, env="MYSQL_USER", description="MySQL 用户名 (MySQL user)"
    )
    MYSQL_PASSWORD: Optional[str] = Field(
        None, env="MYSQL_PASSWORD", description="MySQL 密码 (MySQL password)"
    )
    MYSQL_DB: Optional[str] = Field(
        None, env="MYSQL_DB", description="MySQL 数据库名 (MySQL database name)"
    )

    REDIS_HOST: str = Field(
        os.getenv("REDIS_HOST", "localhost"), description="Redis 主机名 (Redis host)"
    )
    REDIS_PORT: int = Field(
        int(os.getenv("REDIS_PORT", "6379")), description="Redis 端口 (Redis port)"
    )
    REDIS_DB: int = Field(
        int(os.getenv("REDIS_DB", "0")),
        description="Redis 数据库编号 (Redis database number)",
    )
    REDIS_PASSWORD: Optional[str] = Field(
        os.getenv("REDIS_PASSWORD"),
        description="Redis 密码 (可选) (Redis password (optional))",
    )
    REDIS_URL: Optional[str] = Field(
        os.getenv("REDIS_URL"),
        description="Redis 连接 URL (优先于单独参数) (Redis connection URL (overrides individual params))",
    )

    SQLITE_DB_PATH: str = Field(
        os.getenv("SQLITE_DB_PATH", "data/app.db"),
        description="SQLite 数据库文件路径 (SQLite database file path)",
    )

    data_dir: Path = Field(
        default_factory=lambda: Path.cwd() / "data",
        exclude=True,  # 不包含在 model_dump 中，也不会从外部数据填充
        description="应用数据文件存放的基础目录 (Base directory for application data files)",
    )
    enable_uvicorn_access_log: bool = Field(
        False, description="是否启用Uvicorn的访问日志 (Enable Uvicorn access log)"
    )  # 新增配置项
    debug_mode: bool = Field(
        default_factory=lambda: os.getenv("DEBUG_MODE", "False").lower() == "true",
        description="是否启用调试模式 (主要用于控制uvicorn的reload) (Enable debug mode (mainly for uvicorn reload))",
    )

    @validator("user_config")
    def check_user_config_lengths(cls, v: UserValidationConfig) -> UserValidationConfig:
        """校验用户配置中最大长度不小于最小长度。(Validate user config: max length not less than min length.)"""
        if v.uid_max_len < v.uid_min_len:
            raise ValueError(
                "用户名字段 uid_max_len 不能小于 uid_min_len (uid_max_len cannot be less than uid_min_len)"
            )
        if v.password_max_len < v.password_min_len:
            raise ValueError(
                "密码字段 password_max_len 不能小于 password_min_len (password_max_len cannot be less than password_min_len)"
            )
        return v

    # Pydantic v2+ handles enum validation automatically when the type hint is LogLevelEnum.
    # The custom validator for log_level string format is no longer needed.
    # Pydantic will ensure the value is a valid member of LogLevelEnum.
    # If an invalid string is provided, Pydantic will raise a ValidationError.

    model_config = {
        "validate_assignment": True,  # 确保赋值时也进行验证 (Ensure validation on assignment)
        "extra": "ignore",  # 忽略未在模型中定义的额外字段 (Ignore extra fields not defined in the model)
    }

    def get_db_file_path(self, db_type: str) -> Path:
        """
        获取特定类型JSON数据库文件的完整路径。
        (Get the full path for a specific type of JSON database file.)

        参数 (Args):
            db_type (str): 数据库类型，如 'papers', 'users', 'settings'。
                           (Database type, e.g., 'papers', 'users', 'settings'.)
        返回 (Returns):
            Path: 对应数据库文件的完整路径对象。
                  (Full Path object for the corresponding database file.)
        异常 (Raises):
            ValueError: 如果请求的 `db_type` 未知。 (If the requested `db_type` is unknown.)
        """
        if db_type == "papers":
            return self.data_dir / self.database_files.papers
        elif db_type == "users":
            return self.data_dir / self.database_files.users
        elif (
            db_type == "settings"
        ):  # settings.json 通常直接在 data_dir 下 (settings.json usually directly under data_dir)
            return self.data_dir / "settings.json"
        raise ValueError(
            f"未知的数据库文件类型 (Unknown database file type): {db_type}"
        )

    def get_library_path(self) -> Path:
        """获取题库文件夹 (library) 的完整路径。(Get the full path of the question library folder.)"""
        return self.data_dir / self.question_library_path

    def get_library_index_path(self) -> Path:
        """获取题库索引文件 (index.json) 的完整路径。(Get the full path of the question library index file.)"""
        return self.get_library_path() / self.question_library_index_file


# endregion

# region 配置加载与管理逻辑 (Configuration Loading and Management Logic)
_settings_instance: Optional[Settings] = (
    None  # 全局单例配置实例 (Global singleton configuration instance)
)
_settings_file_lock = (
    asyncio.Lock()
)  # 用于异步更新配置文件的锁 (Async lock for updating config file)


def setup_logging(
    log_level_str: str,
    log_file_name: str,
    data_dir: Path,
    enable_uvicorn_access_log: bool,
):
    """
    配置应用范围的日志记录。会设置根日志记录器，添加控制台和文件处理器。
    (Configure application-wide logging. Sets up the root logger, adds console and file handlers.)

    参数 (Args):
        log_level_str (str): 日志级别字符串 (如 "INFO", "DEBUG")。 (Log level string (e.g., "INFO", "DEBUG").)
        log_file_name (str): 日志文件名。 (Log filename.)
        data_dir (Path): 数据目录，日志文件将存放在此目录下。 (Data directory where log file will be stored.)
        enable_uvicorn_access_log (bool): 是否启用Uvicorn访问日志的单独控制。
    """
    log_level = getattr(
        logging, log_level_str.upper(), logging.INFO
    )  # 获取对应的日志级别对象

    # --- 应用主日志记录器配置 (Application main logger configuration) ---
    app_root_logger = logging.getLogger()  # 获取根日志记录器 (Get root logger)
    app_root_logger.setLevel(log_level)  # 设置根日志级别 (Set root log level)

    # 移除已存在的处理器，防止重复记录日志 (尤其在重载时)
    # (Remove existing handlers to prevent duplicate logging (especially on reload))
    for handler in app_root_logger.handlers[:]:
        app_root_logger.removeHandler(handler)

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s"
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    app_root_logger.addHandler(console_handler)

    log_file_path = data_dir / log_file_name
    try:
        file_handler = logging.FileHandler(
            log_file_path, encoding="utf-8", mode="a"
        )  # 追加模式 (Append mode)
        file_handler.setFormatter(formatter)
        app_root_logger.addHandler(file_handler)
        _config_module_logger.info(
            f"应用日志将写入到 (Application logs will be written to): {log_file_path} (级别 (Level): {log_level_str})"
        )
    except Exception as e:
        _config_module_logger.error(
            f"无法配置日志文件处理器 '{log_file_path}' (Failed to configure log file handler): {e}"
        )

    # --- Uvicorn 日志记录器配置 (Uvicorn logger configuration) ---
    # 根据 enable_uvicorn_access_log 控制 Uvicorn 访问日志记录器的处理器
    uvicorn_access_logger = logging.getLogger("uvicorn.access")
    # 清理 uvicorn.access 可能已有的处理器，以避免重复或冲突
    for handler in uvicorn_access_logger.handlers[:]:
        uvicorn_access_logger.removeHandler(handler)
    uvicorn_access_logger.propagate = False  # 阻止 uvicorn.access 的日志传播到根记录器

    if enable_uvicorn_access_log:
        uvicorn_access_logger.setLevel(logging.INFO)  # Uvicorn访问日志通常是INFO级别
        # 可以为uvicorn.access添加与应用日志相同的处理器，或特定处理器
        uvicorn_access_logger.addHandler(console_handler)  # 例如，也输出到控制台
        if "file_handler" in locals():  # 如果文件处理器已成功创建
            uvicorn_access_logger.addHandler(file_handler)  # 也输出到主日志文件
        _config_module_logger.info(
            "Uvicorn 访问日志已启用并配置。 (Uvicorn access log enabled and configured.)"
        )
    else:
        uvicorn_access_logger.setLevel(
            logging.CRITICAL + 1
        )  # 设置一个非常高的级别来 фактически禁用它
        uvicorn_access_logger.addHandler(
            logging.NullHandler()
        )  # 添加一个NullHandler以防止 "no handlers" 警告
        _config_module_logger.info(
            "Uvicorn 访问日志已禁用。 (Uvicorn access log disabled.)"
        )

    # Uvicorn 错误日志 (uvicorn.error) 通常默认会传播到根记录器，并使用根记录器的配置
    # 如果需要特别处理 uvicorn.error，可以类似地获取其logger并配置。
    # uvicorn_error_logger = logging.getLogger("uvicorn.error")
    # uvicorn_error_logger.propagate = False # 如果要完全自定义处理


def _ensure_data_files_exist(settings_obj: Settings):
    """
    确保应用所需的数据文件和目录存在。如果不存在，则会尝试创建它们。
    此函数主要在 `load_settings` 首次加载配置后调用。
    (Ensures that data files and directories required by the application exist.
    If they don't exist, it attempts to create them. This function is primarily called
    by `load_settings` after the initial configuration load.)

    参数 (Args):
        settings_obj (Settings): 当前的应用配置实例。 (The current application configuration instance.)
    """
    try:
        settings_obj.data_dir.mkdir(
            parents=True, exist_ok=True
        )  # 创建主数据目录 (Create main data directory)

        # 确保用户和试卷的JSON数据库文件存在 (如果使用JSON存储)
        # (Ensure user and paper JSON database files exist (if using JSON storage))
        if settings_obj.data_storage_type == "json":
            users_db_path = settings_obj.get_db_file_path("users")
            if not users_db_path.exists():
                with open(users_db_path, "w", encoding="utf-8") as f:
                    json.dump([], f)  # 初始化为空列表 (Initialize as empty list)
                _config_module_logger.info(
                    f"提示：已在 '{users_db_path}' 创建空的用户数据库文件。"
                    f"(Hint: Created empty user database file at '{users_db_path}'.)"
                )

            papers_db_path = settings_obj.get_db_file_path("papers")
            if not papers_db_path.exists():
                with open(papers_db_path, "w", encoding="utf-8") as f:
                    json.dump([], f)
                _config_module_logger.info(
                    f"提示：已在 '{papers_db_path}' 创建空的试卷数据库文件。"
                    f"(Hint: Created empty paper database file at '{papers_db_path}'.)"
                )

        # 确保题库目录和索引文件存在 (Ensure question library directory and index file exist)
        library_path = settings_obj.get_library_path()
        library_path.mkdir(parents=True, exist_ok=True)
        library_index_path = settings_obj.get_library_index_path()
        if not library_index_path.exists():
            with open(library_index_path, "w", encoding="utf-8") as f:
                json.dump(
                    [], f, indent=4, ensure_ascii=False
                )  # 创建空的JSON列表 (Create empty JSON list)
            _config_module_logger.info(
                f"提示：已在 '{library_index_path}' 创建空的题库索引文件。"
                f"(Hint: Created empty question library index file at '{library_index_path}'.)"
            )

    except IOError as e:
        _config_module_logger.warning(
            f"创建数据文件或目录时发生IO错误 (IOError creating data files/dirs): {e}"
        )
    except Exception as e:
        _config_module_logger.warning(
            f"创建数据文件或目录时发生未知错误 (Unknown error creating data files/dirs): {e}"
        )


def load_settings() -> Settings:
    """
    加载应用配置 (Load application configuration)。
    配置加载顺序: Pydantic模型默认值 -> settings.json 文件 -> 环境变量。
    环境变量具有最高优先级。
    首次运行时，如果 settings.json 不存在，会根据默认值和环境变量生成一个。
    同时也会初始化日志配置和确保基本数据文件存在。

    (Configuration loading order: Pydantic model defaults -> settings.json file -> environment variables.
    Environment variables have the highest priority. On first run, if settings.json doesn't exist,
    one will be generated based on defaults and environment variables. Logging configuration
    and basic data file existence are also ensured.)

    返回 (Returns):
        Settings: 加载并验证后的全局配置实例。(Loaded and validated global configuration instance.)
    """
    global _settings_instance
    if (
        _settings_instance is not None
    ):  # 如果已加载，直接返回单例 (If already loaded, return singleton)
        return _settings_instance

    project_root = Path.cwd()  # 项目根目录 (Project root directory)
    data_dir = project_root / "data"  # 数据目录 (Data directory)
    settings_file = data_dir / "settings.json"  # 主配置文件路径 (Main config file path)

    load_dotenv(
        dotenv_path=project_root / ".env"
    )  # 加载 .env 文件中的环境变量 (Load .env file)

    json_config: Dict[str, Any] = (
        {}
    )  # 用于存放从 settings.json 读取的配置 (For config from settings.json)
    if settings_file.exists() and settings_file.is_file():
        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                json_config = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            _config_module_logger.warning(
                f"无法从 '{settings_file}' 加载JSON配置: {e}。将使用默认值和环境变量。"
                f"(Cannot load JSON config from '{settings_file}': {e}. Using defaults and env vars.)"
            )
    else:
        _config_module_logger.info(
            f"JSON配置文件 '{settings_file}' 未找到。将基于默认值和环境变量创建。"
            f"(JSON config file '{settings_file}' not found. Creating based on defaults and env vars.)"
        )

    # 从环境变量读取配置，Pydantic V2 会自动处理 `env` 标记的字段
    # 此处手动合并是为了更清晰地展示优先级和确保所有来源都被考虑
    # (Pydantic V2 handles fields marked with `env` automatically. Manual merging here for clarity.)

    # Pydantic模型字段的默认值是基础 (Pydantic model field defaults are the base)
    # json_config 会覆盖 Pydantic 默认值 (json_config overrides Pydantic defaults)
    # 环境变量会覆盖 json_config 和 Pydantic 默认值 (Environment variables override json_config and Pydantic defaults)

    # Pydantic V2 会自动从环境变量加载。我们只需合并 json_config。
    # 最终的初始化数据将是 json_config，Pydantic 在实例化时会应用环境变量（如果定义了 env）和默认值。
    final_init_data = {
        **json_config
    }  # Start with JSON config, Pydantic handles defaults and env vars

    try:
        parsed_settings = Settings(
            **final_init_data
        )  # Pydantic validates and loads env vars here
        _config_module_logger.info(
            "应用配置已成功加载和验证。 (Application config loaded and validated successfully.)"
        )
    except ValidationError as e:
        _config_module_logger.error(
            f"配置验证失败！将使用Pydantic模型的纯默认值。\n错误详情 (Config validation failed! Using pure Pydantic model defaults.\nError details): {e}",
            exc_info=True,
        )
        parsed_settings = (
            Settings()
        )  # 出错时回退到纯Pydantic默认值 (Fallback to pure Pydantic defaults on error)

    parsed_settings.data_dir = data_dir  # 动态设置 data_dir (Dynamically set data_dir)
    _ensure_data_files_exist(parsed_settings)

    if not settings_file.exists() or not json_config:  # 首次运行或settings.json为空时
        try:
            settings_file.parent.mkdir(parents=True, exist_ok=True)
            with open(settings_file, "w", encoding="utf-8") as f:
                # 写入配置到 settings.json，排除敏感或动态计算的字段
                # (Write config to settings.json, excluding sensitive or dynamically calculated fields)
                writable_settings_dict = parsed_settings.model_dump(
                    exclude={
                        "data_dir",
                        "default_admin_password_override",
                        # 数据库连接信息通常来自环境变量 (DB connection info usually from env vars)
                        "POSTGRES_HOST",
                        "POSTGRES_PORT",
                        "POSTGRES_USER",
                        "POSTGRES_PASSWORD",
                        "POSTGRES_DB",
                        "POSTGRES_DSN",
                        "MYSQL_HOST",
                        "MYSQL_PORT",
                        "MYSQL_USER",
                        "MYSQL_PASSWORD",
                        "MYSQL_DB",
                        "REDIS_HOST",
                        "REDIS_PORT",
                        "REDIS_DB",
                        "REDIS_PASSWORD",
                        "REDIS_URL",
                    }
                )
                json.dump(writable_settings_dict, f, indent=4, ensure_ascii=False)
            _config_module_logger.info(
                f"提示：已将基础配置写入 '{settings_file}'。请根据需要修改。"
                f"(Hint: Base config written to '{settings_file}'. Modify as needed.)"
            )
        except IOError as e:
            _config_module_logger.warning(
                f"无法写入初始配置到 '{settings_file}' (Cannot write initial config to '{settings_file}'): {e}"
            )

    setup_logging(
        parsed_settings.log_level.value,  # 传递枚举的值 (Pass the enum's value)
        parsed_settings.log_file_name,
        parsed_settings.data_dir,
        parsed_settings.enable_uvicorn_access_log,  # 传递Uvicorn访问日志启用标志
    )

    _settings_instance = parsed_settings
    return _settings_instance


async def update_and_persist_settings(new_settings_data: Dict[str, Any]) -> Settings:
    """
    异步更新并持久化应用的配置。
    它会读取当前的 settings.json，合并新数据，验证，然后写回 settings.json。
    全局的 `_settings_instance` 也会被更新。

    (Asynchronously updates and persists the application's configuration.
    It reads the current settings.json, merges new data, validates, and then writes
    back to settings.json. The global `_settings_instance` is also updated.)

    参数 (Args):
        new_settings_data (Dict[str, Any]): 一个包含要更新的配置项的字典。
                                           键应与 `Settings` 模型中的字段名匹配。
                                           (A dictionary containing configuration items to update.
                                            Keys should match field names in the `Settings` model.)
    返回 (Returns):
        Settings: 更新并重新加载后的全局配置实例。
                  (The updated and reloaded global configuration instance.)
    异常 (Raises):
        ValueError: 如果提供的配置数据无效。(If the provided configuration data is invalid.)
        IOError: 如果写入 settings.json 文件失败。(If writing to settings.json file fails.)
    """
    global _settings_instance
    if _settings_instance is None:
        load_settings()  # 确保配置已首次加载 (Ensure config is loaded first)
        assert _settings_instance is not None, "Settings instance should be loaded."

    async with (
        _settings_file_lock
    ):  # 使用异步锁确保文件操作的原子性 (Use async lock for atomic file ops)
        settings_file_path = _settings_instance.get_db_file_path("settings")
        current_json_config: Dict[str, Any] = {}
        if settings_file_path.exists():
            try:
                with open(settings_file_path, "r", encoding="utf-8") as f:
                    current_json_config = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                _config_module_logger.error(
                    f"读取当前 settings.json 失败: {e}。将基于空配置进行更新。 (Failed to read current settings.json: {e}. Updating based on empty config.)"
                )

        # 合并新数据到从文件加载的配置中 (Merge new data into config loaded from file)
        data_to_validate_and_persist = {**current_json_config, **new_settings_data}

        # Pydantic V2: 环境变量在实例化时自动处理，所以我们主要关注持久化到JSON的数据
        # (Pydantic V2: Env vars handled at instantiation, focus on data persisted to JSON)
        try:
            # 使用合并后的数据（json + new_settings）尝试创建新的Settings实例
            # Pydantic会自动从环境变量加载 env=True 的字段，并进行验证
            updated_settings_obj = Settings(**data_to_validate_and_persist)
        except ValidationError as e:
            _config_module_logger.error(
                f"更新配置时数据验证失败 (Data validation failed on update): {e}"
            )
            raise ValueError(
                f"提供的配置数据无效 (Provided config data invalid): {e}"
            ) from e

        # data_to_validate_and_persist 是我们希望写入JSON的内容（新设置已合并）
        # 但要排除那些只应来自环境变量的字段
        keys_to_exclude_from_json = [
            "data_dir",
            "default_admin_password_override",
            "POSTGRES_HOST",
            "POSTGRES_PORT",
            "POSTGRES_USER",
            "POSTGRES_PASSWORD",
            "POSTGRES_DB",
            "POSTGRES_DSN",
            "MYSQL_HOST",
            "MYSQL_PORT",
            "MYSQL_USER",
            "MYSQL_PASSWORD",
            "MYSQL_DB",
            "REDIS_HOST",
            "REDIS_PORT",
            "REDIS_DB",
            "REDIS_PASSWORD",
            "REDIS_URL",
        ]
        data_to_write_to_json = {
            k: v
            for k, v in data_to_validate_and_persist.items()
            if k not in keys_to_exclude_from_json
        }

        try:
            with open(settings_file_path, "w", encoding="utf-8") as f:
                json.dump(data_to_write_to_json, f, indent=4, ensure_ascii=False)

            _settings_instance = (
                updated_settings_obj  # 更新全局实例 (Update global instance)
            )
            _settings_instance.data_dir = Path.cwd() / "data"  # 确保 data_dir 正确

            # 比较时，需要比较枚举的值，因为 current_json_config["log_level"] 是字符串
            current_log_level_str = current_json_config.get("log_level")
            new_log_level_str = _settings_instance.log_level.value

            if (
                current_log_level_str != new_log_level_str
                or current_json_config.get("log_file_name")
                != _settings_instance.log_file_name
                or current_json_config.get("enable_uvicorn_access_log")
                != _settings_instance.enable_uvicorn_access_log
            ):
                setup_logging(
                    _settings_instance.log_level.value,  # 传递枚举的值
                    _settings_instance.log_file_name,
                    _settings_instance.data_dir,
                    _settings_instance.enable_uvicorn_access_log,
                )
            _config_module_logger.info(
                f"应用配置已成功更新并写入 '{settings_file_path}'。 (App config updated and written to '{settings_file_path}'.)"
            )
            return _settings_instance
        except IOError as e:
            _config_module_logger.error(
                f"更新配置文件 '{settings_file_path}' 失败 (Failed to update config file): {e}"
            )
            raise IOError(f"更新配置文件 '{settings_file_path}' 失败: {e}") from e


settings: Settings = (
    load_settings()
)  # 在模块加载时执行一次配置加载 (Load config once on module load)
# endregion

__all__ = [
    "settings",  # 全局配置实例 (Global settings instance)
    "Settings",  # Settings Pydantic 模型类 (Settings Pydantic model class)
    "DifficultyLevel",  # 难度级别枚举 (DifficultyLevel enum)
    "RateLimitConfig",  # 速率限制配置模型 (RateLimitConfig model)
    "UserTypeRateLimits",  # 用户类型速率限制模型 (UserTypeRateLimits model)
    "CloudflareIPsConfig",  # Cloudflare IP配置模型 (CloudflareIPsConfig model)
    "DatabaseFilesConfig",  # 数据库文件配置模型 (DatabaseFilesConfig model)
    "UserValidationConfig",  # 用户验证配置模型 (UserValidationConfig model)
    "setup_logging",  # 日志设置函数 (Logging setup function)
    "load_settings",  # 配置加载函数 (Settings loading function)
    "update_and_persist_settings",  # 配置更新函数 (Settings update function)
    "CODE_AUTH_SUCCESS",
    "CODE_AUTH_WRONG",
    "CODE_AUTH_DUPLICATE",  # 认证状态码 (Auth status codes)
    "CODE_SUCCESS",
    "CODE_NOT_FOUND",
    "CODE_INFO_OR_SPECIFIC_CONDITION",  # 通用API状态码 (General API status codes)
]

if __name__ == "__main__":
    # 此模块不应作为主脚本执行。它定义配置模型和加载逻辑，应由应用的其他部分导入。
    # (This module should not be executed as the main script. It defines configuration models
    #  and loading logic, and should be imported by other parts of the application.)
    _config_module_logger.info(
        f"模块 {__name__} 定义了应用配置，不应直接执行。它应被 FastAPI 应用导入。"
    )
    print(f"模块 {__name__} 定义了应用配置，不应直接执行。它应被 FastAPI 应用导入。")
