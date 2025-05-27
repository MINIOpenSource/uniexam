# -*- coding: utf-8 -*-
# region 包初始化
"""
app.models 包初始化文件。

此包包含应用中所有核心数据结构的 Pydantic 模型定义。
这些模型用于数据验证、序列化以及API接口的请求和响应类型提示。

通过从子模块中导入主要模型，可以简化其他模块对这些模型的访问路径，
例如，可以直接使用 `from app.models import UserCreate` 而不是
`from app.models.user_models import UserCreate`。
"""

# 从 user_models.py 导入核心用户相关模型
from .user_models import (
    UserTag,
    UserBase,
    UserCreate,
    UserProfileUpdate,
    UserPasswordUpdate,
    UserInDBBase,
    UserInDB,
    UserPublicProfile,
    AdminUserUpdate,
    UserDirectoryEntry # New model for user directory
)

# 从 token_models.py 导入Token相关模型
from .token_models import (
    Token,
    TokenData,
    AuthStatusResponse # 新增导入
)

# 从 qb_models.py 导入题库相关模型
from .qb_models import (
    QuestionModel,       # 单个题目的详细模型 (包含多种题型)
    LibraryIndexItem,    # 题库索引 (index.json) 中的条目模型
    QuestionBank         # 完整的题库模型 (元数据 + 题目列表)
)

# 从 paper_models.py 导入试卷和答题相关模型
from .paper_models import (
    PaperSubmissionPayload,          # 用户提交试卷/更新进度的请求体
    ExamPaperResponse,             # /get_exam 接口的响应体 (新试卷)
    GradingResultResponse,         # /finish 接口的响应体 (批改结果)
    UpdateProgressResponse,        # /update 接口的响应体 (进度保存结果)
    HistoryItem,                   # /history 接口中单个历史记录的摘要
    HistoryPaperQuestionClientView,    # /history_paper 接口中单个问题的结构
    HistoryPaperDetailResponse,    # /history_paper 接口的响应体 (历史试卷详情)
    PaperAdminView,                # Admin API /admin/paper/all 的试卷摘要
    PaperQuestionInternalDetail,   # Admin API /admin/paper/ 试卷详情中单个问题的内部结构
    PaperFullDetailModel           # Admin API /admin/paper/ 的完整试卷详情
)

# 可以定义 __all__ 变量来明确指定 `from app.models import *` 时应导入哪些名称
__all__ = [
    # User Models
    "UserTag",
    "UserBase",
    "UserCreate",
    "UserProfileUpdate",
    "UserPasswordUpdate",
    "UserInDBBase",
    "UserInDB",
    "UserPublicProfile",
    "AdminUserUpdate",
    "UserDirectoryEntry",
    # Token Models
    "Token",
    "TokenData",
    "AuthStatusResponse",
    # Question Bank Models
    "QuestionModel",
    "LibraryIndexItem",
    "QuestionBank",
    # Paper Models
    "PaperSubmissionPayload",
    "ExamPaperResponse",
    "GradingResultResponse",
    "UpdateProgressResponse",
    "HistoryItem",
    "HistoryPaperQuestionClientView",
    "HistoryPaperDetailResponse",
    "PaperAdminView",
    "PaperQuestionInternalDetail",
    "PaperFullDetailModel",
]
# endregion
