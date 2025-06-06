# -*- coding: utf-8 -*-
"""
题库相关的Pydantic模型模块。
(Pydantic Models Module for Question Banks.)

此模块定义了用于表示题库题目、题库索引元数据以及完整题库结构的数据模型。
这些模型用于数据验证、序列化以及在应用内部和API接口间传递题库信息。
(This module defines data models for representing question bank items,
question bank index metadata, and the overall structure of a question bank.
These models are used for data validation, serialization, and for passing
question bank information within the application and through API interfaces.)
"""
# region 模块导入 (Module Imports)
import logging
from typing import List, Optional

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator

from ..core.config import DifficultyLevel, settings  # 导入难度枚举和全局配置
from .enums import QuestionTypeEnum  # 导入题目类型枚举

# endregion

_qb_models_logger = logging.getLogger(__name__)  # 获取本模块的日志记录器实例


# region 题库题目模型 (QuestionModel)
class QuestionModel(BaseModel):
    """
    题库中单个问题的模型。
    (Model for a single question in the question bank.)
    用于文件存储、Admin API的GET响应（作为列表元素）和POST请求体（添加新题目时）。
    支持单选题、多选题（未来）、填空题（未来）和主观题（论述/简答题）。
    (Used for file storage, GET responses in Admin API (as a list element),
    and POST request bodies (when adding new questions).
    Supports single-choice, multiple-choice (future), fill-in-the-blank (future), and essay/subjective questions.)
    """

    body: str = Field(
        ...,
        min_length=1,
        description="问题题干，对于填空题，使用 {blank} 表示填空位置。(Question body; for fill-in-the-blank, use {blank} for blanks.)",
    )
    question_type: QuestionTypeEnum = Field(  # 使用枚举类型 (Use enum type)
        default=QuestionTypeEnum.SINGLE_CHOICE,  # 使用枚举成员作为默认值
        description="题目类型。(Question type.)",
    )

    # --- 选择题相关字段 (Multiple-choice related fields) ---
    correct_choices: Optional[List[str]] = Field(
        None,
        min_items=1,
        description="【选择题】正确答案选项的文本列表。对于主观题，此字段应为None。 (List of correct answer option texts for choice-based questions. Should be None for subjective questions.)",
    )
    incorrect_choices: Optional[List[str]] = Field(
        None,
        min_items=1,
        description="【选择题】错误答案选项的文本列表。对于主观题，此字段应为None。 (List of incorrect answer option texts for choice-based questions. Should be None for subjective questions.)",
    )
    num_correct_to_select: Optional[int] = Field(
        None,
        ge=1,
        description="【选择题】对于多选题，指示需要选择的正确答案数量；单选题通常为1。对于主观题，此字段应为None。 (For multiple-choice questions, indicates the number of correct answers to select; usually 1 for single-choice. Should be None for subjective questions.)",
    )

    # --- 填空题相关字段 (Fill-in-the-blank related fields) ---
    correct_fillings: Optional[List[str]] = Field(
        None,
        min_items=1,
        description="【填空题】正确填充答案的文本列表 (可包含通配符，例如 '?')。对于非填空题，此字段应为None。 (List of correct filling answer texts for fill-in-the-blank questions (can include wildcards, e.g., '?'). Should be None for other question types.)",
    )

    # --- 主观题相关字段 (Subjective/Essay Question related fields) ---
    standard_answer_text: Optional[str] = Field(
        None,
        description="【主观题】参考答案或答案要点。用于教师批阅时参考，或在回顾时展示给学生。对于非主观题，此字段应为None。 (Reference answer or key points for subjective questions. For teacher grading reference or student review. Should be None for non-subjective questions.)"
    )
    scoring_criteria: Optional[str] = Field(
        None,
        description="【主观题】评分标准或详细评分细则。供教师批阅时参考。对于非主观题，此字段应为None。 (Scoring criteria or detailed rubrics for subjective questions. For teacher grading reference. Should be None for non-subjective questions.)"
    )

    # --- 通用参考/解释字段 (General Reference/Explanation field) ---
    # 此字段可用于所有题型，提供额外的解释、解题思路或知识点链接等。
    # (This field can be used for all question types to provide additional explanations, solution approaches, or links to knowledge points.)
    ref: Optional[str] = Field(
        None,
        description="通用答案解释或参考信息 (可选)。例如，选择题的答案解析，或主观题的补充说明。 (General answer explanation or reference information (optional). E.g., explanation for multiple-choice answers, or supplementary notes for subjective questions.)",
    )

    @field_validator("correct_choices", "incorrect_choices", mode="before")
    def _validate_choice_text(
        cls, v: Optional[List[Optional[str]]], info: ValidationInfo
    ) -> Optional[List[Optional[str]]]:
        """
        验证选择题的选项文本（如果提供）不为空或仅包含空白。
        (Validates that choice text (if provided) is not empty or whitespace-only.)
        """
        if v is None:
            return None
        validated_list = []
        for item_idx, item_value in enumerate(v):
            if item_value is not None and (
                not isinstance(item_value, str) or not item_value.strip()
            ):
                raise ValueError(
                    f"字段 '{info.field_name}' 中索引 {item_idx} 处的选项内容不能为空字符串或纯空白。(Option at index {item_idx} in field '{info.field_name}' cannot be empty or whitespace.)"
                )
            validated_list.append(item_value)
        return validated_list

    @field_validator("correct_fillings", mode="before")
    def _validate_filling_text(
        cls, v: Optional[List[Optional[str]]]
    ) -> Optional[List[Optional[str]]]:
        """
        验证填空题的填充答案文本（如果提供）不为空或仅包含空白。
        (Validates that fill-in-the-blank answer text (if provided) is not empty or whitespace-only.)
        """
        if v is None:
            return None
        for item_idx, item_value in enumerate(v):
            if item_value is not None and (
                not isinstance(item_value, str) or not item_value.strip()
            ):
                raise ValueError(
                    f"填空题的正确填充答案列表索引 {item_idx} 处的内容不能为空字符串或纯空白。(Filling answer at index {item_idx} cannot be empty or whitespace.)"
                )
        return v

    # Pydantic V2+ handles enum validation automatically when the type hint is QuestionTypeEnum.
    # The custom validator _validate_question_type is no longer needed.


# endregion


# region 题库索引条目模型 (LibraryIndexItem Model)
class LibraryIndexItem(BaseModel):
    """
    题库索引文件 (`index.json`) 中单个题库的元数据模型。
    (Metadata model for a single question bank in the library index file (`index.json`).)
    """

    id: str = Field(
        ...,
        min_length=1,
        max_length=50,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="题库的唯一ID (通常与文件名对应，例如 'easy')。(Unique ID of the bank (usually corresponds to filename, e.g., 'easy').)",
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="题库的显示名称 (例如 '简单难度')。(Display name of the bank (e.g., 'Simple Difficulty').)",
    )
    description: Optional[str] = Field(
        None,
        max_length=500,
        description="题库的详细描述。(Detailed description of the bank.)",
    )
    default_questions: int = Field(
        default_factory=lambda: settings.num_questions_per_paper_default,
        ge=1,
        description="从此题库出题时的默认题目数量。(Default number of questions when generating a paper from this bank.)",
    )
    total_questions: int = Field(
        default=0,
        ge=0,
        description="此题库中实际的总题目数量 (通常动态更新)。(Actual total number of questions in this bank (usually updated dynamically).)",
    )

    @field_validator("id", mode="after")
    def id_must_be_valid_difficulty_or_custom(cls, v: str) -> str:
        """
        验证ID是否是有效的DifficultyLevel值。当前实现要求ID必须是DifficultyLevel中的一个。
        (Validates if the ID is a valid DifficultyLevel value. Current implementation requires ID to be one of DifficultyLevel.)
        """
        try:
            DifficultyLevel(v)  # 尝试将其转换为 DifficultyLevel 枚举成员
        except ValueError as e:
            raise ValueError(
                f"题库ID '{v}' 不是一个有效的预定义难度级别。有效级别 (Bank ID '{v}' is not a valid predefined difficulty level. Valid levels): {[d.value for d in DifficultyLevel]}"
            ) from e
        return v


# endregion


# region 完整题库模型 (QuestionBank Model) - 用于API响应或内部聚合
class QuestionBank(BaseModel):
    """
    表示一个完整的题库，包含其元数据和所有题目列表。
    主要用于API响应，例如管理员获取整个题库内容时。
    (Represents a complete question bank, including its metadata and list of all questions.
    Mainly used for API responses, e.g., when an admin fetches the entire content of a bank.)
    """

    metadata: LibraryIndexItem = Field(
        description="题库的元数据信息。(Metadata information of the bank.)"
    )
    questions: List[QuestionModel] = Field(
        description="题库中的所有题目列表。(List of all questions in the bank.)"
    )

    @model_validator(mode="after")
    def check_total_questions_match(self) -> "QuestionBank":
        """
        验证元数据中的 `total_questions` 是否与实际题目列表长度一致。
        (Validates if `total_questions` in metadata matches the actual length of the questions list.)
        """
        if (
            self.metadata
            and self.questions is not None
            and self.metadata.total_questions != len(self.questions)
        ):
            _qb_models_logger.warning(
                f"题库 '{self.metadata.id}' 元数据中的 total_questions ({self.metadata.total_questions}) "
                f"与实际题目数量 ({len(self.questions)}) 不符。建议在CRUD层修正。"
                f"(total_questions ({self.metadata.total_questions}) in metadata for bank '{self.metadata.id}' "
                f"does not match actual questions count ({len(self.questions)}). Consider fixing in CRUD layer.)"
            )
            # 实际修正通常在CRUD层完成，模型层主要负责验证和警告
            # (Actual correction is usually done in the CRUD layer; model layer primarily for validation and warnings.)
            # self.metadata.total_questions = len(self.questions) # 可选：模型层自我修正 (Optional: model layer self-correction)
        return self


# endregion

__all__ = [
    "QuestionModel",
    "LibraryIndexItem",
    "QuestionBank",
]

if __name__ == "__main__":
    # 此模块不应作为主脚本执行。它定义了与题库相关的Pydantic模型。
    # (This module should not be executed as the main script. It defines Pydantic models
    #  related to question banks.)
    _qb_models_logger.info(
        f"模块 {__name__} 定义了与题库相关的Pydantic模型，不应直接执行。"
    )
    print(
        f"模块 {__name__} 定义了与题库相关的Pydantic模型，不应直接执行。 (This module defines Pydantic models related to question banks and should not be executed directly.)"
    )
