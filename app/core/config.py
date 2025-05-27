# region 模块导入
import json
import os
from pathlib import Path # 用于处理文件路径
from typing import Dict, Any, Optional, List
import logging # 导入标准日志模块
import asyncio # 导入 asyncio 用于锁
from enum import Enum # Ensure Enum is imported

from dotenv import load_dotenv # 从 .env 文件加载环境变量
from pydantic import BaseModel, Field, validator, ValidationError
# endregion

_config_module_logger = logging.getLogger(__name__)

# region Dynamic DifficultyLevel Enum Definition
def _get_difficulty_ids_from_index_json() -> List[str]:
    """
    Reads the library index.json file and extracts unique 'id' values
    to be used for DifficultyLevel Enum members.
    This function is called once at module load time.
    """
    ids: List[str] = []
    try:
        base_data_path = Path.cwd() / "data"
        library_path_default = "library"
        index_file_default = "index.json"
        index_json_path = base_data_path / library_path_default / index_file_default

        if not index_json_path.exists():
            _config_module_logger.error(
                f"DifficultyLevel: Crucial file '{index_json_path}' not found. "
                "Cannot create dynamic DifficultyLevel enum from library index."
            )
            return []

        with open(index_json_path, "r", encoding="utf-8") as f:
            index_data = json.load(f)

        if not isinstance(index_data, list):
            _config_module_logger.error(
                f"DifficultyLevel: Content of '{index_json_path}' is not a list. "
                "Expected a list of library metadata items."
            )
            return []

        for item_idx, item in enumerate(index_data):
            if isinstance(item, dict) and "id" in item and isinstance(item["id"], str):
                item_id = item["id"]
                if not item_id:
                    _config_module_logger.warning(f"DifficultyLevel: Item at index {item_idx} in '{index_json_path}' has an empty 'id'. Skipping.")
                    continue
                if not item_id.isidentifier():
                    _config_module_logger.error(f"DifficultyLevel: Item 'id' \"{item_id}\" from '{index_json_path}' is not a valid Python identifier. Cannot use as Enum member name. Skipping.")
                    continue
                if item_id not in ids: ids.append(item_id)
                else: _config_module_logger.warning(f"DifficultyLevel: Duplicate 'id' \"{item_id}\" found in '{index_json_path}'. Using the first occurrence.")
            else: _config_module_logger.warning(f"DifficultyLevel: Invalid item or missing/invalid 'id' string at index {item_idx} in '{index_json_path}': {str(item)[:100]}...")
        if not ids: _config_module_logger.warning(f"DifficultyLevel: No valid and unique 'id's found in '{index_json_path}' to create DifficultyLevel enum members.")
        return ids
    except json.JSONDecodeError as e:
        _config_module_logger.error(f"DifficultyLevel: Failed to decode JSON from '{index_json_path}': {e}. Cannot create dynamic DifficultyLevel enum.")
        return []
    except IOError as e:
        _config_module_logger.error(f"DifficultyLevel: IOError reading '{index_json_path}': {e}. Cannot create dynamic DifficultyLevel enum.")
        return []
    except Exception as e:
        _config_module_logger.error(f"DifficultyLevel: Unexpected error while reading '{index_json_path}' for enum creation: {e}", exc_info=True)
        return []

_difficulty_member_ids = _get_difficulty_ids_from_index_json()

if not _difficulty_member_ids:
    _config_module_logger.critical(
        "CRITICAL: No difficulty levels could be loaded from library index.json. "
        "Application functionality will be severely impaired. "
        "Using a fallback DifficultyLevel with a single 'unknown_difficulty' member."
    )
    DifficultyLevel = Enum('DifficultyLevel', {'unknown_difficulty': 'unknown_difficulty'}, type=str)
else:
    enum_members_map = {id_val: id_val for id_val in _difficulty_member_ids}
    DifficultyLevel = Enum('DifficultyLevel', enum_members_map, type=str)
    _config_module_logger.info(f"Successfully created dynamic DifficultyLevel enum with members: {list(DifficultyLevel.__members__.keys())}")
# endregion

# region Authentication Status Codes
CODE_AUTH_SUCCESS: str = "SUCCESS"
CODE_AUTH_WRONG: str = "WRONG"
CODE_AUTH_DUPLICATE: str = "DUPLICATE"

# General API Status Codes (can be used by CRUD operations)
CODE_SUCCESS: int = 200  # Or a more specific success code if needed, e.g., for creation 201
CODE_NOT_FOUND: int = 404
CODE_INFO_OR_SPECIFIC_CONDITION: int = 299 # Example custom code for informational/specific non-error conditions
# endregion

# region 配置模型定义 (Pydantic模型)

class RateLimitConfig(BaseModel):
    """单个接口的速率限制配置模型。"""
    limit: int = Field(description="在时间窗口内的最大请求次数")
    window: int = Field(description="时间窗口大小（秒）")

class UserTypeRateLimits(BaseModel):
    """特定用户类型的速率限制配置集合。"""
    get_exam: RateLimitConfig = RateLimitConfig(limit=3, window=120)
    auth_attempts: RateLimitConfig = RateLimitConfig(limit=5, window=60)

class CloudflareIPsConfig(BaseModel):
    """Cloudflare IP范围获取配置。"""
    v4_url: str = "https://www.cloudflare.com/ips-v4/"
    v6_url: str = "https://www.cloudflare.com/ips-v6/"
    fetch_interval_seconds: int = 86400

class DatabaseFilesConfig(BaseModel):
    """数据库文件路径配置（相对于data目录）。"""
    papers: str = "db.json"
    users: str = "users_db.json"

class UserValidationConfig(BaseModel):
    """用户注册时的验证规则配置。"""
    uid_min_len: int = Field(5, ge=1, description="用户名最小长度")
    uid_max_len: int = Field(16, description="用户名最大长度") # ge 约束依赖于 uid_min_len，在Pydantic v2中通常用 @model_validator
    password_min_len: int = Field(8, ge=1, description="密码最小长度")
    password_max_len: int = Field(48, description="密码最大长度") # ge 约束依赖于 password_min_len
    uid_regex: str = r"^[a-z0-9_]+$"

class Settings(BaseModel):
    """应用主配置模型。"""
    app_name: str = "在线考试系统"
    app_domain: str = Field(default_factory=lambda: os.getenv("APP_DOMAIN", "localhost"))
    frontend_domain: str = Field(default_factory=lambda: os.getenv("FRONTEND_DOMAIN", "http://localhost:3000"))
    listening_port: int = Field(default_factory=lambda: int(os.getenv("LISTENING_PORT", "17071")))
    
    default_admin_password_override: Optional[str] = Field(None)
    token_expiry_hours: int = Field(24, ge=1)
    token_length_bytes: int = Field(32, ge=16, le=64)
    
    num_questions_per_paper_default: int = Field(50, ge=1, description="默认每份试卷的题目数量")
    # 新增用于试卷生成的常量配置
    num_correct_choices_to_select: int = Field(1, ge=1, description="每道选择题应选取的正确选项数量")
    num_incorrect_choices_to_select: int = Field(3, ge=1, description="每道选择题应选取的错误选项数量")
    generated_code_length_bytes: int = Field(8, ge=4, le=16, description="用于选项ID和通行码的随机十六进制字符串的字节长度 (最终字符串长度为其2倍)")

    passing_score_percentage: float = Field(60.0, ge=0, le=100)
    db_persist_interval_seconds: int = Field(60, ge=10)
    
    rate_limits: Dict[str, UserTypeRateLimits] = {
        "default_user": UserTypeRateLimits(),
        "limited_user": UserTypeRateLimits(
            get_exam=RateLimitConfig(limit=1, window=300),
            auth_attempts=RateLimitConfig(limit=2, window=300)
        )
    }
    cloudflare_ips: CloudflareIPsConfig = CloudflareIPsConfig()
    log_file_name: str = "exam_app.log"
    log_level: str = Field("INFO", description="应用日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)")
    database_files: DatabaseFilesConfig = DatabaseFilesConfig()
    
    question_library_path: str = Field("library")
    question_library_index_file: str = Field("index.json")
    
    user_config: UserValidationConfig = UserValidationConfig()

    data_dir: Path = Field(default_factory=lambda: Path.cwd() / "data", exclude=True)

    # Pydantic v2 的模型验证器，用于跨字段验证
    @validator('user_config')
    def check_user_config_lengths(cls, v: UserValidationConfig) -> UserValidationConfig:
        if v.uid_max_len < v.uid_min_len:
            raise ValueError("用户名字段 uid_max_len 不能小于 uid_min_len")
        if v.password_max_len < v.password_min_len:
            raise ValueError("密码字段 password_max_len 不能小于 password_min_len")
        return v
    
    @validator('log_level')
    def log_level_must_be_valid(cls, v: str) -> str:
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"无效的日志级别 '{v}'. 允许的级别: {valid_levels}")
        return v.upper()

    model_config = {
        "validate_assignment": True,
        "extra": "ignore"
    }

    def get_db_file_path(self, db_type: str) -> Path:
        """获取特定数据库文件的完整路径。"""
        if db_type == "papers": return self.data_dir / self.database_files.papers
        elif db_type == "users": return self.data_dir / self.database_files.users
        elif db_type == "settings": return self.data_dir / "settings.json"
        raise ValueError(f"未知的数据库类型: {db_type}")

    def get_library_path(self) -> Path:
        """获取题库文件夹的完整路径。"""
        return self.data_dir / self.question_library_path
    
    def get_library_index_path(self) -> Path:
        """获取题库索引文件的完整路径。"""
        return self.get_library_path() / self.question_library_index_file
# endregion

# region 配置加载与管理逻辑
_settings_instance: Optional[Settings] = None
_settings_file_lock = asyncio.Lock()

def setup_logging(log_level_str: str, log_file_name: str, data_dir: Path):
    """
    配置应用范围的日志记录。
    """
    log_level = getattr(logging, log_level_str.upper(), logging.INFO)
    
    # 获取根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # 移除现有的处理器，以避免重复日志
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # 定义日志格式
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s"
    )

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 文件处理器
    log_file_path = data_dir / log_file_name
    try:
        file_handler = logging.FileHandler(log_file_path, encoding='utf-8', mode='a')
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
        _config_module_logger.info(f"日志将写入到: {log_file_path} (级别: {log_level_str})")
    except Exception as e:
        _config_module_logger.error(f"无法配置日志文件处理器 '{log_file_path}': {e}")

def _ensure_data_files_exist(settings_obj: Settings): # ... (逻辑不变)
    try:
        settings_obj.data_dir.mkdir(parents=True, exist_ok=True)
        users_db_path = settings_obj.get_db_file_path("users")
        if not users_db_path.exists():
            with open(users_db_path, "w", encoding="utf-8") as f: json.dump([], f)
            _config_module_logger.info(f"提示：已在 '{users_db_path}' 创建空的用户数据库文件。")
        papers_db_path = settings_obj.get_db_file_path("papers")
        if not papers_db_path.exists():
            with open(papers_db_path, "w", encoding="utf-8") as f: json.dump([], f)
            _config_module_logger.info(f"提示：已在 '{papers_db_path}' 创建空的试卷数据库文件。")
        library_path = settings_obj.get_library_path()
        library_path.mkdir(parents=True, exist_ok=True)
        library_index_path = settings_obj.get_library_index_path()
        if not library_index_path.exists():
            with open(library_index_path, "w", encoding="utf-8") as f: json.dump([], f, indent=4, ensure_ascii=False)
            _config_module_logger.info(f"提示：已在 '{library_index_path}' 创建空的题库索引文件。")
    except IOError as e: _config_module_logger.warning(f"创建数据文件或目录时发生IO错误: {e}")
    except Exception as e: _config_module_logger.warning(f"创建数据文件或目录时发生未知错误: {e}")

def load_settings() -> Settings: # ... (逻辑不变)
    global _settings_instance
    if _settings_instance is not None: return _settings_instance
    project_root = Path.cwd(); data_dir = project_root / "data"; settings_file = data_dir / "settings.json"
    load_dotenv(dotenv_path=project_root / ".env")
    json_config: Dict[str, Any] = {}
    if settings_file.exists() and settings_file.is_file():
        try:
            with open(settings_file, "r", encoding="utf-8") as f: json_config = json.load(f)
        except (json.JSONDecodeError, IOError) as e: _config_module_logger.warning(f"无法从 '{settings_file}' 加载配置: {e}。")
    else: _config_module_logger.info(f"配置文件 '{settings_file}' 未找到。")
    env_settings = {"app_domain": os.getenv("APP_DOMAIN"), "frontend_domain": os.getenv("FRONTEND_DOMAIN"), "listening_port": os.getenv("LISTENING_PORT"), "default_admin_password_override": os.getenv("INITIAL_ADMIN_PASSWORD")}
    env_settings_filtered = {k: v for k, v in env_settings.items() if v is not None}
    temp_settings_from_json = Settings(**json_config); final_init_data = temp_settings_from_json.model_dump(); final_init_data.update(env_settings_filtered)
    try: parsed_settings = Settings(**final_init_data); _config_module_logger.info("应用配置已成功加载和验证。")
    except ValidationError as e: _config_module_logger.error(f"配置验证失败！\n{e}\n将使用默认值。", exc_info=True); parsed_settings = Settings()
    parsed_settings.data_dir = data_dir; _ensure_data_files_exist(parsed_settings)
    if not settings_file.exists() or not json_config:
        try:
            settings_file.parent.mkdir(parents=True, exist_ok=True)
            with open(settings_file, "w", encoding="utf-8") as f:
                writable_settings = parsed_settings.model_dump(exclude={"data_dir", "app_domain", "frontend_domain", "listening_port", "default_admin_password_override"})
                json.dump(writable_settings, f, indent=4, ensure_ascii=False)
            _config_module_logger.info(f"提示：已将基础配置写入 '{settings_file}'。")
        except IOError as e: _config_module_logger.warning(f"无法写入初始配置到 '{settings_file}': {e}")
    
    # Setup logging as soon as settings are loaded
    setup_logging(parsed_settings.log_level, parsed_settings.log_file_name, parsed_settings.data_dir)
    _settings_instance = parsed_settings; return _settings_instance

async def update_and_persist_settings(new_settings_data: Dict[str, Any]) -> Settings: # ... (逻辑不变)
    global _settings_instance
    if _settings_instance is None: load_settings(); assert _settings_instance is not None
    async with _settings_file_lock:
        settings_file_path = _settings_instance.get_db_file_path("settings"); current_json_config: Dict[str, Any] = {}
        if settings_file_path.exists():
            try:
                with open(settings_file_path, "r", encoding="utf-8") as f: current_json_config = json.load(f)
            except (json.JSONDecodeError, IOError) as e: _config_module_logger.error(f"读取当前 settings.json 失败: {e}。")
        data_to_persist = {**current_json_config, **new_settings_data}
        env_overrides = {"app_domain": os.getenv("APP_DOMAIN"), "frontend_domain": os.getenv("FRONTEND_DOMAIN"), "listening_port": os.getenv("LISTENING_PORT"), "default_admin_password_override": os.getenv("INITIAL_ADMIN_PASSWORD")}
        env_overrides_filtered = {k: v for k, v in env_overrides.items() if v is not None}
        final_data_for_pydantic_init = {**data_to_persist, **env_overrides_filtered}
        try: updated_settings_obj = Settings(**final_data_for_pydantic_init)
        except ValidationError as e: _config_module_logger.error(f"更新配置验证失败: {e}"); raise ValueError(f"提供的配置数据无效: {e}")
        keys_from_env_to_exclude_from_json = ["app_domain", "frontend_domain", "listening_port", "default_admin_password_override"]
        data_to_write_to_json = {k: v for k, v in data_to_persist.items() if k not in keys_from_env_to_exclude_from_json}
        try:
            with open(settings_file_path, "w", encoding="utf-8") as f: json.dump(data_to_write_to_json, f, indent=4, ensure_ascii=False)
            _settings_instance = updated_settings_obj; _settings_instance.data_dir = Path("data") 
            # Re-setup logging if log level or file name changed
            setup_logging(_settings_instance.log_level, _settings_instance.log_file_name, _settings_instance.data_dir)
            _config_module_logger.info(f"应用配置已成功更新并写入 '{settings_file_path}'。")
            return _settings_instance
        except IOError as e: _config_module_logger.error(f"更新配置文件 '{settings_file_path}' 失败: {e}"); raise
settings: Settings = load_settings()
# endregion
