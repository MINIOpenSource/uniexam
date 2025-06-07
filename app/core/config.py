# -*- coding: utf-8 -*-
"""
应用配置模块 (Application Configuration Module)。

此模块负责定义应用的配置模型 (使用 Pydantic)，加载来自 .env 文件、
JSON 配置文件 (settings.json) 的配置项，并提供全局可访问的配置实例。
它还包括动态生成 `DifficultyLevel` 枚举和设置日志记录的功能。
"""
# [中文]: 此模块负责定义应用的配置模型 (使用 Pydantic)，加载来自 .env 文件、
# JSON 配置文件 (settings.json) 的配置项，并提供全局可访问的配置实例。
# 它还包括动态生成 `DifficultyLevel` 枚举和设置日志记录的功能。

# region 模块导入
import asyncio  # 导入 asyncio 用于锁
import json
import logging  # 导入标准日志模块
import logging.handlers  # 导入日志处理器模块
import os
from datetime import datetime, timezone  # 确保 timezone 也被导入 for JsonFormatter
from enum import Enum  # 确保 Enum 被导入
from pathlib import Path  # 用于处理文件路径
from typing import Any, Dict, List, Optional

from dotenv import (
    load_dotenv,
)  # 从 .env 文件加载环境变量
from pydantic import (
    BaseModel,
    Field,
    ValidationError,
    validator,  # Pydantic v2中推荐使用field_validator, 但validator在v1兼容模式下仍可使用
)  # Pydantic 模型及验证工具

# 导入自定义枚举类型
from ..models.enums import AuthStatusCodeEnum, LogLevelEnum  # 导入认证状态码枚举

# endregion 模块导入结束


# region 自定义JSON日志格式化器
class JsonFormatter(logging.Formatter):
    """
    自定义日志格式化器，将日志记录转换为JSON格式字符串。
    """

    def format(self, record: logging.LogRecord) -> str:
        """
        将 LogRecord 对象格式化为JSON字符串。
        """
        log_object: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),  # 获取格式化后的主消息
            "logger_name": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "thread_id": record.thread,
            "thread_name": record.threadName,
            "process_id": record.process,
        }

        # 添加异常信息
        if record.exc_info:
            # formatException 会返回包含换行符的字符串，对于单行JSON日志可能需要进一步处理
            # 例如替换换行符或将其作为数组元素。当前保持原样。
            log_object["exception"] = self.formatException(record.exc_info)

        # 添加通过 extra 传递的额外字段
        # 标准 LogRecord 属性列表，用于排除它们，只提取 "extra" 内容
        standard_record_attrs = {
            "args",
            "asctime",
            "created",
            "exc_info",
            "exc_text",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "message",
            "module",
            "msecs",
            "msg",
            "name",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "thread",
            "threadName",
            # Formatter可能添加的内部属性，以及我们已经明确记录的
            "currentframe",
            "taskName",
            "timestamp",
            "level",
            "logger_name",
            "function",
            "line",
            "thread_id",
            "thread_name",
            "process_id",
        }

        # 遍历record中所有非下划线开头的属性
        for key, value in record.__dict__.items():
            if not key.startswith("_") and key not in standard_record_attrs:
                log_object[key] = value

        return json.dumps(
            log_object, ensure_ascii=False, default=str
        )  # [中文]: default=str 处理无法序列化的对象


# endregion 自定义JSON日志格式化器结束

# region 全局变量与初始化
_config_module_logger = logging.getLogger(__name__)  # 获取本模块的日志记录器实例
# endregion 全局变量与初始化结束

# region 动态难度级别枚举定义


def _get_difficulty_ids_from_index_json() -> List[str]:
    """
    从题库索引文件 (data/library/index.json) 读取并提取唯一的 'id' 值，
    用于动态创建 `DifficultyLevel` 枚举的成员。
    此函数在模块加载时被调用一次。

    返回:
        List[str]: 从索引文件中提取的有效且唯一的难度ID列表。
                   如果文件不存在、格式错误或未找到有效ID，则返回空列表。
    """
    ids: List[str] = []
    try:
        # [中文]: 获取当前工作目录，并构建数据和题库索引文件的路径
        base_data_path = Path.cwd() / "data"
        library_path_default = "library"  # 题库目录名
        index_file_default = (
            "index.json"  # 题库索引文件名
        )
        index_json_path = base_data_path / library_path_default / index_file_default

        if not index_json_path.exists():
            _config_module_logger.error(
                f"DifficultyLevel: 关键文件 '{index_json_path}' 未找到。"
                "无法从题库索引动态创建 DifficultyLevel 枚举。"
            )
            return []

        with open(index_json_path, "r", encoding="utf-8") as f:
            index_data = json.load(f)  # [中文]: 加载JSON数据

        if not isinstance(index_data, list):
            _config_module_logger.error(
                f"DifficultyLevel: 文件 '{index_json_path}' 的内容不是一个列表。"
                "期望的是一个包含题库元数据项的列表。"
            )
            return []

        for item_idx, item in enumerate(index_data):
            if isinstance(item, dict) and "id" in item and isinstance(item["id"], str):
                item_id = item["id"]
                if not item_id:  # [中文]: ID不应为空
                    _config_module_logger.warning(
                        f"DifficultyLevel: 文件 '{index_json_path}' 中索引 {item_idx} 处的项目 'id' 为空。已跳过。"
                    )
                    continue
                if (
                    not item_id.isidentifier()
                ):  # [中文]: ID必须是有效的Python标识符
                    _config_module_logger.error(
                        f"DifficultyLevel: 文件 '{index_json_path}' 中的项目 'id' \"{item_id}\" 不是有效的Python标识符。不能用作枚举成员名。已跳过。"
                    )
                    continue
                if item_id not in ids:  # [中文]: 保证ID的唯一性
                    ids.append(item_id)
                else:  # [中文]: 如果重复，记录警告并使用第一个
                    _config_module_logger.warning(
                        f"DifficultyLevel: 在 '{index_json_path}' 中发现重复的 'id' \"{item_id}\"。将使用首次出现的值。"
                    )
            else:
                _config_module_logger.warning(
                    f"DifficultyLevel: 文件 '{index_json_path}' 中索引 {item_idx} 处的项目无效或缺少有效的 'id' 字符串: {str(item)[:100]}..."
                )

        if (
            not ids
        ):  # [中文]: 如果最终没有收集到任何有效的ID
            _config_module_logger.warning(
                f"DifficultyLevel: 未能在 '{index_json_path}' 中找到任何有效且唯一的 'id' 来创建 DifficultyLevel 枚举成员。"
            )
        return ids
    except json.JSONDecodeError as e:
        _config_module_logger.error(
            f"DifficultyLevel: 从 '{index_json_path}' 解码JSON失败: {e}。无法创建动态 DifficultyLevel 枚举。"
        )
        return []
    except IOError as e:
        _config_module_logger.error(
            f"DifficultyLevel: 读取 '{index_json_path}' 时发生IOError: {e}。无法创建动态 DifficultyLevel 枚举。"
        )
        return []
    except Exception as e:  # [中文]: 捕获其他意外错误
        _config_module_logger.error(
            f"DifficultyLevel: 为创建枚举读取 '{index_json_path}' 时发生未知错误: {e}",
            exc_info=True,  # [中文]: 记录完整的异常信息
        )
        return []


# [中文]: 执行函数以获取难度ID
_difficulty_member_ids = _get_difficulty_ids_from_index_json()

# [中文]: 根据获取的ID动态创建DifficultyLevel枚举
if not _difficulty_member_ids:
    # [中文]: 如果未能加载任何难度级别，记录严重错误并使用一个回退的枚举
    _config_module_logger.critical(
        "严重错误：无法从 library/index.json 加载任何难度级别。"
        "应用功能将受到严重影响。"
        "正在使用包含单个 'unknown_difficulty' 成员的回退 DifficultyLevel。"
    )
    DifficultyLevel = Enum(
        "DifficultyLevel", {"unknown_difficulty": "unknown_difficulty"}, type=str
    )
else:
    # [中文]: 使用获取到的ID创建枚举成员
    enum_members_map = {id_val: id_val for id_val in _difficulty_member_ids}
    DifficultyLevel = Enum("DifficultyLevel", enum_members_map, type=str)
    _config_module_logger.info(
        f"成功动态创建 DifficultyLevel 枚举，成员: {list(DifficultyLevel.__members__.keys())}"
    )
# endregion 动态难度级别枚举定义结束

# region 认证状态码
# [中文]: 使用 AuthStatusCodeEnum 枚举替代旧的字符串常量
CODE_AUTH_SUCCESS: AuthStatusCodeEnum = AuthStatusCodeEnum.AUTH_SUCCESS
CODE_AUTH_WRONG: AuthStatusCodeEnum = AuthStatusCodeEnum.AUTH_WRONG_CREDENTIALS
CODE_AUTH_DUPLICATE: AuthStatusCodeEnum = AuthStatusCodeEnum.AUTH_DUPLICATE_UID
# endregion 认证状态码结束

# region 通用API状态码
# [中文]: 这些状态码可被CRUD操作或其他API端点用作响应的一部分，以提供更具体的执行结果信息。
CODE_SUCCESS: int = 200  # [中文]: 操作成功
CODE_NOT_FOUND: int = 404  # [中文]: 资源未找到
CODE_INFO_OR_SPECIFIC_CONDITION: int = (
    299  # [中文]: 自定义代码，用于表示非错误但需要特别指出的信息或特定条件
)
# endregion 通用API状态码结束

# region Pydantic 配置模型定义


class RateLimitConfig(BaseModel):
    """
    单个接口的速率限制配置模型。
    定义了在特定时间窗口内允许的最大请求次数。
    """

    limit: int = Field(
        description="在时间窗口内的最大请求次数"
    )
    window: int = Field(description="时间窗口大小（秒）")


class UserTypeRateLimits(BaseModel):
    """
    特定用户类型的速率限制配置集合。
    允许为不同类型的用户（如默认用户、受限用户）定义不同的接口速率限制。
    """

    get_exam: RateLimitConfig = RateLimitConfig(
        limit=3,
        window=120,
        description="获取新试卷接口的速率限制",
    )
    auth_attempts: RateLimitConfig = RateLimitConfig(
        limit=5,
        window=60,
        description="认证尝试（登录/注册）的速率限制",
    )


class CloudflareIPsConfig(BaseModel):
    """
    Cloudflare IP地址范围获取相关的配置模型。
    用于从Cloudflare官方地址获取最新的IP范围，以便更准确地识别通过CF代理的客户端真实IP。
    """

    v4_url: str = Field(
        "https://www.cloudflare.com/ips-v4/",
        description="Cloudflare IPv4地址范围列表URL",
    )
    v6_url: str = Field(
        "https://www.cloudflare.com/ips-v6/",
        description="Cloudflare IPv6地址范围列表URL",
    )
    fetch_interval_seconds: int = Field(
        86400,
        description="自动更新Cloudflare IP范围的时间间隔（秒），默认为24小时",
    )


class DatabaseFilesConfig(BaseModel):
    """
    数据库文件路径配置模型（当使用基于文件的存储时，如JSON）。
    路径相对于 `data_dir` 定义。
    """

    papers: str = Field(
        "db.json", description="存储试卷数据的文件名"
    )
    users: str = Field(
        "users_db.json", description="存储用户数据的文件名"
    )


class UserValidationConfig(BaseModel):
    """
    用户注册时的验证规则配置模型。
    定义了用户名和密码的长度及格式要求。
    """

    uid_min_len: int = Field(
        5, ge=1, description="用户名最小长度"
    )
    uid_max_len: int = Field(16, description="用户名最大长度")
    password_min_len: int = Field(
        8, ge=1, description="密码最小长度"
    )
    password_max_len: int = Field(48, description="密码最大长度")
    uid_regex: str = Field(
        r"^[a-z0-9_]+$",
        description="用户名的正则表达式，限制为小写字母、数字和下划线",
    )


class Settings(BaseModel):
    """
    应用主配置模型。
    聚合了应用的所有配置项，包括基本信息、安全设置、功能参数、数据库连接等。
    配置项可以从环境变量、JSON文件加载，并具有默认值。
    """

    app_name: str = Field("在线考试系统", description="应用名称")
    app_domain: str = Field(
        default_factory=lambda: os.getenv("APP_DOMAIN", "localhost"),
        description="应用主域名",
    )
    frontend_domain: str = Field(
        default_factory=lambda: os.getenv("FRONTEND_DOMAIN", "http://localhost:3000"),
        description="前端应用域名，用于CORS配置",
    )
    listening_port: int = Field(
        default_factory=lambda: int(os.getenv("LISTENING_PORT", "17071")),
        description="应用监听端口",
    )

    default_admin_password_override: Optional[str] = Field(
        None,
        description="初始管理员密码（可选，通过环境变量设置，用于首次启动）",
    )
    token_expiry_hours: int = Field(
        24, ge=1, description="用户访问Token的有效小时数"
    )
    token_length_bytes: int = Field(
        32,
        ge=16,
        le=64,
        description="生成的Token的字节长度（最终字符串长度为其2倍）",
    )

    num_questions_per_paper_default: int = Field(
        50,
        ge=1,
        description="默认情况下，每份试卷包含的题目数量",
    )
    num_correct_choices_to_select: int = Field(
        1,
        ge=1,
        description="对于单选题或多选题，每道题应选取的正确选项数量（主要用于单选）",
    )
    num_incorrect_choices_to_select: int = Field(
        3,
        ge=1,
        description="对于选择题，生成试卷时应选取的错误选项数量",
    )
    generated_code_length_bytes: int = Field(
        8,
        ge=4,
        le=16,
        description="用于生成选项ID和考试通过码的随机十六进制字符串的字节长度",
    )

    passing_score_percentage: float = Field(
        60.0,
        ge=0,
        le=100,
        description="考试通过的百分制分数阈值",
    )
    db_persist_interval_seconds: int = Field(
        60,
        ge=10,
        description="内存数据定期持久化到文件的时间间隔（秒）",
    )

    rate_limits: Dict[str, UserTypeRateLimits] = Field(
        default_factory=lambda: {
            "default_user": UserTypeRateLimits(),
            "limited_user": UserTypeRateLimits(
                get_exam=RateLimitConfig(limit=1, window=300),
                auth_attempts=RateLimitConfig(limit=2, window=300),
            ),
        },
        description="不同用户类型的速率限制配置",
    )
    cloudflare_ips: CloudflareIPsConfig = Field(
        default_factory=CloudflareIPsConfig,
        description="Cloudflare IP获取配置",
    )
    log_file_name: str = Field("exam_app.log", description="日志文件名")
    log_level: LogLevelEnum = Field(  # [中文]: 使用 LogLevelEnum 类型
        LogLevelEnum.INFO,  # [中文]: Pydantic将自动使用枚举成员的值 (如 "INFO")
        description="应用日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )
    audit_log_file_path: str = Field(
        "data/logs/audit.log", description="审计日志文件路径"
    )

    database_files: DatabaseFilesConfig = Field(
        default_factory=DatabaseFilesConfig,
        description="JSON数据库文件名配置",
    )
    question_library_path: str = Field(
        "library",
        description="题库文件存放的相对路径 (相对于 data_dir)",
    )
    question_library_index_file: str = Field(
        "index.json", description="题库索引文件名"
    )
    user_config: UserValidationConfig = Field(
        default_factory=UserValidationConfig,
        description="用户验证规则配置",
    )

    data_storage_type: str = Field(
        "json",
        description="数据存储类型 ('json', 'sqlite', 'postgres', 'mysql', 'redis')",
    )

    POSTGRES_HOST: Optional[str] = Field(
        None, env="POSTGRES_HOST", description="PostgreSQL 主机名"
    )
    POSTGRES_PORT: Optional[int] = Field(
        default_factory=lambda: int(os.getenv("POSTGRES_PORT", "5432")),
        env="POSTGRES_PORT",
        description="PostgreSQL 端口",
    )
    POSTGRES_USER: Optional[str] = Field(
        None, env="POSTGRES_USER", description="PostgreSQL 用户名"
    )
    POSTGRES_PASSWORD: Optional[str] = Field(
        None,
        env="POSTGRES_PASSWORD",
        description="PostgreSQL 密码",
    )
    POSTGRES_DB: Optional[str] = Field(
        None,
        env="POSTGRES_DB",
        description="PostgreSQL 数据库名",
    )
    POSTGRES_DSN: Optional[str] = Field(
        None,
        env="POSTGRES_DSN",
        description="PostgreSQL DSN 连接字符串 (优先于单独参数)",
    )

    MYSQL_HOST: Optional[str] = Field(
        None, env="MYSQL_HOST", description="MySQL 主机名"
    )
    MYSQL_PORT: Optional[int] = Field(
        default_factory=lambda: int(os.getenv("MYSQL_PORT", "3306")),
        env="MYSQL_PORT",
        description="MySQL 端口",
    )
    MYSQL_USER: Optional[str] = Field(
        None, env="MYSQL_USER", description="MySQL 用户名"
    )
    MYSQL_PASSWORD: Optional[str] = Field(
        None, env="MYSQL_PASSWORD", description="MySQL 密码"
    )
    MYSQL_DB: Optional[str] = Field(
        None, env="MYSQL_DB", description="MySQL 数据库名"
    )

    REDIS_HOST: str = Field(
        os.getenv("REDIS_HOST", "localhost"), description="Redis 主机名"
    )
    REDIS_PORT: int = Field(
        int(os.getenv("REDIS_PORT", "6379")), description="Redis 端口"
    )
    REDIS_DB: int = Field(
        int(os.getenv("REDIS_DB", "0")),
        description="Redis 数据库编号",
    )
    REDIS_PASSWORD: Optional[str] = Field(
        os.getenv("REDIS_PASSWORD"),
        description="Redis 密码 (可选)",
    )
    REDIS_URL: Optional[str] = Field(
        os.getenv("REDIS_URL"),
        description="Redis 连接 URL (优先于单独参数)",
    )

    SQLITE_DB_PATH: str = Field(
        os.getenv("SQLITE_DB_PATH", "data/app.db"),
        description="SQLite 数据库文件路径",
    )

    data_dir: Path = Field(
        default_factory=lambda: Path.cwd() / "data",
        exclude=True,  # [中文]: 不包含在 model_dump 中，也不会从外部数据填充
        description="应用数据文件存放的基础目录",
    )
    enable_uvicorn_access_log: bool = Field(
        False, description="是否启用Uvicorn的访问日志"
    )  # [中文]: 新增配置项
    debug_mode: bool = Field(
        default_factory=lambda: os.getenv("DEBUG_MODE", "False").lower() == "true",
        description="是否启用调试模式 (主要用于控制uvicorn的reload)",
    )

    @validator("user_config")
    def check_user_config_lengths(cls, v: UserValidationConfig) -> UserValidationConfig:
        """校验用户配置中最大长度不小于最小长度。"""
        if v.uid_max_len < v.uid_min_len:
            raise ValueError(
                "用户名字段 uid_max_len 不能小于 uid_min_len"
            )
        if v.password_max_len < v.password_min_len:
            raise ValueError(
                "密码字段 password_max_len 不能小于 password_min_len"
            )
        return v

    # [中文]: Pydantic v2+ 自动处理枚举验证（当类型提示为 LogLevelEnum 时）。
    # [中文]: 不再需要自定义的 log_level 字符串格式验证器。
    # [中文]: Pydantic 会确保值是 LogLevelEnum 的有效成员。
    # [中文]: 如果提供了无效字符串，Pydantic 会引发 ValidationError。

    model_config = {
        "validate_assignment": True,  # [中文]: 确保赋值时也进行验证
        "extra": "ignore",  # [中文]: 忽略未在模型中定义的额外字段
    }

    def get_db_file_path(self, db_type: str) -> Path:
        """
        获取特定类型JSON数据库文件的完整路径。

        参数:
            db_type (str): 数据库类型，如 'papers', 'users', 'settings'。
        返回:
            Path: 对应数据库文件的完整路径对象。
        异常:
            ValueError: 如果请求的 `db_type` 未知。
        """
        if db_type == "papers":
            return self.data_dir / self.database_files.papers
        elif db_type == "users":
            return self.data_dir / self.database_files.users
        elif (
            db_type == "settings"
        ):  # [中文]: settings.json 通常直接在 data_dir 下
            return self.data_dir / "settings.json"
        raise ValueError(
            f"未知的数据库文件类型: {db_type}"
        )

    def get_library_path(self) -> Path:
        """获取题库文件夹 (library) 的完整路径。"""
        return self.data_dir / self.question_library_path

    def get_library_index_path(self) -> Path:
        """获取题库索引文件 (index.json) 的完整路径。"""
        return self.get_library_path() / self.question_library_index_file


# endregion Pydantic 配置模型定义结束

# region 配置加载与管理逻辑
_settings_instance: Optional[Settings] = (
    None  # [中文]: 全局单例配置实例
)
_settings_file_lock = (
    asyncio.Lock()
)  # [中文]: 用于异步更新配置文件的锁


def setup_logging(
    log_level_str: str,
    log_file_name: str,
    data_dir: Path,
    enable_uvicorn_access_log: bool,
):
    """
    配置应用范围的日志记录。会设置根日志记录器，添加控制台和文件处理器。

    参数:
        log_level_str (str): 日志级别字符串 (如 "INFO", "DEBUG")。
        log_file_name (str): 日志文件名。
        data_dir (Path): 数据目录，日志文件将存放在此目录下。
        enable_uvicorn_access_log (bool): 是否启用Uvicorn访问日志的单独控制。
    """
    log_level = getattr(
        logging, log_level_str.upper(), logging.INFO
    )  # [中文]: 获取对应的日志级别对象

    # --- 应用主日志记录器配置 ---
    app_root_logger = logging.getLogger()  # [中文]: 获取根日志记录器
    app_root_logger.setLevel(log_level)  # [中文]: 设置根日志级别

    # [中文]: 移除已存在的处理器，防止重复记录日志 (尤其在重载时)
    for handler in app_root_logger.handlers[:]:
        app_root_logger.removeHandler(handler)

    # [中文]: 保留原有的文本格式化器给控制台
    text_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s"
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(text_formatter)
    app_root_logger.addHandler(console_handler)

    # [中文]: 为文件处理器创建并设置JSON格式化器
    log_file_path = data_dir / log_file_name
    try:
        json_formatter = JsonFormatter()  # [中文]: 使用自定义的JsonFormatter
        # [中文]: 使用 TimedRotatingFileHandler 实现日志按天轮转，保留7天备份
        file_handler = logging.handlers.TimedRotatingFileHandler(
            filename=log_file_path,
            when="midnight",  # [中文]: 每天午夜轮转
            interval=1,  # [中文]: 每天一次
            backupCount=7,  # [中文]: 保留7个备份文件
            encoding="utf-8",
            utc=True,  # [中文]: 使用UTC时间进行轮转
            delay=False,  # [中文]: False: 在创建处理器时即打开文件
        )
        file_handler.setFormatter(json_formatter)  # [中文]: 应用JsonFormatter
        app_root_logger.addHandler(file_handler)
        # [中文]: 初始日志消息仍将使用根记录器的控制台格式，直到文件处理器被添加。
        _config_module_logger.info(  # [中文]: 此消息本身会通过 console_handler 以文本格式输出
            f"应用日志将以JSON格式按天轮转写入到: {log_file_path} (级别: {log_level_str})"
        )
    except Exception as e:
        _config_module_logger.error(
            f"无法配置带轮转的JSON日志文件处理器 '{log_file_path}': {e}"
        )

    # --- Uvicorn 日志记录器配置 ---
    # [中文]: 根据 enable_uvicorn_access_log 控制 Uvicorn 访问日志记录器的处理器
    uvicorn_access_logger = logging.getLogger("uvicorn.access")
    # [中文]: 清理 uvicorn.access 可能已有的处理器，以避免重复或冲突
    for handler in uvicorn_access_logger.handlers[:]:
        uvicorn_access_logger.removeHandler(handler)
    uvicorn_access_logger.propagate = False  # [中文]: 阻止 uvicorn.access 的日志传播到根记录器

    if enable_uvicorn_access_log:
        uvicorn_access_logger.setLevel(logging.INFO)  # [中文]: Uvicorn访问日志通常是INFO级别
        # [中文]: 可以为uvicorn.access添加与应用日志相同的处理器，或特定处理器
        uvicorn_access_logger.addHandler(console_handler)  # [中文]: 例如，也输出到控制台
        if "file_handler" in locals():  # [中文]: 如果文件处理器已成功创建
            uvicorn_access_logger.addHandler(file_handler)  # [中文]: 也输出到主日志文件
        _config_module_logger.info(
            "Uvicorn 访问日志已启用并配置。"
        )
    else:
        uvicorn_access_logger.setLevel(
            logging.CRITICAL + 1
        )  # [中文]: 设置一个非常高的级别来 фактически禁用它
        uvicorn_access_logger.addHandler(
            logging.NullHandler()
        )  # [中文]: 添加一个NullHandler以防止 "no handlers" 警告
        _config_module_logger.info(
            "Uvicorn 访问日志已禁用。"
        )

    # [中文]: Uvicorn 错误日志 (uvicorn.error) 通常默认会传播到根记录器，并使用根记录器的配置
    # [中文]: 如果需要特别处理 uvicorn.error，可以类似地获取其logger并配置。
    # uvicorn_error_logger = logging.getLogger("uvicorn.error")
    # uvicorn_error_logger.propagate = False # [中文]: 如果要完全自定义处理


def _ensure_data_files_exist(settings_obj: Settings):
    """
    确保应用所需的数据文件和目录存在。如果不存在，则会尝试创建它们。
    此函数主要在 `load_settings` 首次加载配置后调用。

    参数:
        settings_obj (Settings): 当前的应用配置实例。
    """
    try:
        settings_obj.data_dir.mkdir(
            parents=True, exist_ok=True
        )  # [中文]: 创建主数据目录

        # [中文]: 确保用户和试卷的JSON数据库文件存在 (如果使用JSON存储)
        if settings_obj.data_storage_type == "json":
            users_db_path = settings_obj.get_db_file_path("users")
            if not users_db_path.exists():
                with open(users_db_path, "w", encoding="utf-8") as f:
                    json.dump([], f)  # [中文]: 初始化为空列表
                _config_module_logger.info(
                    f"提示：已在 '{users_db_path}' 创建空的用户数据库文件。"
                )

            papers_db_path = settings_obj.get_db_file_path("papers")
            if not papers_db_path.exists():
                with open(papers_db_path, "w", encoding="utf-8") as f:
                    json.dump([], f)
                _config_module_logger.info(
                    f"提示：已在 '{papers_db_path}' 创建空的试卷数据库文件。"
                )

        # [中文]: 确保题库目录和索引文件存在
        library_path = settings_obj.get_library_path()
        library_path.mkdir(parents=True, exist_ok=True)
        library_index_path = settings_obj.get_library_index_path()
        if not library_index_path.exists():
            with open(library_index_path, "w", encoding="utf-8") as f:
                json.dump(
                    [], f, indent=4, ensure_ascii=False
                )  # [中文]: 创建空的JSON列表
            _config_module_logger.info(
                f"提示：已在 '{library_index_path}' 创建空的题库索引文件。"
            )

    except IOError as e:
        _config_module_logger.warning(
            f"创建数据文件或目录时发生IO错误: {e}"
        )
    except Exception as e:
        _config_module_logger.warning(
            f"创建数据文件或目录时发生未知错误: {e}"
        )


def load_settings() -> Settings:
    """
    加载应用配置。
    配置加载顺序: Pydantic模型默认值 -> settings.json 文件 -> 环境变量。
    环境变量具有最高优先级。
    首次运行时，如果 settings.json 不存在，会根据默认值和环境变量生成一个。
    同时也会初始化日志配置和确保基本数据文件存在。

    返回:
        Settings: 加载并验证后的全局配置实例。
    """
    global _settings_instance
    if (
        _settings_instance is not None
    ):  # [中文]: 如果已加载，直接返回单例
        return _settings_instance

    project_root = Path.cwd()  # [中文]: 项目根目录
    data_dir = project_root / "data"  # [中文]: 数据目录
    settings_file = data_dir / "settings.json"  # [中文]: 主配置文件路径

    load_dotenv(
        dotenv_path=project_root / ".env"
    )  # [中文]: 加载 .env 文件中的环境变量

    json_config: Dict[
        str, Any
    ] = {}  # [中文]: 用于存放从 settings.json 读取的配置
    if settings_file.exists() and settings_file.is_file():
        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                json_config = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            _config_module_logger.warning(
                f"无法从 '{settings_file}' 加载JSON配置: {e}。将使用默认值和环境变量。"
            )
    else:
        _config_module_logger.info(
            f"JSON配置文件 '{settings_file}' 未找到。将基于默认值和环境变量创建。"
        )

    # [中文]: 从环境变量读取配置，Pydantic V2 会自动处理 `env` 标记的字段
    # [中文]: 此处手动合并是为了更清晰地展示优先级和确保所有来源都被考虑

    # [中文]: Pydantic模型字段的默认值是基础
    # [中文]: json_config 会覆盖 Pydantic 默认值
    # [中文]: 环境变量会覆盖 json_config 和 Pydantic 默认值

    # [中文]: Pydantic V2 会自动从环境变量加载。我们只需合并 json_config。
    # [中文]: 最终的初始化数据将是 json_config，Pydantic 在实例化时会应用环境变量（如果定义了 env）和默认值。
    final_init_data = {
        **json_config
    }  # [中文]: 以JSON配置开始, Pydantic处理默认值和环境变量

    try:
        parsed_settings = Settings(
            **final_init_data
        )  # [中文]: Pydantic 在此处验证并加载环境变量
        _config_module_logger.info(
            "应用配置已成功加载和验证。"
        )
    except ValidationError as e:
        _config_module_logger.error(
            f"配置验证失败！将使用Pydantic模型的纯默认值。\n错误详情: {e}",
            exc_info=True,
        )
        parsed_settings = (
            Settings()
        )  # [中文]: 出错时回退到纯Pydantic默认值

    parsed_settings.data_dir = data_dir  # [中文]: 动态设置 data_dir
    _ensure_data_files_exist(parsed_settings)

    if not settings_file.exists() or not json_config:  # [中文]: 首次运行或settings.json为空时
        try:
            settings_file.parent.mkdir(parents=True, exist_ok=True)
            with open(settings_file, "w", encoding="utf-8") as f:
                # [中文]: 写入配置到 settings.json，排除敏感或动态计算的字段
                writable_settings_dict = parsed_settings.model_dump(
                    exclude={
                        "data_dir",
                        "default_admin_password_override",
                        # [中文]: 数据库连接信息通常来自环境变量
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
            )
        except IOError as e:
            _config_module_logger.warning(
                f"无法写入初始配置到 '{settings_file}': {e}"
            )

    setup_logging(
        parsed_settings.log_level.value,  # [中文]: 传递枚举的值
        parsed_settings.log_file_name,
        parsed_settings.data_dir,
        parsed_settings.enable_uvicorn_access_log,  # [中文]: 传递Uvicorn访问日志启用标志
    )

    _settings_instance = parsed_settings
    return _settings_instance


async def update_and_persist_settings(new_settings_data: Dict[str, Any]) -> Settings:
    """
    异步更新并持久化应用的配置。
    它会读取当前的 settings.json，合并新数据，验证，然后写回 settings.json。
    全局的 `_settings_instance` 也会被更新。

    参数:
        new_settings_data (Dict[str, Any]): 一个包含要更新的配置项的字典。
                                           键应与 `Settings` 模型中的字段名匹配。
    返回:
        Settings: 更新并重新加载后的全局配置实例。
    异常:
        ValueError: 如果提供的配置数据无效。
        IOError: 如果写入 settings.json 文件失败。
    """
    global _settings_instance
    if _settings_instance is None:
        load_settings()  # [中文]: 确保配置已首次加载
        assert _settings_instance is not None, "Settings instance should be loaded."

    async with (
        _settings_file_lock
    ):  # [中文]: 使用异步锁确保文件操作的原子性
        settings_file_path = _settings_instance.get_db_file_path("settings")
        current_json_config: Dict[str, Any] = {}
        if settings_file_path.exists():
            try:
                with open(settings_file_path, "r", encoding="utf-8") as f:
                    current_json_config = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                _config_module_logger.error(
                    f"读取当前 settings.json 失败: {e}。将基于空配置进行更新。"
                )

        # [中文]: 合并新数据到从文件加载的配置中
        data_to_validate_and_persist = {**current_json_config, **new_settings_data}

        # [中文]: Pydantic V2: 环境变量在实例化时自动处理，所以我们主要关注持久化到JSON的数据
        try:
            # [中文]: 使用合并后的数据（json + new_settings）尝试创建新的Settings实例
            # [中文]: Pydantic会自动从环境变量加载 env=True 的字段，并进行验证
            updated_settings_obj = Settings(**data_to_validate_and_persist)
        except ValidationError as e:
            _config_module_logger.error(
                f"更新配置时数据验证失败: {e}"
            )
            raise ValueError(
                f"提供的配置数据无效: {e}"
            ) from e

        # [中文]: data_to_validate_and_persist 是我们希望写入JSON的内容（新设置已合并）
        # [中文]: 但要排除那些只应来自环境变量的字段
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
                updated_settings_obj  # [中文]: 更新全局实例
            )
            _settings_instance.data_dir = Path.cwd() / "data"  # [中文]: 确保 data_dir 正确

            # [中文]: 比较时，需要比较枚举的值，因为 current_json_config["log_level"] 是字符串
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
                    _settings_instance.log_level.value,  # [中文]: 传递枚举的值
                    _settings_instance.log_file_name,
                    _settings_instance.data_dir,
                    _settings_instance.enable_uvicorn_access_log,
                )
            _config_module_logger.info(
                f"应用配置已成功更新并写入 '{settings_file_path}'。"
            )
            return _settings_instance
        except IOError as e:
            _config_module_logger.error(
                f"更新配置文件 '{settings_file_path}' 失败: {e}"
            )
            raise IOError(f"更新配置文件 '{settings_file_path}' 失败: {e}") from e


settings: Settings = (
    load_settings()
)  # [中文]: 在模块加载时执行一次配置加载
# endregion 配置加载与管理逻辑结束

__all__ = [
    "settings",  # [中文]: 全局配置实例
    "Settings",  # [中文]: Settings Pydantic 模型类
    "DifficultyLevel",  # [中文]: 难度级别枚举
    "RateLimitConfig",  # [中文]: 速率限制配置模型
    "UserTypeRateLimits",  # [中文]: 用户类型速率限制模型
    "CloudflareIPsConfig",  # [中文]: Cloudflare IP配置模型
    "DatabaseFilesConfig",  # [中文]: 数据库文件配置模型
    "UserValidationConfig",  # [中文]: 用户验证配置模型
    "setup_logging",  # [中文]: 日志设置函数
    "load_settings",  # [中文]: 配置加载函数
    "update_and_persist_settings",  # [中文]: 配置更新函数
    "CODE_AUTH_SUCCESS",
    "CODE_AUTH_WRONG",
    "CODE_AUTH_DUPLICATE",  # [中文]: 认证状态码
    "CODE_SUCCESS",
    "CODE_NOT_FOUND",
    "CODE_INFO_OR_SPECIFIC_CONDITION",  # [中文]: 通用API状态码
]

if __name__ == "__main__":
    # [中文]: 此模块不应作为主脚本执行。它定义配置模型和加载逻辑，应由应用的其他部分导入。
    _config_module_logger.info(
        f"模块 {__name__} 定义了应用配置，不应直接执行。它应被 FastAPI 应用导入。"
    )
    print(f"模块 {__name__} 定义了应用配置，不应直接执行。它应被 FastAPI 应用导入。")
