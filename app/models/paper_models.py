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
import uuid  # Fixed F821: For PaperQuestionInternalDetail.internal_question_id default_factory
from typing import Dict, List, Optional, Union

# UUID from typing is also available, but direct import of uuid module is common for uuid.uuid4()
# from uuid import UUID  # 用于处理UUID类型 (For handling UUID type) -> This is fine, but default_factory needs the module
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

    paper_id: uuid.UUID = Field(
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
    paper: List[ExamQuestionClientView] = Field(
        description="试卷题目列表。(List of paper questions.)"
    )

    model_config = {
        "populate_by_name": True,
    }


class GradingResultResponse(BaseModel):
    """
    POST /finish 接口的响应模型，表示试卷批改结果。
    (Response model for the POST /finish endpoint, representing the paper grading result.)
    """

    status_code: PaperPassStatusEnum = Field(
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
    pending_manual_grading_count: Optional[int] = Field(
        None,
        description="等待人工批阅的主观题数量。若为0或None，则表示所有题目已自动或人工批改完毕。 (Number of subjective questions pending manual grading. If 0 or None, all questions are graded.)",
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
    pass_status: Optional[PaperPassStatusEnum] = Field(
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
    question_type: QuestionTypeEnum = Field(description="题目类型。(Question type.)")
    choices: Optional[Dict[str, str]] = Field(
        None,
        description="选择题的选项 (ID到文本的映射，已打乱)。(Options for multiple-choice questions (map of ID to text, shuffled).)",
    )
    submitted_answer: Optional[Union[str, List[str]]] = Field(
        None,
        description="用户对此题提交的答案 (选择题为选项ID或ID列表，填空题为文本列表，主观题为文本)。(User's submitted answer: option ID(s) for choice, list of texts for fill-in-blank, text for subjective.)",
    )
    student_subjective_answer: Optional[str] = Field(
        None,
        description="【主观题】学生提交的答案文本（如果题目是主观题）。(Student's submitted text answer if it's a subjective question.)",
    )
    standard_answer_text: Optional[str] = Field(
        None,
        description="【主观题】参考答案或要点（如果允许学生查看）。(Standard answer/key points for subjective questions, if student viewing is allowed.)",
    )
    manual_score: Optional[float] = Field(
        None,
        description="【主观题】此题目的人工批阅得分。(Manual score for this subjective question.)",
    )
    teacher_comment: Optional[str] = Field(
        None,
        description="【主观题】教师对此题的评语。(Teacher's comment on this subjective question.)",
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
    pass_status: Optional[PaperPassStatusEnum] = Field(
        None, description="最终通过状态。(Final pass status.)"
    )
    passcode: Optional[str] = Field(
        None, description="通行码 (如果通过)。(Passcode (if passed).)"
    )
    submission_time_utc: Optional[str] = Field(
        None, description="试卷提交时间。(Paper submission time.)"
    )
    pending_manual_grading_count: Optional[int] = Field(
        None,
        description="等待人工批阅的主观题数量。若为0或None，则表示所有题目已自动或人工批改完毕。 (Number of subjective questions pending manual grading. If 0 or None, all questions are graded.)",
    )
    subjective_questions_count: Optional[int] = Field(
        None,
        description="试卷中主观题的总数量。(Total number of subjective questions in the paper.)",
    )
    graded_subjective_questions_count: Optional[int] = Field(
        None,
        description="已人工批阅的主观题数量。(Number of manually graded subjective questions.)",
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
    )
    passcode: Optional[str] = Field(None, description="通行码。(Passcode.)")
    last_update_time_utc: Optional[str] = Field(
        None, description="最后更新时间 (UTC)。(Last update time (UTC).)"
    )
    last_update_ip: Optional[str] = Field(
        None, description="最后更新IP地址。(Last update IP address.)"
    )
    subjective_questions_count: Optional[int] = Field(
        0,
        description="试卷中主观题的总数量。(Total number of subjective questions in the paper.)",
    )
    graded_subjective_questions_count: Optional[int] = Field(
        0,
        description="已人工批阅的主观题数量。(Number of manually graded subjective questions.)",
    )


class PaperQuestionInternalDetail(BaseModel):
    """
    在Admin API GET /admin/paper/ (获取单个试卷详情) 中，
    表示 `paper_questions` 字段里单个问题的内部存储结构。
    包含题目内容、选择题答案映射、以及主观题的作答与批阅信息。
    (Internal storage structure for a single question within the `paper_questions` field.
    Includes question content, choice answer mappings, and subjective question answering/grading info.)
    """

    internal_question_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="试卷中此题目的唯一内部ID。(Unique internal ID for this question within the paper.)",
    )
    body: str = Field(description="问题题干。(Question body.)")
    correct_choices_map: Optional[Dict[str, str]] = Field(
        None,
        description="【选择题】正确选项 (ID -> 文本)。(Correct choices (ID -> text) for choice questions.)",
    )
    incorrect_choices_map: Optional[Dict[str, str]] = Field(
        None,
        description="【选择题】错误选项 (ID -> 文本)。(Incorrect choices (ID -> text) for choice questions.)",
    )
    question_type: Optional[QuestionTypeEnum] = Field(
        None,
        description="题目类型 (例如 'single_choice', 'essay_question')。(Question type (e.g., 'single_choice', 'essay_question').)",
    )
    standard_answer_text: Optional[str] = Field(
        None,
        description="【主观题】参考答案或答案要点。(Reference answer for subjective questions.)",
    )
    scoring_criteria: Optional[str] = Field(
        None,
        description="【主观题】评分标准。(Scoring criteria for subjective questions.)",
    )
    ref: Optional[str] = Field(
        None,
        description="通用答案解析或参考信息。(General answer explanation or reference information.)",
    )
    student_subjective_answer: Optional[str] = Field(
        None,
        description="学生提交的主观题答案文本。(Student's submitted text answer for subjective questions.)",
    )
    manual_score: Optional[float] = Field(
        None,
        description="人工批阅得分（针对单个主观题）。(Manual score for this subjective question.)",
    )
    teacher_comment: Optional[str] = Field(
        None,
        description="教师对学生此题作答的评语。(Teacher's comment on this subjective question.)",
    )
    is_graded_manually: Optional[bool] = Field(
        False,
        description="此主观题是否已被人工批阅。(Whether this subjective question has been manually graded.)",
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
        description="用户提交的答案卡 (选项ID列表，未答为null)。(User's complete original answer card (list of option IDs, null for unanswered).)",
    )
    submission_time_utc: Optional[str] = Field(
        None, description="提交时间 (UTC)。(Submission time (UTC).)"
    )
    submission_ip: Optional[str] = Field(
        None, description="提交时IP地址。(Submission IP address.)"
    )
    pass_status: Optional[PaperPassStatusEnum] = Field(
        None, description="通过状态。(Pass status.)"
    )
    passcode: Optional[str] = Field(None, description="通行码。(Passcode.)")
    last_update_time_utc: Optional[str] = Field(
        None, description="最后更新时间 (UTC)。(Last update time (UTC).)"
    )
    last_update_ip: Optional[str] = Field(
        None, description="最后更新IP地址。(Last update IP address.)"
    )
    subjective_questions_count: Optional[int] = Field(
        None,
        description="试卷中主观题的总数量。(Total number of subjective questions in the paper.)",
    )
    graded_subjective_questions_count: Optional[int] = Field(
        None,
        description="已人工批阅的主观题数量。(Number of manually graded subjective questions.)",
    )


# endregion

__all__ = [
    "ExamQuestionClientView",
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
    "PendingGradingPaperItem",
    "SubjectiveQuestionForGrading",
    "GradeSubmissionPayload",
]

# region Models for Grading Subjective Questions


class PendingGradingPaperItem(BaseModel):
    """
    待批阅试卷列表中的项目模型。
    (Item model for the list of papers pending manual grading.)
    """

    paper_id: str = Field(description="试卷ID。(Paper ID.)")
    user_uid: Optional[str] = Field(None, description="用户UID。(User UID.)")
    submission_time_utc: Optional[str] = Field(
        None, description="提交时间 (UTC)。(Submission time (UTC).)"
    )
    subjective_questions_count: Optional[int] = Field(
        0, description="主观题总数。(Total subjective questions.)"
    )
    pending_manual_grading_count: Optional[int] = Field(
        0, description="待批改主观题数量。(Pending subjective questions.)"
    )
    difficulty: Optional[str] = Field(None, description="试卷难度。(Paper difficulty.)")


class SubjectiveQuestionForGrading(BaseModel):
    """
    获取待批阅主观题详情时，单个题目的数据模型。
    (Data model for a single question when fetching subjective questions for grading.)
    """

    internal_question_id: str = Field(
        description="题目在试卷中的唯一内部ID。(Internal unique ID of the question in the paper.)"
    )
    body: str = Field(description="问题题干。(Question body.)")
    question_type: QuestionTypeEnum = Field(
        description="题目类型 (应为 essay_question)。(Question type (should be essay_question).)"
    )
    student_subjective_answer: Optional[str] = Field(
        None, description="学生提交的答案文本。(Student's submitted text answer.)"
    )
    standard_answer_text: Optional[str] = Field(
        None, description="参考答案或答案要点。(Standard answer or key points.)"
    )
    scoring_criteria: Optional[str] = Field(
        None, description="评分标准。(Scoring criteria.)"
    )
    manual_score: Optional[float] = Field(
        None, description="当前已保存的人工得分。(Current saved manual score.)"
    )
    teacher_comment: Optional[str] = Field(
        None, description="当前已保存的教师评语。(Current saved teacher comment.)"
    )
    is_graded_manually: Optional[bool] = Field(
        False, description="此题是否已批阅。(Whether this question has been graded.)"
    )


class GradeSubmissionPayload(BaseModel):
    """
    提交单个主观题批阅结果的请求体模型。
    (Request body model for submitting the grading result of a single subjective question.)
    """

    manual_score: float = Field(
        ...,
        ge=0,
        description="人工给出的分数 (非负)。(Manually assigned score (non-negative).)",
    )
    teacher_comment: Optional[str] = Field(
        None,
        max_length=1000,
        description="教师评语 (可选, 最长1000字符)。(Teacher's comment (optional, max 1000 chars).)",
    )


# endregion

if __name__ == "__main__":
    # 此模块不应作为主脚本执行。它定义了与试卷和答题相关的Pydantic模型。
    # (This module should not be executed as the main script. It defines Pydantic models
    #  related to exam papers and submissions.)
    print(f"此模块 ({__name__}) 定义了与试卷和答题相关的Pydantic模型，不应直接执行。")
    print(
        f"(This module ({__name__}) defines Pydantic models related to exam papers and submissions and should not be executed directly.)"
    )
