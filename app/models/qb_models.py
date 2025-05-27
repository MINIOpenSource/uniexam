# region 模块导入
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator, ValidationInfo, model_validator
import re # 用于正则表达式 (如果需要)
import logging # For QuestionBank validator
 
# 使用相对导入从同级 core 包导入配置和枚举
from ..core.config import DifficultyLevel, settings 
# endregion

# region 题库题目模型 (QuestionModel)
class QuestionModel(BaseModel):
    """
    题库中单个问题的模型。
    用于文件存储、Admin API的GET响应（作为列表元素）和POST请求体（添加新题目时）。
    包含了对未来题型（填空、解答）的预留字段。
    """
    body: str = Field(..., min_length=1, description="问题题干，对于填空题，使用 {blank} 表示填空位置")
    question_type: str = Field(
        default="single_choice", # 默认为单选题
        description="题目类型: 'single_choice', 'multiple_choice', 'fill_in_blank', 'essay_question'"
    )
    
    # --- 选择题相关字段 ---
    correct_choices: Optional[List[str]] = Field(
        None, # 对于非选择题，此字段可以为None或空
        min_items=1, # 如果提供，则至少有一个正确答案
        description="选择题的正确答案列表"
    )
    incorrect_choices: Optional[List[str]] = Field(
        None, # 对于非选择题，此字段可以为None或空
        min_items=1, # 如果提供，则至少有一个错误答案 (对于选择题通常需要3个)
        description="选择题的错误答案列表"
    )
    # 预留字段，用于指示多选题的正确答案数量，或单选题（通常为1）
    num_correct_to_select: Optional[int] = Field(
        None, ge=1,
        description="对于多选题，指示需要选择的正确答案数量；单选题通常为1"
    )

    # --- 填空题相关字段 ---
    correct_fillings: Optional[List[str]] = Field(
        None,
        min_items=1, # 如果是填空题且有标准答案，则至少一个
        description="填空题的正确填充答案列表 (可包含通配符，例如 '?')"
    )

    # --- 解答题和填空题的参考/解释字段 ---
    ref: Optional[str] = Field(
        None,
        description="答案解释、参考信息或评分标准，用于批阅时展示给批阅者参考"
    )

    @field_validator('correct_choices', 'incorrect_choices', mode='before')
    def _validate_choice_text(cls, v: Optional[List[Optional[str]]], info: ValidationInfo) -> Optional[List[Optional[str]]]:
        """验证选择题的选项文本（如果提供）不为空或仅包含空白。"""
        if v is None:
            return None
        validated_list = []
        for item_idx, item_value in enumerate(v):
            if item_value is not None and (not isinstance(item_value, str) or not item_value.strip()):
                raise ValueError(
                    f"字段 '{info.field_name}' 中索引 {item_idx} 处的选项内容不能为空字符串或纯空白"
                )
            validated_list.append(item_value)
        return validated_list

    @field_validator('correct_fillings', mode='before')
    def _validate_filling_text(cls, v: Optional[List[Optional[str]]]) -> Optional[List[Optional[str]]]:
        """验证填空题的填充答案文本（如果提供）不为空或仅包含空白。"""
        if v is None:
            return None
        for item_idx, item_value in enumerate(v):
            if item_value is not None and (not isinstance(item_value, str) or not item_value.strip()):
                raise ValueError(f"填空题的正确填充答案列表索引 {item_idx} 处的内容不能为空字符串或纯空白")
        return v
    
    @field_validator('question_type', mode='after') # mode='after' is the default if not specified
    def _validate_question_type(cls, v: str) -> str:
        """验证题目类型是否为预定义的值之一。"""
        allowed_types = ["single_choice", "multiple_choice", "fill_in_blank", "essay_question"]
        if v not in allowed_types:
            raise ValueError(f"无效的题目类型 '{v}'。允许的类型: {allowed_types}")
        return v

    # 可以添加 @model_validator (Pydantic v2) 或 @root_validator (Pydantic v1)
    # 来进行更复杂的跨字段验证，例如：
    # - 如果 question_type 是 'single_choice' 或 'multiple_choice'，则 correct_choices 和 incorrect_choices 必须提供。
    # - 如果 question_type 是 'fill_in_blank'，则 correct_fillings 必须提供。
    # - 确保 num_correct_to_select 与 correct_choices 长度一致（对于多选题）。
# endregion

# region 题库索引条目模型 (LibraryIndexItem)
class LibraryIndexItem(BaseModel):
    """
    题库索引文件 (index.json) 中单个题库的元数据模型。
    """
    id: str = Field(
        ...,
        min_length=1,
        max_length=50,
        pattern=r"^[a-zA-Z0-9_-]+$", # ID通常用作文件名，限制字符集
        description="题库的唯一ID (通常与文件名对应，例如 'easy', 不含.json后缀)"
    )
    name: str = Field(..., min_length=1, max_length=100, description="题库的显示名称 (例如 '简单难度')")
    description: Optional[str] = Field(None, max_length=500, description="题库的详细描述")
    default_questions: int = Field(
        default_factory=lambda: settings.num_questions_per_paper_default, # 从全局配置获取默认值
        ge=1,
        description="从此题库出题时的默认题目数量"
    )
    total_questions: int = Field(
        default=0,
        ge=0,
        description="此题库中实际的总题目数量 (通常由加载时或Admin操作动态更新)"
    )
    # difficulty_level: DifficultyLevel # id 字段已经可以映射到 DifficultyLevel

    @field_validator('id', mode='after') # mode='after' is the default
    def id_must_be_valid_difficulty_or_custom(cls, v: str) -> str:
        """
        验证ID是否是有效的DifficultyLevel值，或者允许自定义ID（如果业务需要）。
        当前实现要求ID必须是 DifficultyLevel 中的一个。
        """
        try:
            DifficultyLevel(v) # 尝试将其转换为 DifficultyLevel 枚举成员
        except ValueError:
            # 如果您的业务逻辑允许 DifficultyLevel 之外的自定义ID，可以在这里调整
            # 当前严格要求ID必须是预定义的难度级别之一
            raise ValueError(
                f"题库ID '{v}' 不是一个有效的预定义难度级别。 "
                f"有效级别: {[d.value for d in DifficultyLevel]}"
            )
        return v
# endregion

# region 完整题库模型 (QuestionBank) - 用于API响应或内部聚合
class QuestionBank(BaseModel):
    """
    表示一个完整的题库，包含其元数据和所有题目列表。
    主要用于API响应，例如管理员获取整个题库内容时。
    """
    metadata: LibraryIndexItem = Field(description="题库的元数据信息")
    questions: List[QuestionModel] = Field(description="题库中的所有题目列表")

    @model_validator(mode='after')
    def check_total_questions_match(self) -> 'QuestionBank':
        """验证元数据中的 total_questions 是否与实际题目列表长度一致。"""
        if self.metadata and self.questions is not None and self.metadata.total_questions != len(self.questions):
            # 可以选择是抛出错误，还是自动修正 metadata.total_questions
            # 这里选择记录警告，并以实际题目数量为准（如果需要修正，应在CRUD层进行）
            _qb_models_logger = logging.getLogger(__name__) # 获取logger
            _qb_models_logger.warning(
                f"题库 '{self.metadata.id}' 元数据中的 total_questions ({self.metadata.total_questions}) "
                f"与实际题目数量 ({len(self.questions)}) 不符。将以实际数量为准。"
            )
            # If you want to auto-correct:
            # self.metadata.total_questions = len(self.questions)
        return self
# endregion
