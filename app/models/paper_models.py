# -*- coding: utf-8 -*-
"""
试卷与答题相关的Pydantic模型模块。
(Pydantic Models Module for Exam Papers and Submissions.)

此模块定义了用于处理试卷创建、提交、批改、历史记录查看等功能所需的数据结构。
这些模型广泛应用于API的请求体、响应体以及内部数据传递。
(This module defines the data structures required for functionalities such as
paper creation, submission, grading, history viewing, etc. These models are
extensively used in API request/response bodies and for internal data transfer.)
"""
# region 模块导入 (Module Imports)
from typing import Dict, List, Optional, Union
from uuid import UUID  # 用于处理UUID类型 (For handling UUID type)

from pydantic import BaseModel, Field

from ..core.config import (
    DifficultyLevel,
)  # 导入难度级别枚举 (Import DifficultyLevel enum)
from .enums import PaperPassStatusEnum, QuestionTypeEnum  # 导入新的枚举类型

# endregion

# region 主应用 API 模型 - 试卷与答题相关 (Main App API Models - Paper & Submission Related)


class ExamQuestionClientView(BaseModel):
    """
    在 /get_exam 响应中，表示单个试题的结构（面向客户端）。
    (Structure for a single question in the /get_exam response (client-facing).)
    """

    body: str = Field(description="问题题干。(Question body.)")
    choices: Dict[str, str] = Field(
        description="选择题的选项 (ID到文本的映射，已打乱)。(Options for multiple-choice questions (map of ID to text, shuffled).)"
    )
    question_type: QuestionTypeEnum = Field(
        default=QuestionTypeEnum.SINGLE_CHOICE, description="题目类型。(Question type.)"
    )


class PaperSubmissionPayload(BaseModel):
    """
    用户提交试卷或更新进度的请求体模型。
    (Request body model for user submitting a paper or updating progress.)
    """

    paper_id: UUID = Field(
        ..., description="试卷的唯一标识符。(Unique identifier for the paper.)"
    )
    result: List[Optional[str]] = Field(  # 允许答案列表中的元素为None，表示未作答
        ...,
        description="所选选项ID的列表，按顺序对应每道题的答案。对于未作答的题目，发送null或空字符串。"
        "(List of selected option IDs, corresponding sequentially to each question's answer. "
        "For unanswered questions, send null or an empty string.)",
    )


class ExamPaperResponse(BaseModel):
    """
    GET /get_exam 接口的响应模型。
    用于返回新创建的试卷或用户恢复的未完成试卷。
    (Response model for the GET /get_exam endpoint.
    Used to return a newly created paper or an unfinished paper resumed by the user.)
    """

    paper_id: str = Field(
        description="试卷的唯一标识符 (UUID字符串)。(Unique identifier of the paper (UUID string).)"
    )
    difficulty: DifficultyLevel = Field(
        description="试卷的难度级别。(Difficulty level of the paper.)"
    )
    paper: List[ExamQuestionClientView] = (
        Field(  # 使用新定义的模型 (Use the newly defined model)
            description="试卷题目列表。(List of paper questions.)"
        )
    )
    # `submitted_answers_for_resume` 字段已移除，因为恢复逻辑通常在客户端处理或通过专用接口
    # (The `submitted_answers_for_resume` field has been removed, as resume logic is typically
    #  handled client-side or via a dedicated endpoint.)

    model_config = {  # Pydantic v2 配置 (Pydantic v2 config)
        "populate_by_name": True,  # 允许使用别名填充 (Allow population by alias)
    }


class GradingResultResponse(BaseModel):
    """
    POST /finish 接口的响应模型，表示试卷批改结果。
    (Response model for the POST /finish endpoint, representing the paper grading result.)
    """

    # The 'code: int' field is removed as HTTP status codes will be the primary indicator.
    # The 'status_code: str' (now PaperPassStatusEnum) remains to indicate business outcome like PASSED/FAILED.
    status_code: PaperPassStatusEnum = Field( # Now uses PaperPassStatusEnum
        description="文本状态描述 (例如 'PASSED', 'FAILED', 'ALREADY_GRADED')。(Textual status description (e.g., 'PASSED', 'FAILED', 'ALREADY_GRADED').)"
    )
    message: Optional[str] = Field(
        None,
        description="附带的操作结果消息。(Optional accompanying message for the operation result.)",
    )
    passcode: Optional[str] = Field(
        None,
        description="如果通过考试，生成的通行码 (可选)。(Passcode generated if the exam is passed (optional).)",
    )
    score: Optional[int] = Field(
        None,
        description="原始得分 (答对的题目数量)。(Raw score (number of correctly answered questions).)",
    )
    score_percentage: Optional[float] = Field(
        None, description="百分制得分 (0-100)。(Percentage score (0-100).)"
    )
    previous_result: Optional[str] = Field(
        None,
        description="如果试卷之前已被批改，此字段表示之前的状态。(If the paper was previously graded, this field indicates the prior status.)",
    )


class UpdateProgressResponse(BaseModel):
    """
    POST /update 接口的响应模型，表示试卷进度保存结果。
    (Response model for the POST /update endpoint, representing the paper progress saving result.)
    """

    code: int = Field(description="自定义业务状态码。(Custom business status code.)")
    status_code: str = Field(
        description="文本状态描述 (例如 'PROGRESS_SAVED')。(Textual status description (e.g., 'PROGRESS_SAVED').)"
    )
    message: str = Field(description="操作结果消息。(Operation result message.)")
    paper_id: Optional[str] = Field(
        None, description="相关的试卷ID。(Related paper ID.)"
    )
    last_update_time_utc: Optional[str] = Field(
        None,
        description="最后更新时间的ISO格式字符串。(ISO formatted string of the last update time.)",
    )


# endregion


# region 历史记录 API 模型 (History API Models)
class HistoryItem(BaseModel):
    """
    GET /history 接口中，用户历史记录列表里单个试卷的摘要信息。
    (Summary information for a single paper in the user's history list (GET /history endpoint).)
    """

    paper_id: str = Field(
        description="试卷的唯一标识符 (UUID字符串)。(Unique identifier of the paper (UUID string).)"
    )
    difficulty: DifficultyLevel = Field(
        description="试卷难度。(Difficulty level of the paper.)"
    )
    score: Optional[int] = Field(
        None, description="原始得分 (如果已批改)。(Raw score (if graded).)"
    )
    score_percentage: Optional[float] = Field(
        None, description="百分制得分 (如果已批改)。(Percentage score (if graded).)"
    )
    pass_status: Optional[PaperPassStatusEnum] = Field(  # 使用枚举 (Use enum)
        None,
        description="通过状态 ('PASSED', 'FAILED', 或 null)。(Pass status ('PASSED', 'FAILED', or null).)",
    )
    submission_time_utc: Optional[str] = Field(
        None,
        description="提交时间的ISO格式字符串 (如果已提交)。(ISO formatted string of submission time (if submitted).)",
    )


class HistoryPaperQuestionClientView(BaseModel):
    """
    GET /history_paper 接口中，单个问题的结构（面向客户端）。
    (Structure for a single question in the GET /history_paper endpoint (client-facing).)
    """

    body: str = Field(description="问题题干。(Question body.)")
    question_type: QuestionTypeEnum = Field(
        description="题目类型。(Question type.)"
    )  # 使用枚举 (Use enum)
    choices: Optional[Dict[str, str]] = Field(
        None,
        description="选择题的选项 (ID到文本的映射，已打乱)。(Options for multiple-choice questions (map of ID to text, shuffled).)",
    )
    submitted_answer: Optional[Union[str, List[str]]] = Field(
        None,
        description="用户对此题提交的答案 (选择题为选项ID，填空题为文本，多选为ID列表)。(User's submitted answer for this question (option ID for multiple choice, text for fill-in-the-blank, list of IDs for multi-select).)",
    )


class HistoryPaperDetailResponse(BaseModel):
    """
    GET /history_paper 接口的响应模型，获取指定历史试卷的详细信息。
    (Response model for the GET /history_paper endpoint, for detailed information of a specific historical paper.)
    """

    paper_id: str = Field(
        description="试卷的唯一标识符 (UUID字符串)。(Unique identifier of the paper (UUID string).)"
    )
    difficulty: DifficultyLevel = Field(
        description="试卷难度。(Difficulty level of the paper.)"
    )
    user_uid: str = Field(
        description="进行此试卷的用户的UID。(UID of the user who took this paper.)"
    )
    paper_questions: List[HistoryPaperQuestionClientView] = Field(
        description="试卷题目列表及其用户作答情况。(List of paper questions and user's answers.)"
    )
    score: Optional[int] = Field(
        None,
        description="原始总得分 (如果已完全批改)。(Total raw score (if fully graded).)",
    )
    score_percentage: Optional[float] = Field(
        None,
        description="百分制总得分 (如果已完全批改)。(Total percentage score (if fully graded).)",
    )
    submitted_answers_card: Optional[List[Optional[str]]] = Field(
        None,
        description="用户提交的完整原始答案卡 (选项ID列表，未答为null)。(User's complete original answer card (list of option IDs, null for unanswered).)",
    )
    pass_status: Optional[PaperPassStatusEnum] = Field(  # 使用枚举 (Use enum)
        None, description="最终通过状态。(Final pass status.)"
    )
    passcode: Optional[str] = Field(
        None, description="通行码 (如果通过)。(Passcode (if passed).)"
    )
    submission_time_utc: Optional[str] = Field(
        None, description="试卷提交时间。(Paper submission time.)"
    )


# endregion


# region Admin API 模型 - 试卷相关 (Admin API Models - Paper Related)
class PaperAdminView(BaseModel):
    """
    GET /admin/paper/all 接口中，单个试卷的摘要信息模型。
    (Summary information model for a single paper in the GET /admin/paper/all endpoint.)
    """

    paper_id: str = Field(description="试卷ID。(Paper ID.)")
    user_uid: Optional[str] = Field(None, description="用户UID。(User UID.)")
    creation_time_utc: str = Field(description="创建时间 (UTC)。(Creation time (UTC).)")
    creation_ip: str = Field(description="创建时IP地址。(Creation IP address.)")
    difficulty: Optional[str] = Field(None, description="试卷难度。(Paper difficulty.)")
    count: int = Field(
        description="该试卷的总题目数量。(Total number of questions in this paper.)"
    )
    finished_count: Optional[int] = Field(
        None,
        description="用户已作答的题目数量。(Number of questions answered by the user.)",
    )
    correct_count: Optional[int] = Field(
        None,
        description="用户答对的题目数量 (等同于已批改的score)。(Number of questions answered correctly by the user (same as graded score).)",
    )
    score: Optional[int] = Field(None, description="原始得分。(Raw score.)")
    score_percentage: Optional[float] = Field(
        None, description="百分制得分。(Percentage score.)"
    )
    submission_time_utc: Optional[str] = Field(
        None, description="提交时间 (UTC)。(Submission time (UTC).)"
    )
    submission_ip: Optional[str] = Field(
        None, description="提交时IP地址。(Submission IP address.)"
    )
    pass_status: Optional[PaperPassStatusEnum] = Field(
        None, description="通过状态。(Pass status.)"
    )  # 使用枚举 (Use enum)
    passcode: Optional[str] = Field(None, description="通行码。(Passcode.)")
    last_update_time_utc: Optional[str] = Field(
        None, description="最后更新时间 (UTC)。(Last update time (UTC).)"
    )
    last_update_ip: Optional[str] = Field(
        None, description="最后更新IP地址。(Last update IP address.)"
    )


class PaperQuestionInternalDetail(BaseModel):
    """
    在Admin API GET /admin/paper/ (获取单个试卷详情) 中，
    表示 `paper_questions` 字段里单个问题的内部存储结构。
    (Internal storage structure for a single question within the `paper_questions` field
    in the Admin API GET /admin/paper/ (get single paper details).)
    """

    body: str = Field(description="问题题干。(Question body.)")
    # 存储时，正确和错误选项分别存储，并包含其唯一ID
    # (When stored, correct and incorrect options are stored separately with their unique IDs)
    correct_choices_map: Optional[Dict[str, str]] = Field(
        None, description="正确选项 (ID -> 文本)。(Correct choices (ID -> text).)"
    )
    incorrect_choices_map: Optional[Dict[str, str]] = Field(
        None, description="错误选项 (ID -> 文本)。(Incorrect choices (ID -> text).)"
    )
    question_type: Optional[QuestionTypeEnum] = Field(  # 使用枚举 (Use enum)
        None,
        description="题目类型 (例如 'single_choice')。(Question type (e.g., 'single_choice').)",
    )
    ref: Optional[str] = Field(
        None,
        description="答案解析或参考信息。(Answer explanation or reference information.)",
    )


class PaperFullDetailModel(BaseModel):
    """
    GET /admin/paper/?paper_id={paper_id} 接口的响应模型，
    获取指定试卷的完整详细信息。
    (Response model for GET /admin/paper/?paper_id={paper_id} endpoint,
    for full details of a specific paper.)
    """

    paper_id: str = Field(description="试卷ID。(Paper ID.)")
    user_uid: Optional[str] = Field(None, description="用户UID。(User UID.)")
    creation_time_utc: str = Field(description="创建时间 (UTC)。(Creation time (UTC).)")
    creation_ip: str = Field(description="创建时IP地址。(Creation IP address.)")
    difficulty: Optional[str] = Field(None, description="试卷难度。(Paper difficulty.)")
    paper_questions: List[PaperQuestionInternalDetail] = Field(
        description="试卷的原始问题列表（含答案映射）。(List of original paper questions (with answer mappings).)"
    )
    score: Optional[int] = Field(None, description="原始得分。(Raw score.)")
    score_percentage: Optional[float] = Field(
        None, description="百分制得分。(Percentage score.)"
    )
    submitted_answers_card: Optional[List[Optional[str]]] = Field(
        None,
        description="用户提交的答案卡 (选项ID列表，未答为null)。(User's submitted answer card (list of option IDs, null for unanswered).)",
    )
    submission_time_utc: Optional[str] = Field(
        None, description="提交时间 (UTC)。(Submission time (UTC).)"
    )
    submission_ip: Optional[str] = Field(
        None, description="提交时IP地址。(Submission IP address.)"
    )
    pass_status: Optional[PaperPassStatusEnum] = Field(
        None, description="通过状态。(Pass status.)"
    )  # 使用枚举 (Use enum)
    passcode: Optional[str] = Field(None, description="通行码。(Passcode.)")
    last_update_time_utc: Optional[str] = Field(
        None, description="最后更新时间 (UTC)。(Last update time (UTC).)"
    )
    last_update_ip: Optional[str] = Field(
        None, description="最后更新IP地址。(Last update IP address.)"
    )


# endregion

__all__ = [
    "ExamQuestionClientView",  # 新增模型 (Added new model)
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

if __name__ == "__main__":
    # 此模块不应作为主脚本执行。它定义了与试卷和答题相关的Pydantic模型。
    # (This module should not be executed as the main script. It defines Pydantic models
    #  related to exam papers and submissions.)
    print(f"此模块 ({__name__}) 定义了与试卷和答题相关的Pydantic模型，不应直接执行。")
    print(
        f"(This module ({__name__}) defines Pydantic models related to exam papers and submissions and should not be executed directly.)"
    )
