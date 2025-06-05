# -*- coding: utf-8 -*-
"""
app.models 包初始化文件。
(app.models package initialization file.)

此包集中了应用中所有 Pydantic 数据模型。这些模型用于：
- API 请求体验证与序列化。
- API 响应体验证与序列化。
- 内部数据结构定义。
(This package centralizes all Pydantic data models in the application. These models are used for:
- API request body validation and serialization.
- API response body validation and serialization.
- Internal data structure definition.)

通过从各个子模块导入模型，使得可以直接从 `app.models` 导入所需的任何模型。
例如 (e.g.): `from app.models import UserCreate, Token, ExamPaperResponse`
"""

# Explicitly import models from submodules to avoid F403 and F405 errors from ruff/pyflakes
# and to make it clear what is being exported.

from .config_models import (
    CloudflareIPsConfigPayload,
    DatabaseFilesConfigPayload,
    RateLimitConfigPayload,
    SettingsResponseModel,
    SettingsUpdatePayload,
    UserTypeRateLimitsPayload,
    UserValidationConfigPayload,
)
from .paper_models import (
    ExamPaperResponse,
    GradingResultResponse,
    HistoryItem,
    HistoryPaperDetailResponse,
    HistoryPaperQuestionClientView,
    PaperAdminView,
    PaperFullDetailModel,
    # UserAnswer, # Not defined in paper_models.py
    # PaperProgressData, # Not defined in paper_models.py
    PaperQuestionInternalDetail,
    PaperSubmissionPayload,
    UpdateProgressResponse,
)
from .qb_models import (
    DifficultyLevel,  # Enum
    LibraryIndexItem,
    QuestionBank,  # This is a model, not QuestionBankContent or QuestionBankMetadata directly
    # QuestionBankContent, # This is a concept, represented by QuestionBank.questions
    # QuestionBankMetadata, # This is a concept, represented by QuestionBank.metadata (which is LibraryIndexItem)
    # QuestionType, # Not defined as a separate enum in qb_models.py, part of QuestionModel
    QuestionModel,
)
from .token_models import (
    AuthStatusResponse,
    Token,
    TokenData,
)
from .user_models import (
    AdminUserUpdate,
    UserBase,
    UserCreate,
    UserDirectoryEntry,  # Added
    UserInDB,
    UserInDBBase,
    UserPasswordUpdate,
    UserProfileUpdate,
    UserPublicProfile,
    UserTag,  # Enum
    # UserUpdate, # Not actually defined in user_models.py, removed from import and __all__
)

__all__ = [
    # from config_models.py
    "RateLimitConfigPayload",
    "UserTypeRateLimitsPayload",
    "CloudflareIPsConfigPayload",
    "DatabaseFilesConfigPayload",
    "UserValidationConfigPayload",
    "SettingsResponseModel",
    "SettingsUpdatePayload",
    # from paper_models.py
    "ExamPaperResponse",
    "PaperSubmissionPayload",
    "UpdateProgressResponse",
    "GradingResultResponse",
    "HistoryItem",
    "HistoryPaperDetailResponse",
    "HistoryPaperQuestionClientView",
    "PaperAdminView",
    "PaperFullDetailModel",
    "PaperQuestionInternalDetail",
    # "UserAnswer", # Ensure this is defined in paper_models.py if exported
    # "PaperProgressData", # Ensure this is defined in paper_models.py if exported
    # from qb_models.py
    "DifficultyLevel",
    # "QuestionType", # If it's a separate Enum
    "QuestionModel",
    "LibraryIndexItem",
    "QuestionBank",  # Represents the full bank with metadata and questions
    # from token_models.py
    "Token",
    "TokenData",
    "AuthStatusResponse",
    # from user_models.py
    "UserBase",
    "UserCreate",
    # "UserUpdate", # Removed as it's not defined
    "UserInDBBase",
    "UserInDB",
    "UserPublicProfile",
    "UserProfileUpdate",
    "UserPasswordUpdate",
    "AdminUserUpdate",
    "UserTag",
    "UserDirectoryEntry",  # Added
]

# Dynamically clean up __all__ to ensure no undefined names are listed,
# though with explicit imports this should be less of an issue.
_imported_items = globals()
__all__ = sorted([name for name in __all__ if name in _imported_items])
