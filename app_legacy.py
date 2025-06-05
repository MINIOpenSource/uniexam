# -*- coding: utf-8 -*-
# region 模块导入与初始设置
"""
FastAPI 应用，用于管理和批改试卷。

主要功能：
- 用户账户系统（注册、登录、Token刷新）。
- 基于Token的认证机制，保护核心答题接口。
- 用户可以请求新试卷（受速率限制），并根据难度参数从不同的JSON文件加载题库。
- 用户可以提交答案进行批改。
- 用户可以通过 /update 接口保存未完成的试卷进度。
- 用户可以查看自己的答题历史和历史试卷详情。
- 试卷数据主要存储在内存中，并每分钟定期持久化到 db.json 文件。
- 应用关闭时会执行一次最终保存，以减少数据丢失风险。
- 提供 /admin/ 路径下的API用于管理试卷和题库，需要HTTP Basic密码验证。
  Admin的试卷摘要API (/admin/paper/all) 包含总题数、已答题数和正确题数。
- 自动获取并使用 Cloudflare IP 地址范围来更准确地识别客户端真实IP。
- 日志信息将写入 exam_app.log 文件。
- 新试卷请求的速率限制为每个IP在120秒内最多3次，恢复试卷不受此限制。
"""

import asyncio
import copy  # 用于深拷贝内存数据结构，防止意外修改
import datetime
import ipaddress  # 用于处理IP地址和网络
import json
import logging
import os
import random
import secrets  # 用于生成安全的随机 Token 和比较字符串
import time
import uuid
from enum import Enum  # 用于定义枚举类型，如难度级别
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import UUID  # 用于处理UUID类型

import fastapi  # FastAPI 框架本身
import httpx  # 用于异步HTTP请求 (需要安装: pip install httpx)
import uvicorn  # ASGI 服务器
from fastapi import (
    Depends,
    HTTPException,
    Query,
    Request,
    status as http_status,
)  # FastAPI 相关组件
from fastapi.routing import APIRouter  # 用于组织路由
from fastapi.security import HTTPBasic, HTTPBasicCredentials  # 用于 HTTP Basic 认证
from passlib.context import CryptContext  # 用于密码哈希
from pydantic import BaseModel, Field  # 用于数据验证和模型定义
from starlette.middleware.cors import CORSMiddleware  # 用于处理跨域资源共享
from starlette.responses import JSONResponse  # 用于返回JSON响应

# Application-specific imports
from .models.paper_models import HistoryPaperQuestionClientView

# endregion

# region 日志设置
LOG_FILE_NAME = "exam_app.log"  # 日志文件名
app_logger = logging.getLogger(
    "exam_app_logger"
)  # 获取一个名为 "exam_app_logger" 的日志记录器
app_logger.setLevel(logging.INFO)  # 设置日志记录器的最低级别为 INFO

try:
    # 创建文件处理器，用于将日志写入文件
    file_handler = logging.FileHandler(LOG_FILE_NAME, encoding="utf-8", mode="a")
    file_handler.setLevel(logging.INFO)  # 文件处理器的日志级别

    # 创建格式化器，定义日志消息的输出格式
    log_formatter = logging.Formatter("%(message)s")
    file_handler.setFormatter(log_formatter)

    # 将文件处理器添加到日志记录器
    app_logger.addHandler(file_handler)
    app_logger.propagate = False  # 防止日志向上传播
except Exception as e:
    print(f"错误：无法配置日志文件处理器: {e}")
# endregion

# region 全局常量与枚举定义
NUM_QUESTIONS_PER_PAPER: int = 50
NUM_CORRECT_CHOICES_TO_SELECT: int = 1
NUM_INCORRECT_CHOICES_TO_SELECT: int = 3
PASSING_SCORE_THRESHOLD: int = 40
GENERATED_CODE_LENGTH: int = 16
TOKEN_LENGTH_BYTES: int = 32
TOKEN_EXPIRY_HOURS: int = 24

DEFAULT_DB_FILE_PATH: str = "db.json"
DEFAULT_USERS_DB_FILE_PATH: str = "users_db.json"
DB_PERSIST_INTERVAL_SECONDS: int = 60

CLOUDFLARE_IPV4_URL: str = "https://www.cloudflare.com/ips-v4/"
CLOUDFLARE_IPV6_URL: str = "https://www.cloudflare.com/ips-v6/"
CLOUDFLARE_IP_FETCH_INTERVAL_SECONDS: int = 24 * 60 * 60

EXAM_REQUEST_LIMIT_PER_WINDOW: int = 3
EXAM_REQUEST_WINDOW_SECONDS: int = 120
AUTH_REQUEST_LIMIT_PER_WINDOW: int = 5
AUTH_REQUEST_WINDOW_SECONDS: int = 60

cloudflare_ipv4_ranges: List[ipaddress.IPv4Network] = []
cloudflare_ipv6_ranges: List[ipaddress.IPv6Network] = []
cloudflare_ranges_last_updated: Optional[float] = None

ip_exam_request_timestamps: Dict[str, List[float]] = {}
ip_login_attempt_timestamps: Dict[str, List[float]] = {}
ip_signin_attempt_timestamps: Dict[str, List[float]] = {}

CODE_SUCCESS: int = 200
CODE_AUTH_SUCCESS: str = "SUCCESS"
CODE_AUTH_WRONG: str = "WRONG"
CODE_AUTH_DUPLICATE: str = "DUPLICATE"
CODE_INFO_OR_SPECIFIC_CONDITION: int = 1001

ADMIN_USERNAME: str = "admin"
ADMIN_PASSWORD: str = "password"


class DifficultyLevel(str, Enum):
    easy = "easy"
    hybrid = "hybrid"
    hard = "hard"


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
# endregion

# region FastAPI 应用实例初始化
app = fastapi.FastAPI(
    title="试卷 API",
    description="包含用户账户、Token认证、历史记录及Cloudflare IP感知等功能的试卷API。",
    version="2.4.1",  # 版本更新：增强Admin摘要字段
)
# endregion

# region HTTP Basic Authentication 依赖项 (Admin)
admin_security = HTTPBasic()


def get_current_admin_user(credentials: HTTPBasicCredentials = Depends(admin_security)):
    """FastAPI 依赖项，用于验证 Admin 用户的 HTTP Basic Auth 凭据。"""
    correct_username = secrets.compare_digest(credentials.username, ADMIN_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password for admin",
            headers={"WWW-Authenticate": 'Basic realm="Admin Area"'},
        )
    return credentials.username


# endregion


# region 工具函数
def get_current_timestamp_str() -> str:
    """获取当前时间的格式化字符串 YYYY-MM-DD HH:MM:SS。"""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def format_short_uuid(uuid_obj: Union[UUID, str]) -> str:
    """将UUID对象或字符串格式化为 "前四位....后四位" 的缩写形式。"""
    s = str(uuid_obj)
    return f"{s[:4]}....{s[-4:]}" if len(s) > 8 else s


def get_client_ip(request: Request) -> str:
    """
    获取客户端真实IP地址。
    如果直接连接来自Cloudflare的已知IP范围，则信任CF相关请求头。
    否则，使用直接连接的IP地址。
    """
    direct_connecting_ip_str = request.client.host if request.client else "Unknown"
    if not direct_connecting_ip_str or direct_connecting_ip_str == "Unknown":
        app_logger.warning("无法从 request.client.host 获取直接连接IP。")
        x_real_ip = request.headers.get("x-real-ip")
        if x_real_ip:
            app_logger.debug(f"request.client.host 为空, 使用 X-Real-IP: {x_real_ip}")
            return x_real_ip
        x_forwarded_for = request.headers.get("x-forwarded-for")
        if x_forwarded_for:
            first_ip = x_forwarded_for.split(",")[0].strip()
            app_logger.debug(
                f"request.client.host 为空, 使用 X-Forwarded-For 的第一个IP: {first_ip}"
            )
            return first_ip
        return "Unknown"

    try:
        direct_connecting_ip = ipaddress.ip_address(direct_connecting_ip_str)
    except ValueError:
        app_logger.warning(
            f"无法将直接连接IP '{direct_connecting_ip_str}' 解析为有效IP地址。将使用原始字符串。"
        )
        return direct_connecting_ip_str

    is_from_cloudflare = False
    if direct_connecting_ip.version == 4 and cloudflare_ipv4_ranges:
        is_from_cloudflare = any(
            direct_connecting_ip in network for network in cloudflare_ipv4_ranges
        )
    elif direct_connecting_ip.version == 6 and cloudflare_ipv6_ranges:
        is_from_cloudflare = any(
            direct_connecting_ip in network for network in cloudflare_ipv6_ranges
        )

    if is_from_cloudflare:
        app_logger.debug(
            f"连接来自Cloudflare IP: {direct_connecting_ip_str}。尝试从请求头获取真实客户端IP。"
        )
        cf_ip = request.headers.get("cf-connecting-ip")
        if cf_ip:
            try:
                ipaddress.ip_address(cf_ip)
                app_logger.debug(f"从 'CF-Connecting-IP' 获取到IP: {cf_ip}")
                return cf_ip
            except ValueError:
                app_logger.warning(
                    f"'CF-Connecting-IP' 的值 '{cf_ip}' 不是有效的IP地址。"
                )
        x_forwarded_for = request.headers.get("x-forwarded-for")
        if x_forwarded_for:
            real_ip = x_forwarded_for.split(",")[0].strip()
            try:
                ipaddress.ip_address(real_ip)
                app_logger.debug(
                    f"从 'X-Forwarded-For' 获取到IP: {real_ip} (原始XFF: '{x_forwarded_for}')"
                )
                return real_ip
            except ValueError:
                app_logger.warning(
                    f"'X-Forwarded-For' 的第一个IP值 '{real_ip}' 不是有效的IP地址。"
                )
        app_logger.warning(
            f"连接来自Cloudflare IP {direct_connecting_ip_str}，但未找到有效的代理头。将使用Cloudflare连接IP。"
        )
        return direct_connecting_ip_str
    else:
        app_logger.debug(
            f"连接来自非Cloudflare IP: {direct_connecting_ip_str}。将使用此直接连接IP。"
        )
        return direct_connecting_ip_str


def shuffle_dictionary_items(input_dict: Dict[Any, Any]) -> Dict[Any, Any]:
    """随机打乱字典条目的顺序。"""
    if not isinstance(input_dict, dict):
        raise TypeError("输入必须是一个字典。")
    items_list: List[Tuple[Any, Any]] = list(input_dict.items())
    random.shuffle(items_list)
    return dict(items_list)


def generate_random_hex_string(length_bytes: int) -> str:
    """生成指定字节长度的随机十六进制字符串。"""
    return secrets.token_hex(length_bytes)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证明文密码与哈希密码是否匹配。"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """生成密码的哈希值。"""
    return pwd_context.hash(password)


# endregion

# region Pydantic 数据模型定义
# Import models needed for local definitions in app.py
# from .models.paper_models import HistoryPaperQuestionClientView  # Moved import earlier


# --- 用户认证与账户模型 ---
class UserCredentialsPayload(BaseModel):
    uid: str = Field(..., min_length=3, max_length=50, description="用户名")
    password: str = Field(..., min_length=6, description="密码")


class TokenResponse(BaseModel):
    status_code: str = Field(CODE_AUTH_SUCCESS, description="操作状态码")
    token: str = Field(..., description="访问Token")


class AuthStatusResponse(BaseModel):
    status_code: str


# --- 主应用 API 模型 ---
class PaperSubmissionPayload(BaseModel):
    paper_id: UUID
    result: List[str]


class ExamPaperResponse(BaseModel):
    paper_id: str
    difficulty: DifficultyLevel
    paper: List[Dict[str, Any]]
    submitted_answers_for_resume: Optional[List[str]] = Field(None, alias="finished")
    model_config = {"populate_by_name": True}


class GradingResultResponse(BaseModel):
    code: int
    status_code: str
    message: Optional[str] = None
    passcode: Optional[str] = None
    score: Optional[int] = None
    previous_result: Optional[str] = None


class UpdateProgressResponse(BaseModel):
    code: int
    status_code: str
    message: str
    paper_id: Optional[str] = None
    last_update_time_utc: Optional[str] = None


# --- 历史记录 API 模型 ---
class HistoryItem(BaseModel):
    paper_id: str
    difficulty: DifficultyLevel
    score: Optional[int] = None
    pass_status: Optional[str] = None


class HistoryPaperDetailResponse(BaseModel):
    paper_id: str
    difficulty: DifficultyLevel
    paper_questions: List[HistoryPaperQuestionClientView]
    score: Optional[int] = None
    submitted_answers_card: Optional[List[str]] = None
    pass_status: Optional[str] = None
    passcode: Optional[str] = None


# --- Admin API 模型 ---
class QuestionModel(BaseModel):
    body: str = Field(..., min_length=1)
    question_type: (
        str  # Added to match qb_models.QuestionModel for consistency in admin add
    )
    correct_choices: Optional[List[str]] = Field(None, min_items=1)
    incorrect_choices: Optional[List[str]] = Field(None, min_items=1)
    # Add other fields from qb_models.QuestionModel if admin can edit them all


class PaperAdminView(BaseModel):
    """用于 GET /admin/paper/all 的试卷摘要信息模型。"""

    paper_id: str
    user_uid: Optional[str] = None
    creation_time_utc: str
    creation_ip: str
    difficulty: Optional[str] = None
    count: int  # 新增：总题数
    finished_count: Optional[int] = None  # 新增：已作答题数
    correct_count: Optional[int] = None  # 新增：正确题数 (等同于已批改的score)
    score: Optional[int] = None  # 保留 score 字段，correct_count 将映射它
    submission_time_utc: Optional[str] = None
    submission_ip: Optional[str] = None
    pass_status: Optional[str] = None
    passcode: Optional[str] = None
    last_update_time_utc: Optional[str] = None
    last_update_ip: Optional[str] = None


class PaperQuestionInternalDetail(BaseModel):
    body: str
    correct_choices_map: Dict[str, str]
    incorrect_choices_map: Dict[str, str]


class PaperFullDetailModel(BaseModel):
    paper_id: str
    user_uid: Optional[str] = None
    creation_time_utc: str
    creation_ip: str
    difficulty: Optional[str] = None
    paper_questions: List[PaperQuestionInternalDetail]
    score: Optional[int] = None
    submitted_answers_card: Optional[List[str]] = None
    submission_time_utc: Optional[str] = None
    submission_ip: Optional[str] = None
    pass_status: Optional[str] = None
    passcode: Optional[str] = None
    last_update_time_utc: Optional[str] = None
    last_update_ip: Optional[str] = None


# endregion


# region 用户数据库与Token管理类 (UserDatabase)
class UserDatabase:  # ... (逻辑不变)
    def __init__(self, users_file_path: str = DEFAULT_USERS_DB_FILE_PATH):
        self.users_file_path: str = users_file_path
        self.in_memory_users: List[Dict[str, str]] = []
        self.active_tokens: Dict[str, Dict[str, Any]] = {}
        self.users_file_lock = asyncio.Lock()
        self._load_users_from_file()

    def _load_users_from_file(self) -> None:
        try:
            if os.path.exists(self.users_file_path):
                with open(self.users_file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    self.in_memory_users = data
                    app_logger.info(
                        f"成功从 '{self.users_file_path}' 加载 {len(self.in_memory_users)} 个用户账户。"
                    )
                else:
                    app_logger.warning(
                        f"'{self.users_file_path}' 内容不是列表，用户数据库初始化为空。"
                    )
            else:
                app_logger.info(
                    f"用户数据库文件 '{self.users_file_path}' 未找到，初始化为空。"
                )
        except (json.JSONDecodeError, ValueError) as e:
            app_logger.error(
                f"从 '{self.users_file_path}' 加载用户数据失败: {e}。初始化为空。"
            )
        except Exception as e:
            app_logger.error(
                f"从 '{self.users_file_path}' 加载用户数据时发生未知错误: {e}。",
                exc_info=True,
            )

    async def _persist_users_to_file_async(self) -> None:
        async with self.users_file_lock:
            try:
                users_to_write = copy.deepcopy(self.in_memory_users)
                with open(self.users_file_path, "w", encoding="utf-8") as f:
                    json.dump(users_to_write, f, indent=4, ensure_ascii=False)
                app_logger.info(
                    f"成功将 {len(users_to_write)} 个用户账户持久化到 '{self.users_file_path}'。"
                )
            except Exception as e:
                app_logger.error(
                    f"持久化用户数据库到 '{self.users_file_path}' 失败: {e}",
                    exc_info=True,
                )

    def get_user(self, uid: str) -> Optional[Dict[str, str]]:
        for user in self.in_memory_users:
            if user.get("uid") == uid:
                return user
        return None

    async def add_user(self, uid: str, password: str) -> bool:
        if self.get_user(uid):
            return False
        hashed_password = get_password_hash(password)
        self.in_memory_users.append({"uid": uid, "hashed_password": hashed_password})
        await self._persist_users_to_file_async()
        return True

    def generate_token(self, user_uid: str) -> str:
        token = generate_random_hex_string(TOKEN_LENGTH_BYTES)
        expires_at = time.time() + (TOKEN_EXPIRY_HOURS * 3600)
        self.active_tokens[token] = {"user_uid": user_uid, "expires_at": expires_at}
        app_logger.info(
            f"为用户 '{user_uid}' 生成新Token (部分): {token[:8]}...，有效期至: {datetime.datetime.fromtimestamp(expires_at).isoformat()}"
        )
        return token

    def validate_token(self, token: str) -> Optional[str]:
        token_data = self.active_tokens.get(token)
        if token_data and token_data["expires_at"] > time.time():
            return token_data["user_uid"]
        if token_data and token_data["expires_at"] <= time.time():
            app_logger.info(f"Token (部分) {token[:8]}... 已过期并被移除。")
            self.active_tokens.pop(token, None)
        return None

    def refresh_token(self, old_token: str) -> Optional[str]:
        user_uid = self.validate_token(old_token)
        if user_uid:
            self.active_tokens.pop(old_token, None)
            return self.generate_token(user_uid)
        return None

    async def cleanup_expired_tokens(self):
        current_time = time.time()
        expired_keys = [
            token
            for token, data in self.active_tokens.items()
            if data["expires_at"] <= current_time
        ]
        for token_key in expired_keys:
            self.active_tokens.pop(token_key, None)
            app_logger.info(f"后台清理：移除过期Token (部分): {token_key[:8]}...")
        if expired_keys:
            app_logger.info(f"后台清理：共移除了 {len(expired_keys)} 个过期Token。")


# endregion


# region 试卷数据库类 (PaperDatabase)
class PaperDatabase:  # ... (大部分逻辑不变)
    def __init__(self, database_file_path: str = DEFAULT_DB_FILE_PATH):
        self.database_file_path: str = database_file_path
        self.in_memory_papers: List[Dict[str, Any]] = []
        self.db_file_lock = asyncio.Lock()
        self._load_db_from_file_on_startup()
        self.question_banks: Dict[DifficultyLevel, List[Dict[str, Any]]] = (
            self._load_all_question_banks()
        )

    def _load_db_from_file_on_startup(self) -> None:
        try:
            if os.path.exists(self.database_file_path):
                with open(self.database_file_path, "r", encoding="utf-8") as db_file:
                    data = json.load(db_file)
                if isinstance(data, list):
                    self.in_memory_papers = data
                    app_logger.info(
                        f"成功从 '{self.database_file_path}' 加载 {len(self.in_memory_papers)} 条试卷记录到内存。"
                    )
                else:
                    app_logger.warning(
                        f"'{self.database_file_path}' 内容不是列表，内存数据库初始化为空。"
                    )
                    self.in_memory_papers = []
            else:
                app_logger.info(
                    f"数据库文件 '{self.database_file_path}' 未找到，内存数据库初始化为空。"
                )
                self.in_memory_papers = []
        except (json.JSONDecodeError, ValueError) as e:
            app_logger.error(
                f"从 '{self.database_file_path}' 加载数据失败: {e}。内存数据库初始化为空。"
            )
            self.in_memory_papers = []
        except Exception as e:
            app_logger.error(
                f"从 '{self.database_file_path}' 加载数据时发生未知错误: {e}。",
                exc_info=True,
            )
            self.in_memory_papers = []

    async def _persist_db_to_file_async(self) -> None:
        async with self.db_file_lock:
            try:
                papers_to_write = copy.deepcopy(self.in_memory_papers)
                with open(self.database_file_path, "w", encoding="utf-8") as db_file:
                    json.dump(papers_to_write, db_file, indent=4, ensure_ascii=False)
                app_logger.info(
                    f"成功将 {len(papers_to_write)} 条试卷记录从内存持久化到 '{self.database_file_path}'。"
                )
            except Exception as e:
                app_logger.error(
                    f"持久化内存数据库到 '{self.database_file_path}' 失败: {e}",
                    exc_info=True,
                )

    def _load_question_bank_from_file(self, file_path: str) -> List[Dict[str, Any]]:
        try:
            with open(file_path, "r", encoding="utf-8") as items_file:
                questions_raw = json.load(items_file)
            if not isinstance(questions_raw, list):
                raise ValueError(f"题库文件 '{file_path}' 内容不是一个列表。")
            validated_questions = []
            for idx, q_raw in enumerate(questions_raw):
                try:
                    question_model = QuestionModel(**q_raw)
                    validated_questions.append(question_model.model_dump())
                except Exception as e_val:
                    raise ValueError(
                        f"题库文件 '{file_path}' 中索引 {idx} 处的问题数据无效: {e_val}"
                    ) from e_val
            app_logger.info(
                f"成功加载并验证题库: '{file_path}'，包含 {len(validated_questions)} 道题目。"
            )
            return validated_questions
        except FileNotFoundError as e:
            app_logger.error(f"未找到题库文件 '{file_path}'。")
            raise RuntimeError(f"未找到题库文件 '{file_path}'。") from e
        except (json.JSONDecodeError, ValueError) as e:
            app_logger.error(f"加载或解析题库 '{file_path}' 时出错: {e}")
            raise RuntimeError(f"加载或解析题库 '{file_path}' 时出错: {e}") from e

    def _load_all_question_banks(self) -> Dict[DifficultyLevel, List[Dict[str, Any]]]:
        banks = {}
        critical_failure = False
        for level in DifficultyLevel:
            file_path = f"{level.value}.json"
            try:
                banks[level] = self._load_question_bank_from_file(file_path)
            except RuntimeError as e:
                if level == DifficultyLevel.hybrid:
                    app_logger.critical(f"关键的 '{level.value}' 题库加载失败: {e}")
                    critical_failure = True
                else:
                    app_logger.warning(f"警告：'{level.value}' 题库加载失败: {e}。")
        if critical_failure or DifficultyLevel.hybrid not in banks:
            app_logger.critical("关键题库加载失败。")
            raise RuntimeError("关键题库加载失败。")
        if not banks:
            app_logger.critical("所有题库均加载失败！")
            raise RuntimeError("所有题库均加载失败！")
        return banks

    def reload_question_bank(self, difficulty: DifficultyLevel) -> bool:
        file_path = f"{difficulty.value}.json"
        try:
            self.question_banks[difficulty] = self._load_question_bank_from_file(
                file_path
            )
            app_logger.info(f"管理员操作：已成功重新加载题库 '{file_path}'。")
            return True
        except RuntimeError as e:
            app_logger.error(f"管理员操作：重新加载题库 '{file_path}' 失败: {e}")
            return False

    def create_new_paper(
        self, request: Request, difficulty: DifficultyLevel, user_uid: str
    ) -> Dict[str, Any]:
        current_question_bank = self.question_banks.get(difficulty)
        if not current_question_bank:
            raise ValueError(f"难度 '{difficulty.value}' 的题库不可用。")
        if len(current_question_bank) < NUM_QUESTIONS_PER_PAPER:
            raise ValueError(f"难度 '{difficulty.value}' 题库题目不足。")
        paper_uuid = str(uuid.uuid4())
        new_paper_data: Dict[str, Any] = {
            "paper_id": paper_uuid,
            "user_uid": user_uid,
            "creation_time_utc": datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat(),
            "creation_ip": get_client_ip(request),
            "difficulty": difficulty.value,
            "paper_questions": [],
        }
        selected_question_samples = random.sample(
            current_question_bank, NUM_QUESTIONS_PER_PAPER
        )
        for item_data in selected_question_samples:
            correct_choice_text = random.sample(
                item_data["correct_choices"], NUM_CORRECT_CHOICES_TO_SELECT
            )[0]
            correct_choice_id = generate_random_hex_string(GENERATED_CODE_LENGTH // 2)
            incorrect_choices_texts = random.sample(
                item_data["incorrect_choices"], NUM_INCORRECT_CHOICES_TO_SELECT
            )
            incorrect_choices_with_ids = {
                generate_random_hex_string(GENERATED_CODE_LENGTH // 2): text
                for text in incorrect_choices_texts
            }
            question_entry = {
                "body": item_data["body"],
                "question_type": item_data.get(
                    "question_type", "single_choice"
                ),  # Store question_type
                "correct_choices_map": {correct_choice_id: correct_choice_text},
                "incorrect_choices_map": incorrect_choices_with_ids,
            }
            new_paper_data["paper_questions"].append(question_entry)
        self.in_memory_papers.append(new_paper_data)
        app_logger.debug(
            f"用户 '{user_uid}' 的新试卷 {paper_uuid} (难度: {difficulty.value}) 已添加到内存。"
        )
        client_paper_response: Dict[str, Any] = {
            "paper_id": paper_uuid,
            "difficulty": difficulty,
            "paper": [],
        }
        for q_data in new_paper_data["paper_questions"]:
            all_choices = {
                **q_data["correct_choices_map"],
                **q_data["incorrect_choices_map"],
            }
            client_paper_response["paper"].append(
                {
                    "body": q_data["body"],
                    "choices": shuffle_dictionary_items(all_choices),
                }
            )
        return client_paper_response

    def update_paper_progress(
        self,
        paper_id: UUID,
        user_uid: str,
        submitted_answers: List[str],
        request: Request,
    ) -> Dict[str, Any]:  # ... (逻辑不变)
        target_paper_record: Optional[Dict[str, Any]] = None
        for paper_record in self.in_memory_papers:
            if (
                str(paper_record.get("paper_id")) == str(paper_id)
                and paper_record.get("user_uid") == user_uid
            ):
                target_paper_record = paper_record
                break
        if target_paper_record is None:
            return {
                "code": CODE_INFO_OR_SPECIFIC_CONDITION,
                "status_code": "NOT_FOUND",
                "message": "未找到指定的试卷或权限不足。",
            }
        pass_status = target_paper_record.get("pass_status")
        if pass_status in ["PASSED", "FAILED"]:
            return {
                "code": CODE_INFO_OR_SPECIFIC_CONDITION,
                "status_code": "ALREADY_COMPLETED",
                "message": "该试卷已完成，无法更新进度。",
                "paper_id": str(paper_id),
            }
        if (
            "paper_questions" in target_paper_record
            and isinstance(target_paper_record["paper_questions"], list)
            and len(submitted_answers) > len(target_paper_record["paper_questions"])
        ):
            return {
                "code": CODE_INFO_OR_SPECIFIC_CONDITION,
                "status_code": "INVALID_ANSWERS_LENGTH",
                "message": "提交的答案数量超过了试卷题目总数。",
            }
        update_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
        target_paper_record["submitted_answers_card"] = submitted_answers
        target_paper_record["last_update_time_utc"] = update_time
        target_paper_record["last_update_ip"] = get_client_ip(request)
        app_logger.debug(f"用户 '{user_uid}' 的试卷 {paper_id} 进度已在内存中更新。")
        return {
            "code": CODE_SUCCESS,
            "status_code": "PROGRESS_SAVED",
            "message": "试卷进度已保存。",
            "paper_id": str(paper_id),
            "last_update_time_utc": update_time,
        }

    def grade_paper_submission(
        self,
        paper_id: UUID,
        user_uid: str,
        submitted_answers: List[str],
        request: Request,
    ) -> Dict[str, Any]:  # ... (逻辑不变)
        target_paper_record: Optional[Dict[str, Any]] = None
        for paper_record in self.in_memory_papers:
            if (
                str(paper_record.get("paper_id")) == str(paper_id)
                and paper_record.get("user_uid") == user_uid
            ):
                target_paper_record = paper_record
                break
        if target_paper_record is None:
            return {
                "code": CODE_INFO_OR_SPECIFIC_CONDITION,
                "status_code": "NOT_FOUND",
                "message": "未找到指定的试卷或权限不足。",
            }
        if "pass_status" in target_paper_record:
            return {
                "code": CODE_INFO_OR_SPECIFIC_CONDITION,
                "status_code": "ALREADY_GRADED",
                "message": "这份试卷已经被批改过了。",
                "previous_result": target_paper_record.get("pass_status"),
                "score": target_paper_record.get("score"),
                "passcode": target_paper_record.get("passcode"),
            }
        if "paper_questions" not in target_paper_record or not isinstance(
            target_paper_record["paper_questions"], list
        ):
            return {
                "code": CODE_INFO_OR_SPECIFIC_CONDITION,
                "status_code": "INVALID_PAPER_STRUCTURE",
                "message": "试卷内部结构错误，无法批改。",
            }
        if len(submitted_answers) != len(target_paper_record["paper_questions"]):
            return {
                "code": CODE_INFO_OR_SPECIFIC_CONDITION,
                "status_code": "INVALID_SUBMISSION",
                "message": "提交的答案数量与试卷题目数量不匹配。",
            }
        correct_answers_count = 0
        for i, q_data in enumerate(target_paper_record["paper_questions"]):
            if (
                isinstance(q_data, dict)
                and "correct_choices_map" in q_data
                and isinstance(q_data["correct_choices_map"], dict)
                and q_data["correct_choices_map"]
            ):
                correct_choice_id = list(q_data["correct_choices_map"].keys())[0]
                if (
                    i < len(submitted_answers)
                    and submitted_answers[i] == correct_choice_id
                ):
                    correct_answers_count += 1
            else:
                app_logger.warning(
                    f"用户 '{user_uid}' 的试卷 {paper_id} 的问题 {i} 结构不正确，跳过计分。"
                )
        current_time_utc_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        target_paper_record["score"] = correct_answers_count
        target_paper_record["submitted_answers_card"] = submitted_answers
        target_paper_record["submission_time_utc"] = current_time_utc_iso
        target_paper_record["submission_ip"] = get_client_ip(request)
        target_paper_record["last_update_time_utc"] = current_time_utc_iso
        target_paper_record["last_update_ip"] = target_paper_record["submission_ip"]
        result_payload: Dict[str, Any] = {"score": correct_answers_count}
        if correct_answers_count >= PASSING_SCORE_THRESHOLD:
            target_paper_record["pass_status"] = "PASSED"
            target_paper_record["passcode"] = generate_random_hex_string(
                GENERATED_CODE_LENGTH // 2
            )
            result_payload.update(
                {
                    "code": CODE_SUCCESS,
                    "status_code": "PASSED",
                    "passcode": target_paper_record["passcode"],
                }
            )
        else:
            target_paper_record["pass_status"] = "FAILED"
            result_payload.update({"code": CODE_SUCCESS, "status_code": "FAILED"})
        app_logger.debug(f"用户 '{user_uid}' 的试卷 {paper_id} 已在内存中批改。")
        return result_payload

    def get_user_history(self, user_uid: str) -> List[Dict[str, Any]]:  # ... (逻辑不变)
        history = []
        for paper in self.in_memory_papers:
            if paper.get("user_uid") == user_uid:
                history.append(
                    {
                        "paper_id": paper.get("paper_id"),
                        "difficulty": DifficultyLevel(
                            paper.get("difficulty", DifficultyLevel.hybrid.value)
                        ),
                        "score": paper.get("score"),
                        "pass_status": paper.get("pass_status"),
                    }
                )
        return sorted(
            history,
            key=lambda x: x.get("submission_time_utc")
            or x.get("creation_time_utc", ""),
            reverse=True,
        )

    def get_user_paper_detail_for_history(
        self, paper_id_str: str, user_uid: str
    ) -> Optional[Dict[str, Any]]:  # ... (逻辑不变)
        for paper_data in self.in_memory_papers:
            # Import the correct model here, inside the method or at the top of the class/file
            # For now, let's assume it's imported at the top of the file after other model imports
            # from app.models import HistoryPaperQuestionClientView # This would be ideal
            # For this diff, we'll rely on it being available via Pydantic's global resolution or a later import
            if (
                str(paper_data.get("paper_id")) == paper_id_str
                and paper_data.get("user_uid") == user_uid
            ):
                history_questions: List[Dict[str, Any]] = []
                submitted_answers = paper_data.get("submitted_answers_card", [])
                if "paper_questions" in paper_data and isinstance(
                    paper_data["paper_questions"], list
                ):
                    for idx, q_internal in enumerate(paper_data["paper_questions"]):
                        all_choices_for_client = {
                            **q_internal.get("correct_choices_map", {}),
                            **q_internal.get("incorrect_choices_map", {}),
                        }
                        submitted_answer_for_this_q: Optional[Union[str, List[str]]] = (
                            None
                        )
                        if idx < len(submitted_answers):
                            submitted_answer_for_this_q = submitted_answers[idx]

                        # Use HistoryPaperQuestionClientView from paper_models.py
                        # Ensure HistoryPaperQuestionClientView is imported at the top of app.py
                        # from app.models.paper_models import HistoryPaperQuestionClientView
                        history_q_view = HistoryPaperQuestionClientView(
                            body=q_internal.get("body", "N/A"),
                            question_type=q_internal.get(
                                "question_type", "single_choice"
                            ),  # Get question_type
                            choices=(
                                shuffle_dictionary_items(all_choices_for_client)
                                if q_internal.get("question_type")
                                in ["single_choice", "multiple_choice"]
                                else None
                            ),
                            submitted_answer=submitted_answer_for_this_q,
                        )
                        history_questions.append(
                            history_q_view.model_dump(exclude_none=True)
                        )
                return {
                    "paper_id": paper_data["paper_id"],
                    "difficulty": DifficultyLevel(
                        paper_data.get("difficulty", DifficultyLevel.hybrid.value)
                    ),
                    "paper_questions": history_questions,
                    "score": paper_data.get("score"),
                    "submitted_answers_card": submitted_answers,
                    "pass_status": paper_data.get("pass_status"),
                    "passcode": paper_data.get("passcode"),
                }
        return None

    def admin_get_all_papers_summary_from_memory(
        self, skip: int = 0, limit: int = 100
    ) -> List[Dict[str, Any]]:  # ... (逻辑不变)
        papers_copy = copy.deepcopy(self.in_memory_papers)
        sorted_papers = sorted(
            papers_copy, key=lambda p: p.get("creation_time_utc", ""), reverse=True
        )
        return sorted_papers[skip : skip + limit]

    def admin_get_paper_detail_from_memory(
        self, paper_id_str: str
    ) -> Optional[Dict[str, Any]]:  # ... (逻辑不变)
        for paper_data in self.in_memory_papers:
            if str(paper_data.get("paper_id")) == paper_id_str:
                return copy.deepcopy(paper_data)
        return None

    def admin_delete_paper_from_memory(
        self, paper_id_str: str
    ) -> bool:  # ... (逻辑不变)
        initial_len = len(self.in_memory_papers)
        self.in_memory_papers = [
            p for p in self.in_memory_papers if str(p.get("paper_id")) != paper_id_str
        ]
        deleted = len(self.in_memory_papers) < initial_len
        if deleted:
            app_logger.info(f"[Admin] 试卷 {paper_id_str} 已从内存中删除。")
        return deleted


# endregion

# region 初始化数据库实例
try:
    user_db_handler = UserDatabase()
    paper_db_handler = PaperDatabase(database_file_path=DEFAULT_DB_FILE_PATH)
except RuntimeError as e:
    app_logger.critical(f"数据库或关键题库初始化失败，应用无法启动: {e}")
    exit(1)
# endregion

# region FastAPI 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# endregion


# region Cloudflare IP范围获取与更新任务
async def fetch_and_update_cloudflare_ips_once():
    """获取一次Cloudflare IP范围并更新全局变量。"""
    global cloudflare_ipv4_ranges, cloudflare_ipv6_ranges, cloudflare_ranges_last_updated
    try:
        app_logger.info("尝试获取Cloudflare IP地址范围...")
        async with httpx.AsyncClient() as client:
            response_v4 = await client.get(CLOUDFLARE_IPV4_URL, timeout=10.0)
            response_v4.raise_for_status()
            ipv4_cidrs = response_v4.text.strip().split("\n")
            new_ipv4_ranges = [
                ipaddress.ip_network(cidr.strip(), strict=False)
                for cidr in ipv4_cidrs
                if cidr.strip()
            ]

            response_v6 = await client.get(CLOUDFLARE_IPV6_URL, timeout=10.0)
            response_v6.raise_for_status()
            ipv6_cidrs = response_v6.text.strip().split("\n")
            new_ipv6_ranges = [
                ipaddress.ip_network(cidr.strip(), strict=False)
                for cidr in ipv6_cidrs
                if cidr.strip()
            ]

            cloudflare_ipv4_ranges = new_ipv4_ranges
            cloudflare_ipv6_ranges = new_ipv6_ranges
            cloudflare_ranges_last_updated = time.time()
            app_logger.info(
                f"成功更新Cloudflare IP范围：加载了 {len(cloudflare_ipv4_ranges)} 个IPv4范围 和 {len(cloudflare_ipv6_ranges)} 个IPv6范围。"
            )
    except httpx.HTTPStatusError as e:
        app_logger.error(
            f"获取Cloudflare IP范围时HTTP错误: {e.request.url} - {e.response.status_code}"
        )
    except httpx.RequestError as e:
        app_logger.error(
            f"获取Cloudflare IP范围时发生网络请求错误: {e.request.url} - {e}"
        )
    except ValueError as e:
        app_logger.error(f"解析Cloudflare IP范围时发生错误: {e}")
    except Exception as e:
        app_logger.error(f"更新Cloudflare IP范围时发生未知错误: {e}", exc_info=True)


async def periodic_cloudflare_ip_update_task():
    """后台任务，定期获取并更新Cloudflare的IP地址范围。"""
    while True:
        await asyncio.sleep(
            CLOUDFLARE_IP_FETCH_INTERVAL_SECONDS
        )  # 先等待再执行，因为启动时已获取
        await fetch_and_update_cloudflare_ips_once()


# endregion


# region 定期保存任务与生命周期事件
async def periodic_db_tasks():
    """运行所有定期后台任务，包括保存试卷数据和清理过期Token。"""
    while True:
        await asyncio.sleep(DB_PERSIST_INTERVAL_SECONDS)
        app_logger.info(
            f"后台任务：尝试定期 ({DB_PERSIST_INTERVAL_SECONDS}s) 执行数据库相关任务..."
        )
        await paper_db_handler._persist_db_to_file_async()
        await user_db_handler.cleanup_expired_tokens()


@app.on_event("startup")
async def startup_event_tasks():
    """应用启动时执行的事件。"""
    app_logger.info("应用启动事件：初始化并开始定期后台任务。")
    await fetch_and_update_cloudflare_ips_once()
    asyncio.create_task(periodic_cloudflare_ip_update_task())
    asyncio.create_task(periodic_db_tasks())


@app.on_event("shutdown")
async def shutdown_event():  # ... (逻辑不变)
    app_logger.info("应用关闭事件：执行最后一次数据保存...")
    await paper_db_handler._persist_db_to_file_async()
    await user_db_handler._persist_users_to_file_async()


# endregion


# region Token 认证依赖项 (普通用户)
async def get_current_active_user(
    token: str = Query(..., description="用户访问Token"),
) -> str:  # ... (逻辑不变)
    user_uid = user_db_handler.validate_token(token)
    if not user_uid:
        app_logger.warning(f"无效或过期的Token尝试访问受保护资源: {token[:8]}...")
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="无效或已过期的Token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_uid


# endregion

# region 用户认证 API 端点
auth_router = APIRouter(tags=["Authentication"])


def _apply_auth_rate_limit(client_ip: str, attempt_type: str) -> None:  # ... (逻辑不变)
    current_time = time.time()
    timestamps_dict_ref: Dict[str, List[float]]
    if attempt_type == "login":
        timestamps_dict_ref = ip_login_attempt_timestamps
    elif attempt_type == "signin":
        timestamps_dict_ref = ip_signin_attempt_timestamps
    else:
        return
    timestamps = timestamps_dict_ref.get(client_ip, [])
    timestamps = [
        ts for ts in timestamps if current_time - ts < AUTH_REQUEST_WINDOW_SECONDS
    ]
    if len(timestamps) >= AUTH_REQUEST_LIMIT_PER_WINDOW:
        app_logger.warning(f"IP {client_ip} 的 {attempt_type} 操作超出速率限制。")
        raise HTTPException(
            status_code=http_status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"{attempt_type.capitalize()} 尝试过于频繁。",
        )
    timestamps.append(current_time)
    timestamps_dict_ref[client_ip] = timestamps


@auth_router.post(
    "/login",
    response_model=TokenResponse,
    responses={
        401: {"model": AuthStatusResponse},
        429: {"description": "Too Many Requests"},
    },
)
async def login_for_access_token(
    payload: UserCredentialsPayload, request: Request
):  # ... (逻辑不变)
    client_ip = get_client_ip(request)
    _apply_auth_rate_limit(client_ip, "login")
    user = user_db_handler.get_user(payload.uid)
    if not user or not verify_password(payload.password, user["hashed_password"]):
        app_logger.warning(
            f"用户 '{payload.uid}' 登录失败：用户名或密码错误 (IP: {client_ip})。"
        )
        return JSONResponse(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            content={"status_code": CODE_AUTH_WRONG},
        )
    token = user_db_handler.generate_token(user["uid"])
    app_logger.info(f"用户 '{payload.uid}' 登录成功 (IP: {client_ip})。")
    return TokenResponse(token=token)


@auth_router.get(
    "/login",
    response_model=TokenResponse,
    responses={401: {"model": AuthStatusResponse}},
)
async def refresh_access_token(
    token: str = Query(..., description="需要刷新的旧Token"),
):  # ... (逻辑不变)
    new_token = user_db_handler.refresh_token(token)
    if not new_token:
        app_logger.warning(
            f"刷新Token失败：旧Token无效或已过期 (部分Token: {token[:8]}...)"
        )
        return JSONResponse(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            content={"status_code": CODE_AUTH_WRONG},
        )
    app_logger.info(f"Token (部分旧Token: {token[:8]}...) 已成功刷新。")
    return TokenResponse(token=new_token)


@auth_router.post(
    "/signin",
    response_model=TokenResponse,
    responses={
        409: {"model": AuthStatusResponse},
        429: {"description": "Too Many Requests"},
    },
)
async def sign_up_new_user(
    payload: UserCredentialsPayload, request: Request
):  # ... (逻辑不变)
    client_ip = get_client_ip(request)
    _apply_auth_rate_limit(client_ip, "signin")
    if not await user_db_handler.add_user(payload.uid, payload.password):
        app_logger.warning(
            f"用户注册失败：用户名 '{payload.uid}' 已存在 (IP: {client_ip})。"
        )
        return JSONResponse(
            status_code=http_status.HTTP_409_CONFLICT,
            content={"status_code": CODE_AUTH_DUPLICATE},
        )
    token = user_db_handler.generate_token(payload.uid)
    app_logger.info(f"新用户 '{payload.uid}' 注册成功并登录 (IP: {client_ip})。")
    return TokenResponse(token=token)


app.include_router(auth_router)
# endregion

# region 主应用 API 端点 (需要Token认证)
exam_router = APIRouter(dependencies=[Depends(get_current_active_user)], tags=["Exam"])


@exam_router.get(
    "/get_exam", response_model=ExamPaperResponse, summary="请求一份新试卷"
)
def request_new_exam_paper(
    request: Request,
    current_user_uid: str = Depends(get_current_active_user),
    difficulty: DifficultyLevel = Query(
        default=DifficultyLevel.hybrid, description="新试卷的难度级别"
    ),
):  # ... (逻辑不变)
    client_ip = get_client_ip(request)
    timestamp_str = get_current_timestamp_str()
    current_time = time.time()
    ip_timestamps = ip_exam_request_timestamps.get(client_ip, [])
    ip_timestamps = [
        ts for ts in ip_timestamps if current_time - ts < EXAM_REQUEST_WINDOW_SECONDS
    ]
    if len(ip_timestamps) >= EXAM_REQUEST_LIMIT_PER_WINDOW:
        app_logger.info(
            f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 请求新 [{difficulty.value}] 试卷，但是超出速率限制，拒绝"
        )
        raise HTTPException(
            status_code=http_status.HTTP_429_TOO_MANY_REQUESTS, detail="请求过于频繁。"
        )
    ip_timestamps.append(current_time)
    ip_exam_request_timestamps[client_ip] = ip_timestamps
    app_logger.info(
        f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 请求一份新的 [{difficulty.value}] 试卷"
    )
    try:
        new_paper_client_data = paper_db_handler.create_new_paper(
            request=request, difficulty=difficulty, user_uid=current_user_uid
        )
        short_id = format_short_uuid(new_paper_client_data["paper_id"])
        app_logger.info(
            f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 成功创建新试卷 [{difficulty.value}]：{short_id}"
        )
        return ExamPaperResponse(
            paper_id=new_paper_client_data["paper_id"],
            difficulty=new_paper_client_data["difficulty"],
            paper=new_paper_client_data["paper"],
        )
    except ValueError as ve:
        app_logger.warning(
            f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 创建新 [{difficulty.value}] 试卷失败 (ValueError): {ve}"
        )
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(ve)
        ) from ve
    except RuntimeError as re:
        app_logger.error(
            f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 创建新 [{difficulty.value}] 试卷失败 (RuntimeError): {re}"
        )
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="创建新试卷时出错。",
        ) from re
    except Exception as e:
        app_logger.error(
            f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 创建新 [{difficulty.value}] 试卷时发生意外错误: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建新试卷时发生意外错误: {str(e)}",
        ) from e


@exam_router.post(
    "/update", response_model=UpdateProgressResponse, summary="更新未完成试卷的答题进度"
)
def update_exam_progress(
    payload: PaperSubmissionPayload,
    request: Request,
    current_user_uid: str = Depends(get_current_active_user),
):  # ... (逻辑不变)
    client_ip = get_client_ip(request)
    timestamp_str = get_current_timestamp_str()
    short_paper_id = format_short_uuid(payload.paper_id)
    app_logger.info(
        f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 正在更新试卷 {short_paper_id} 的进度。"
    )
    try:
        update_result = paper_db_handler.update_paper_progress(
            payload.paper_id, current_user_uid, payload.result, request
        )
        status_code_text = update_result.get("status_code", "UNKNOWN_ERROR")
        if status_code_text == "PROGRESS_SAVED":
            app_logger.info(
                f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 成功保存试卷 {short_paper_id} 进度。"
            )
            return UpdateProgressResponse(**update_result)
        elif status_code_text == "NOT_FOUND":
            app_logger.warning(
                f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 更新试卷 {short_paper_id} 进度失败：未找到或权限不足。"
            )
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=update_result.get("message", "未找到试卷或权限不足。"),
            )
        elif status_code_text == "ALREADY_COMPLETED":
            app_logger.warning(
                f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 更新试卷 {short_paper_id} 进度失败：试卷已完成。"
            )
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail=update_result.get("message", "试卷已完成。"),
            )
        elif status_code_text == "INVALID_ANSWERS_LENGTH":
            app_logger.warning(
                f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 更新试卷 {short_paper_id} 进度失败：答案数量错误。"
            )
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=update_result.get("message", "答案数量错误。"),
            )
        else:
            app_logger.error(
                f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 更新试卷 {short_paper_id} 进度时发生已知错误: {update_result}"
            )
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=update_result.get("message", "更新进度失败。"),
            )
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        app_logger.error(
            f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 更新试卷 {short_paper_id} 进度时发生意外错误: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新进度时发生意外错误: {str(e)}",
        ) from e


@exam_router.post(
    "/finish", response_model=GradingResultResponse, summary="提交试卷答案进行批改"
)
def submit_exam_paper(
    payload: PaperSubmissionPayload,
    request: Request,
    current_user_uid: str = Depends(get_current_active_user),
):  # ... (逻辑不变)
    client_ip = get_client_ip(request)
    timestamp_str = get_current_timestamp_str()
    short_paper_id = format_short_uuid(payload.paper_id)
    app_logger.info(
        f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 正在提交试卷 {short_paper_id} 进行批改。"
    )
    try:
        outcome = paper_db_handler.grade_paper_submission(
            payload.paper_id, current_user_uid, payload.result, request
        )
        response_data = GradingResultResponse(**outcome)
        score, status_text = response_data.score, outcome.get("status_code")
        log_msg_prefix = f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 提交试卷 {short_paper_id} 的答案"
        if status_text == "PASSED":
            app_logger.info(
                f"{log_msg_prefix}，获得 {score if score is not None else 'N/A'} 分，通过考试，入群码：{response_data.passcode or 'N/A'}"
            )
        elif status_text == "FAILED":
            app_logger.info(
                f"{log_msg_prefix}，获得 {score if score is not None else 'N/A'} 分，未能通过考试"
            )
        elif status_text == "ALREADY_GRADED":
            app_logger.info(f"{log_msg_prefix}，但该试卷已经有作答记录")
        elif status_text == "NOT_FOUND":
            app_logger.info(f"{log_msg_prefix}，但试卷不存在或权限不足")
        elif status_text == "INVALID_SUBMISSION":
            app_logger.info(f"{log_msg_prefix}，但提交数据无效")
        elif status_text == "INVALID_PAPER_STRUCTURE":
            app_logger.warning(f"{log_msg_prefix}，但试卷内部结构错误，无法批改")
        else:
            app_logger.warning(
                f"{log_msg_prefix}，结果: {status_text}, 详情: {outcome}"
            )
        return JSONResponse(
            content=response_data.model_dump(exclude_none=True), status_code=200
        )
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        app_logger.error(
            f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 提交试卷 {short_paper_id} 时发生意外服务器错误: {e}",
            exc_info=True,
        )
        error_detail = {
            "code": 500,
            "status_code": "SERVER_ERROR",
            "message": f"处理您的提交时发生意外错误: {str(e)}",
        }
        return JSONResponse(content=error_detail, status_code=500)


@exam_router.get(
    "/history", response_model=List[HistoryItem], summary="获取当前用户的答题历史记录"
)
def get_user_exam_history(
    current_user_uid: str = Depends(get_current_active_user),
):  # ... (逻辑不变)
    timestamp_str = get_current_timestamp_str()
    app_logger.info(f"[{timestamp_str}] 用户 '{current_user_uid}' 请求答题历史记录。")
    history_data = paper_db_handler.get_user_history(current_user_uid)
    return [HistoryItem(**item) for item in history_data]


@exam_router.get(
    "/history_paper",
    response_model=HistoryPaperDetailResponse,
    summary="获取指定历史试卷的详细信息",
)
def get_user_history_paper_detail(
    paper_id: UUID = Query(..., description="要获取详情的历史试卷ID"),
    current_user_uid: str = Depends(get_current_active_user),
):  # ... (逻辑不变)
    timestamp_str = get_current_timestamp_str()
    short_paper_id = format_short_uuid(paper_id)
    app_logger.info(
        f"[{timestamp_str}] 用户 '{current_user_uid}' 请求历史试卷 {short_paper_id} 的详情。"
    )
    paper_detail = paper_db_handler.get_user_paper_detail_for_history(
        str(paper_id), current_user_uid
    )
    if not paper_detail:
        app_logger.warning(
            f"[{timestamp_str}] 用户 '{current_user_uid}' 请求的历史试卷 {short_paper_id} 未找到或无权限查看。"
        )
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="指定的历史试卷未找到或您无权查看。",
        )
    return HistoryPaperDetailResponse(**paper_detail)


app.include_router(exam_router)
# endregion

# region Admin API 路由
admin_router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(get_current_admin_user)],
    responses={401: {"description": "Not authorized"}},
)


@admin_router.get(
    "/paper/all", response_model=List[PaperAdminView], summary="获取所有试卷摘要"
)
def admin_get_all_papers_summary(skip: int = 0, limit: int = 100):
    """获取内存中所有试卷的摘要信息列表，按创建时间倒序排列。"""
    try:
        all_papers_data_in_memory = (
            paper_db_handler.admin_get_all_papers_summary_from_memory(skip, limit)
        )
        summaries = []
        for paper_data in all_papers_data_in_memory:
            # 计算总题数
            count = len(paper_data.get("paper_questions", []))

            # 计算已作答题数
            submitted_card = paper_data.get("submitted_answers_card")
            finished_count: Optional[int] = None
            if isinstance(submitted_card, list):
                finished_count = len(submitted_card)

            # 正确题数 (即得分，如果已批改)
            correct_count = paper_data.get("score")  # score 字段本身就是 Optional[int]

            summaries.append(
                PaperAdminView(
                    paper_id=str(paper_data.get("paper_id", "N/A")),
                    user_uid=paper_data.get("user_uid"),
                    creation_time_utc=paper_data.get("creation_time_utc", "N/A"),
                    creation_ip=paper_data.get("creation_ip", "N/A"),
                    difficulty=paper_data.get("difficulty"),
                    count=count,  # 新增
                    finished_count=finished_count,  # 新增
                    correct_count=correct_count,  # 新增 (映射自 score)
                    score=paper_data.get("score"),  # 保留原始 score
                    submission_time_utc=paper_data.get("submission_time_utc"),
                    submission_ip=paper_data.get("submission_ip"),
                    pass_status=paper_data.get("pass_status"),
                    passcode=paper_data.get("passcode"),
                    last_update_time_utc=paper_data.get("last_update_time_utc"),
                    last_update_ip=paper_data.get("last_update_ip"),
                )
            )
        return summaries
    except Exception as e:
        app_logger.error(
            f"[AdminAPI] /paper/all: 获取试卷列表时发生意外错误: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取试卷列表时发生错误: {str(e)}",
        ) from e


@admin_router.get(
    "/paper/", response_model=PaperFullDetailModel, summary="获取指定试卷的详细信息"
)
def admin_get_paper_detail(
    paper_id: str = Query(..., description="要获取详情的试卷ID"),
):  # ... (逻辑不变)
    paper_data = paper_db_handler.admin_get_paper_detail_from_memory(paper_id)
    if not paper_data:
        app_logger.warning(f"[AdminAPI] /paper/?paper_id={paper_id}: 试卷未找到。")
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"试卷ID '{paper_id}' 未找到。",
        )
    try:
        if "paper_questions" not in paper_data or not isinstance(
            paper_data["paper_questions"], list
        ):
            paper_data["paper_questions"] = []
        return PaperFullDetailModel(**paper_data)
    except Exception as e:
        app_logger.error(
            f"[AdminAPI] /paper/?paper_id={paper_id}: 转换试卷数据为详细模型时出错: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"试卷数据格式错误或不完整: {str(e)}",
        ) from e


@admin_router.delete(
    "/paper/", status_code=http_status.HTTP_200_OK, summary="删除指定的试卷"
)
def admin_delete_paper(
    paper_id: str = Query(..., description="要删除的试卷ID"),
):  # ... (逻辑不变)
    deleted = paper_db_handler.admin_delete_paper_from_memory(paper_id)
    if not deleted:
        app_logger.warning(
            f"[AdminAPI] DELETE /paper/?paper_id={paper_id}: 试卷未找到，无法删除。"
        )
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"试卷ID '{paper_id}' 未找到，无法删除。",
        )
    app_logger.info(f"[AdminAPI] 已删除试卷 (内存): {paper_id}。")
    return {"message": f"试卷 {paper_id} 已成功从内存中删除。"}


@admin_router.get(
    "/question/", response_model=List[QuestionModel], summary="获取指定难度的题库"
)
def admin_get_question_bank(
    difficulty: DifficultyLevel = Query(..., description="题库难度"),
):  # ... (逻辑不变)
    bank = paper_db_handler.question_banks.get(difficulty)
    if bank is None:
        app_logger.error(
            f"[AdminAPI] /question/?difficulty={difficulty.value}: 难度题库未加载。"
        )
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"难度 '{difficulty.value}' 的题库未加载或不存在。",
        )
    try:
        # The QuestionModel in app.py is simpler than qb_models.QuestionModel.
        # For admin view, it's better to use the full qb_models.QuestionModel if possible,
        # or ensure app.py's QuestionModel is sufficient for display.
        # Assuming bank contains dicts compatible with app.py's QuestionModel for now.
        # If bank contains full qb_models.QuestionModel instances (or dicts), adjust app.py's QuestionModel.
        return [QuestionModel(**q) for q in bank]
    except Exception as e:
        app_logger.error(
            f"[AdminAPI] /question/?difficulty={difficulty.value}: 转换题库数据时出错: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="题库数据格式错误。",
        ) from e


@admin_router.post(
    "/question/",
    status_code=http_status.HTTP_201_CREATED,
    response_model=QuestionModel,
    summary="为指定难度的题库添加题目",
)
def admin_add_question_to_bank(
    question: QuestionModel,
    difficulty: DifficultyLevel = Query(..., description="题库难度"),
):  # ... (逻辑不变)
    file_path = f"{difficulty.value}.json"
    questions_in_bank: List[Dict]
    try:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                questions_in_bank = json.load(f)
            if not isinstance(questions_in_bank, list):
                app_logger.warning(
                    f"[AdminAPI] POST /question/?difficulty={difficulty.value}: 文件 '{file_path}' 内容不是列表，将重新创建。"
                )
                questions_in_bank = []
        except FileNotFoundError:
            questions_in_bank = []
        questions_in_bank.append(question.model_dump())
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(questions_in_bank, f, indent=4, ensure_ascii=False)
        if not paper_db_handler.reload_question_bank(difficulty):
            app_logger.error(
                f"[AdminAPI] 题目已添加到文件 '{file_path}'，但内存重新加载失败。"
            )
        app_logger.info(
            f"[AdminAPI] 已向题库 '{file_path}' 添加新题目: {question.body[:50]}..."
        )
        return question
    except (json.JSONDecodeError, ValueError) as e:
        app_logger.error(
            f"[AdminAPI] 操作题库文件 '{file_path}' 失败: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"操作题库文件 '{file_path}' 失败: {str(e)}",
        ) from e
    except Exception as e:
        app_logger.error(
            f"[AdminAPI] 添加题目到题库 '{file_path}' 时发生意外错误: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"添加题目时发生意外错误: {str(e)}",
        ) from e


@admin_router.delete(
    "/question/", status_code=http_status.HTTP_200_OK, summary="删除指定题库的指定题目"
)
def admin_delete_question_from_bank(
    difficulty: DifficultyLevel = Query(..., description="题库难度"),
    _index: int = Query(..., alias="index", description="要删除的题目索引 (从0开始)"),
):  # ... (逻辑不变)
    file_path = f"{difficulty.value}.json"
    questions_in_bank: List[Dict]
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            questions_in_bank = json.load(f)
        if not isinstance(questions_in_bank, list):
            raise ValueError("题库文件内容不是一个列表。")
        if not (0 <= _index < len(questions_in_bank)):
            app_logger.warning(
                f"[AdminAPI] DELETE /question/?difficulty={difficulty.value}&index={_index}: 索引无效。"
            )
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"索引 {_index} 在题库 '{file_path}' 中无效。",
            )
        deleted_question_body = questions_in_bank.pop(_index).get("body", "N/A")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(questions_in_bank, f, indent=4, ensure_ascii=False)
        if not paper_db_handler.reload_question_bank(difficulty):
            app_logger.error(
                f"[AdminAPI] 题目已从文件 '{file_path}' 删除，但内存重新加载失败。"
            )
        app_logger.info(
            f"[AdminAPI] 已从题库 '{file_path}' 删除索引为 {_index} 的题目: {deleted_question_body[:50]}..."
        )
        return {
            "message": f"已从题库 '{difficulty.value}' 删除索引为 {_index} 的题目。",
            "deleted_question_body": deleted_question_body,
        }
    except FileNotFoundError:
        app_logger.error(
            f"[AdminAPI] DELETE /question/?difficulty={difficulty.value}&index={_index}: 文件 '{file_path}' 未找到。"
        )
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"题库文件 '{file_path}' 未找到。",
        ) from None
    except (json.JSONDecodeError, ValueError) as e:
        app_logger.error(
            f"[AdminAPI] 操作题库文件 '{file_path}' 失败: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"操作题库文件 '{file_path}' 失败: {str(e)}",
        ) from e
    except Exception as e:
        app_logger.error(
            f"[AdminAPI] 删除题库 '{file_path}' 题目时发生意外错误: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除题目时发生意外错误: {str(e)}",
        ) from e


app.include_router(admin_router)
# endregion

# region 主执行块
if __name__ == "__main__":
    app_logger.info(
        "正在启动 FastAPI 考试应用程序 (用户账户, Cloudflare IP感知, 内存DB模式)..."
    )
    app_logger.info(f"日志将写入到: {os.path.abspath(LOG_FILE_NAME)}")
    app_logger.info(
        f"试卷数据库将每隔 {DB_PERSIST_INTERVAL_SECONDS} 秒持久化到: '{DEFAULT_DB_FILE_PATH}'"
    )
    app_logger.info(
        f"用户数据库将持久化到: '{DEFAULT_USERS_DB_FILE_PATH}' (主要在注册时写入)"
    )
    app_logger.info("将尝试加载 easy.json, hybrid.json, hard.json 题库。")
    app_logger.info(
        f"Cloudflare IP范围将每隔 {CLOUDFLARE_IP_FETCH_INTERVAL_SECONDS // 3600} 小时自动更新。"
    )
    app_logger.info(
        f"Admin API 用户名: {ADMIN_USERNAME}, 密码: {ADMIN_PASSWORD} (警告：生产环境请修改!)"
    )
    app_logger.info(
        f"新试卷请求速率限制: {EXAM_REQUEST_LIMIT_PER_WINDOW} 次 / {EXAM_REQUEST_WINDOW_SECONDS} 秒。"
    )
    app_logger.info(
        f"登录/注册尝试速率限制: {AUTH_REQUEST_LIMIT_PER_WINDOW} 次 / {AUTH_REQUEST_WINDOW_SECONDS} 秒。"
    )

    uvicorn_config = uvicorn.Config(
        app=app, port=17071, host="0.0.0.0", log_level="info", access_log=False
    )
    server = uvicorn.Server(config=uvicorn_config)

    try:
        asyncio.run(server.serve())
    except KeyboardInterrupt:
        app_logger.info("FastAPI 考试应用程序被用户中断。")
    except Exception as e:
        app_logger.critical(f"应用程序启动或运行时发生严重错误: {e}", exc_info=True)
    finally:
        app_logger.info("FastAPI 考试应用程序执行流程结束。")
# endregion
