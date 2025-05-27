# -*- coding: utf-8 -*-
# region 模块导入
from typing import List, Optional, Dict, Any, Union
from uuid import UUID # 用于处理UUID类型
from pydantic import BaseModel, Field

# 使用相对导入
from .user_models import UserTag # 如果需要用户标签
from .qb_models import QuestionModel, LibraryIndexItem, QuestionBank # 导入题库模型
from ..core.config import DifficultyLevel 
# endregion

# region 主应用 API 模型 - 试卷与答题相关

class PaperSubmissionPayload(BaseModel):
    """用户提交试卷或更新进度的请求体模型。"""
    paper_id: UUID = Field(..., description="试卷的唯一标识符。")
    result: List[str] = Field(
        ...,
        description="所选选项ID的列表，按顺序对应每道题的答案。对于未作答的题目，可以发送null或空字符串，但列表长度应与题目数一致（用于/finish）或小于等于（用于/update）。"
    )

class ExamPaperResponse(BaseModel):
    """
    GET /get_exam 接口的响应模型。
    用于返回新创建的试卷或用户恢复的未完成试卷。
    """
    paper_id: str = Field(description="试卷的唯一标识符 (UUID字符串)")
    difficulty: DifficultyLevel = Field(description="试卷的难度级别")
    paper: List[Dict[str, Any]] = Field(
        description="试卷题目列表，每个题目包含 'body' 和 'choices' (选项ID到文本的映射)"
    )
    # `finished` 字段用于在恢复试卷时，向客户端提供已保存的答案卡
    # Pydantic 的 alias 功能使得在Python代码中使用 submitted_answers_for_resume，
    # 而在API的JSON响应中使用 "finished" 作为键名。
    submitted_answers_for_resume: Optional[List[Optional[str]]] = Field( # 允许答案列表中的元素为None
        None,
        alias="finished",
        description="如果恢复试卷，则为已提交的答案卡 (选项ID列表，未答题目为null)"
    )

    model_config = {
        "populate_by_name": True, # 允许通过别名进行填充
    }

class GradingResultResponse(BaseModel):
    """POST /finish 接口的响应模型，表示试卷批改结果。"""
    code: int = Field(description="自定义业务状态码 (例如 200 表示成功批改)")
    status_code: str = Field(description="文本状态描述 (例如 'PASSED', 'FAILED', 'ALREADY_GRADED')")
    message: Optional[str] = Field(None, description="附带的操作结果消息 (英文)")
    passcode: Optional[str] = Field(None, description="如果通过考试，生成的通行码 (可选)")
    score: Optional[int] = Field(None, description="原始得分 (答对的题目数量)")
    score_percentage: Optional[float] = Field(None, description="百分制得分 (0-100)") # 新增
    previous_result: Optional[str] = Field(None, description="如果试卷之前已被批改，此字段表示之前的状态")
    # 如果包含主观题，可能需要添加字段指示是否需要人工批阅

class UpdateProgressResponse(BaseModel):
    """POST /update 接口的响应模型，表示试卷进度保存结果。"""
    code: int = Field(description="自定义业务状态码")
    status_code: str = Field(description="文本状态描述 (例如 'PROGRESS_SAVED')")
    message: str = Field(description="操作结果消息 (英文)")
    paper_id: Optional[str] = Field(None, description="相关的试卷ID")
    last_update_time_utc: Optional[str] = Field(None, description="最后更新时间的ISO格式字符串")
# endregion

# region 历史记录 API 模型
class HistoryItem(BaseModel):
    """GET /history 接口中，用户历史记录列表里单个试卷的摘要信息。"""
    paper_id: str = Field(description="试卷的唯一标识符 (UUID字符串)")
    difficulty: DifficultyLevel = Field(description="试卷难度")
    score: Optional[int] = Field(None, description="原始得分 (如果已批改)")
    score_percentage: Optional[float] = Field(None, description="百分制得分 (如果已批改)") # 新增
    pass_status: Optional[str] = Field(None, description="通过状态 ('PASSED', 'FAILED', 或 null)")
    submission_time_utc: Optional[str] = Field(None, description="提交时间的ISO格式字符串 (如果已提交)") # 考虑添加此字段

class HistoryPaperQuestionClientView(BaseModel): # 重命名以区分内部结构
    """GET /history_paper 接口中，单个问题的结构（面向客户端）。"""
    body: str = Field(description="问题题干")
    question_type: str = Field(description="题目类型") # 新增
    choices: Optional[Dict[str, str]] = Field(None, description="选择题的选项 (ID到文本的映射，已打乱)")
    # 对于填空题，body 中包含 {blank}
    submitted_answer: Optional[Union[str, List[str]]] = Field(None, description="用户对此题提交的答案 (选择题为选项ID，填空题为文本，多选为ID列表)")
    # correct_answer_display: Optional[Union[str, List[str]]] = None # (可选) 用于显示正确答案文本
    # is_correct: Optional[bool] = None # (可选) 此题是否答对

class HistoryPaperDetailResponse(BaseModel):
    """GET /history_paper 接口的响应模型，获取指定历史试卷的详细信息。"""
    paper_id: str = Field(description="试卷的唯一标识符 (UUID字符串)")
    difficulty: DifficultyLevel = Field(description="试卷难度")
    user_uid: str = Field(description="进行此试卷的用户的UID") # 添加用户UID
    paper_questions: List[HistoryPaperQuestionClientView] = Field(description="试卷题目列表及其用户作答情况")
    score: Optional[int] = Field(None, description="原始总得分 (如果已完全批改)")
    score_percentage: Optional[float] = Field(None, description="百分制总得分 (如果已完全批改)")
    submitted_answers_card: Optional[List[Optional[str]]] = Field(None, description="用户提交的完整原始答案卡 (选项ID列表，未答为null)")
    pass_status: Optional[str] = Field(None, description="最终通过状态")
    passcode: Optional[str] = Field(None, description="通行码 (如果通过)")
    submission_time_utc: Optional[str] = Field(None, description="试卷提交时间")
    # 可以添加一个字段指示是否有题目等待人工批阅
    # needs_manual_grading: Optional[bool] = False
# endregion

# region Admin API 模型 - 试卷相关
class PaperAdminView(BaseModel):
    """
    GET /admin/paper/all 接口中，单个试卷的摘要信息模型。
    不包含详细的题目列表 (paper_questions) 和原始答题卡 (submitted_answers_card)。
    """
    paper_id: str
    user_uid: Optional[str] = None # 关联的用户UID
    creation_time_utc: str
    creation_ip: str
    difficulty: Optional[str] = None # 存储的是 difficulty.value
    
    count: int = Field(description="该试卷的总题目数量")
    finished_count: Optional[int] = Field(None, description="用户已作答的题目数量")
    correct_count: Optional[int] = Field(None, description="用户答对的题目数量 (等同于已批改的score)")
    
    score: Optional[int] = None # 原始得分
    score_percentage: Optional[float] = None # 百分制得分
    submission_time_utc: Optional[str] = None
    submission_ip: Optional[str] = None
    pass_status: Optional[str] = None
    passcode: Optional[str] = None
    last_update_time_utc: Optional[str] = None # 通过 /update 接口的最后更新时间
    last_update_ip: Optional[str] = None # 通过 /update 接口的最后更新IP

class PaperQuestionInternalDetail(BaseModel):
    """
    在Admin API GET /admin/paper/ (获取单个试卷详情) 中，
    表示 `paper_questions` 字段里单个问题的内部存储结构。
    包含答案ID到文本的映射，用于服务器端处理和Admin API的详细查看。
    """
    body: str
    # question_type: str # 应该从原始存储中获取
    correct_choices_map: Optional[Dict[str, str]] = None # 选择题
    incorrect_choices_map: Optional[Dict[str, str]] = None # 选择题
    # correct_fillings: Optional[List[str]] = None # 填空题
    # ref: Optional[str] = None # 填空/解答参考

class PaperFullDetailModel(BaseModel):
    """
    GET /admin/paper/?paper_id={paper_id} 接口的响应模型，
    获取指定试卷的完整详细信息。
    """
    paper_id: str
    user_uid: Optional[str] = None
    creation_time_utc: str
    creation_ip: str
    difficulty: Optional[str] = None
    paper_questions: List[PaperQuestionInternalDetail] # 试卷的原始问题列表（含答案映射）
    score: Optional[int] = None
    score_percentage: Optional[float] = None # 新增
    submitted_answers_card: Optional[List[Optional[str]]] = None # 用户提交的答案卡
    submission_time_utc: Optional[str] = None
    submission_ip: Optional[str] = None
    pass_status: Optional[str] = None
    passcode: Optional[str] = None
    last_update_time_utc: Optional[str] = None
    last_update_ip: Optional[str] = None
# endregion
