# -*- coding: utf-8 -*-
"""
试卷数据管理模块 (Paper Data Management Module)。

此模块定义了 `PaperCRUD` 类，用于处理所有与试卷相关的创建、读取、更新和删除 (CRUD) 操作。
它通过依赖注入的 `IDataStorageRepository` 与底层数据存储进行交互，并利用 `QuestionBankCRUD`
(或其接口) 来获取题目信息以生成试卷。
包含了用户答题、进度保存、自动批改、历史记录查看以及管理员对试卷的管理功能。

(This module defines the `PaperCRUD` class for handling all Create, Read, Update, and Delete (CRUD)
operations related to exam papers. It interacts with the underlying data storage through a
dependency-injected `IDataStorageRepository` and utilizes `QuestionBankCRUD` (or its interface)
to fetch question information for generating papers.
It includes functionalities for user exam taking, progress saving, auto-grading,
history viewing, and administrative management of papers.)
"""

# region 模块导入 (Module Imports)
import datetime
import logging
import random
import uuid
from datetime import timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import Request

from ..core.config import (  # 应用配置及常量 (App config and constants)
    CODE_INFO_OR_SPECIFIC_CONDITION,
    CODE_SUCCESS,
    DifficultyLevel,
    settings,
)
from ..core.interfaces import (
    IDataStorageRepository,
)  # 数据存储库接口 (Data storage repository interface)
from ..models.paper_models import (  # 试卷相关的Pydantic模型 (Paper-related Pydantic models)
    HistoryPaperQuestionClientView,
)
from ..utils.helpers import (  # 工具函数 (Utility functions)
    generate_random_hex_string_of_bytes,
    get_client_ip_from_request,
    shuffle_dictionary_items,
)

# endregion

# region 全局变量与初始化 (Global Variables & Initialization)
_paper_crud_logger = logging.getLogger(__name__)  # 获取本模块的日志记录器实例
PAPER_ENTITY_TYPE = "paper"  # 定义Paper实体的类型字符串，用于存储库操作
# endregion


# region 试卷数据管理类 (PaperCRUD)
class PaperCRUD:
    """
    试卷数据管理类 (PaperCRUD - Create, Read, Update, Delete)。
    通过 IDataStorageRepository 与底层数据存储交互。
    依赖 QuestionBankCRUD 来获取题库内容。

    (Paper Data Management Class (PaperCRUD - Create, Read, Update, Delete).
    Interacts with the underlying data storage via IDataStorageRepository.
    Relies on QuestionBankCRUD to fetch question bank content.)
    """

    def __init__(
        self,
        repository: IDataStorageRepository,
        qb_crud_instance: Optional[
            Any
        ] = None,  # 期望是 QuestionBankCRUD 的实例 (Expected: instance of QuestionBankCRUD)
    ):
        """
        初始化 PaperCRUD。
        (Initializes PaperCRUD.)

        参数 (Args):
            repository (IDataStorageRepository): 实现 IDataStorageRepository 接口的存储库实例。
                                                 (Instance of a repository implementing IDataStorageRepository.)
            qb_crud_instance (Optional[Any]): QuestionBankCRUD 的实例，用于获取题库信息。
                                              (Instance of QuestionBankCRUD for fetching question bank info.)
        """
        self.repository = repository
        if qb_crud_instance is None:
            _paper_crud_logger.critical(
                "PaperCRUD 初始化错误：未提供 QuestionBankCRUD 实例！ (PaperCRUD Init Error: QuestionBankCRUD instance not provided!)"
            )
            raise ValueError("QuestionBankCRUD instance is required for PaperCRUD.")
        self.qb_crud: Any = qb_crud_instance  # 类型注解Any，实际应为QbCRUD接口或具体类
        # (Type hint Any, should ideally be QbCRUD interface or concrete class)

    async def initialize_storage(self) -> None:
        """
        确保试卷的存储已初始化。应在应用启动时调用一次。
        (Ensures that the storage for papers is initialized. Should be called once during application startup.)
        """
        await self.repository.init_storage_if_needed(
            PAPER_ENTITY_TYPE, initial_data=[]
        )  # 使用空列表作为默认初始数据
        _paper_crud_logger.info(
            f"实体类型 '{PAPER_ENTITY_TYPE}' 的存储已初始化（如果需要）。 (Storage for entity type '{PAPER_ENTITY_TYPE}' initialized if needed.)"
        )

    async def create_new_paper(
        self,
        request: Request,
        user_uid: str,
        difficulty: DifficultyLevel,
        num_questions_override: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        创建一份新试卷，关联用户UID，并将其存储。题目从 qb_crud 获取。
        (Creates a new paper, associates it with a user UID, and stores it. Questions are fetched from qb_crud.)

        返回 (Returns):
            Dict[str, Any]: 包含新试卷ID、难度和题目列表（用于客户端展示）的字典。
                            (A dictionary containing the new paper's ID, difficulty, and list of questions
                             (formatted for client display).)
        异常 (Raises):
            ValueError: 如果请求的题库为空、题目数量无效或不满足要求。
                        (If the requested question bank is empty, or the number of questions is invalid or unmet.)
        """
        _paper_crud_logger.info(
            f"用户 '{user_uid}' 请求创建难度为 '{difficulty.value}' 的新试卷。 (User '{user_uid}' requesting new paper with difficulty '{difficulty.value}'.)"
        )
        full_question_bank = await self.qb_crud.get_question_bank_with_content(
            difficulty
        )

        if not full_question_bank or not full_question_bank.questions:
            _paper_crud_logger.error(
                f"请求了难度 '{difficulty.value}' 但其题库内容为空或元数据未加载。 (Requested difficulty '{difficulty.value}' but its question bank is empty or metadata not loaded.)"
            )
            raise ValueError(
                f"难度 '{difficulty.value}' 的题库不可用或为空。(Question bank for difficulty '{difficulty.value}' is unavailable or empty.)"
            )

        current_question_bank_content = [
            q.model_dump() for q in full_question_bank.questions
        ]
        current_question_bank_meta = full_question_bank.metadata

        num_questions_to_select = (
            num_questions_override
            if num_questions_override is not None
            else current_question_bank_meta.default_questions
        )
        num_questions_to_select = min(
            num_questions_to_select, current_question_bank_meta.total_questions
        )

        if not (0 < num_questions_to_select <= len(current_question_bank_content)):
            _paper_crud_logger.warning(
                f"请求的题目数量 {num_questions_to_select} 无效或超出题库 '{difficulty.value}' (共 {len(current_question_bank_content)} 题) 的范围。 (Requested number of questions {num_questions_to_select} is invalid or out of range for bank '{difficulty.value}' (total {len(current_question_bank_content)} questions).)"
            )
            raise ValueError(
                f"请求的题目数量 {num_questions_to_select} 无效或超出题库 '{difficulty.value}' 的范围。 (Requested number of questions {num_questions_to_select} is invalid or out of range for bank '{difficulty.value}'.)"
            )

        paper_uuid = str(uuid.uuid4())  # 生成唯一试卷ID
        new_paper_data: Dict[str, Any] = {  # 构建试卷基础数据结构
            "paper_id": paper_uuid,
            "user_uid": user_uid,
            "creation_time_utc": datetime.now(timezone.utc).isoformat(),
            "creation_ip": get_client_ip_from_request(
                request=request
            ),  # 移除CF IP参数，函数内部处理
            "difficulty": difficulty.value,
            "paper_questions": [],
            "score": None,
            "submitted_answers_card": None,
            "submission_time_utc": None,
            "submission_ip": None,
            "pass_status": None,
            "passcode": None,
            "last_update_time_utc": None,
            "last_update_ip": None,
        }

        selected_question_samples = random.sample(
            current_question_bank_content, num_questions_to_select
        )  # 随机抽题
        for item_data in selected_question_samples:  # 为每道题构造存储结构
            correct_choice_text = random.sample(
                item_data["correct_choices"], settings.num_correct_choices_to_select
            )[0]
            correct_choice_id = generate_random_hex_string_of_bytes(
                settings.generated_code_length_bytes
            )
            num_incorrect_to_sample = min(
                settings.num_incorrect_choices_to_select,
                len(item_data["incorrect_choices"]),
            )
            incorrect_choices_texts = random.sample(
                item_data["incorrect_choices"], num_incorrect_to_sample
            )
            incorrect_choices_with_ids = {
                generate_random_hex_string_of_bytes(
                    settings.generated_code_length_bytes
                ): text
                for text in incorrect_choices_texts
            }
            question_entry = {  # 试卷中单个问题的内部表示
                "body": item_data["body"],
                "correct_choices_map": {
                    correct_choice_id: correct_choice_text
                },  # 正确答案ID -> 文本
                "incorrect_choices_map": incorrect_choices_with_ids,  # 错误答案ID -> 文本
                "question_type": item_data.get(
                    "question_type", "single_choice"
                ),  # 题目类型
                "ref": item_data.get("ref"),  # 答案解析或参考
            }
            new_paper_data["paper_questions"].append(question_entry)

        created_paper_repo_record = await self.repository.create(
            PAPER_ENTITY_TYPE, new_paper_data
        )  # 通过存储库创建
        _paper_crud_logger.debug(
            f"用户 '{user_uid}' 的新试卷 {created_paper_repo_record.get('paper_id')} (难度: {difficulty.value}, 题目数: {num_questions_to_select}) 已创建并存储。 (New paper {created_paper_repo_record.get('paper_id')} for user '{user_uid}' (difficulty: {difficulty.value}, num_questions: {num_questions_to_select}) created and stored.)"
        )

        client_paper_response_paper_field: List[Dict[str, Any]] = (
            []
        )  # 为客户端构造题目列表
        for q_data in new_paper_data["paper_questions"]:
            all_choices = {
                **q_data.get("correct_choices_map", {}),
                **q_data.get("incorrect_choices_map", {}),
            }
            client_paper_response_paper_field.append(
                {
                    "body": q_data.get("body", "题目内容缺失 (Question body missing)"),
                    "choices": shuffle_dictionary_items(all_choices),  # 打乱选项顺序
                    "question_type": q_data.get("question_type"),  # 包含题目类型
                }
            )
        return {
            "paper_id": paper_uuid,
            "difficulty": difficulty,  # Pass the enum member directly
            "paper": client_paper_response_paper_field,
        }

    async def update_paper_progress(
        self,
        paper_id: UUID,
        user_uid: str,
        submitted_answers: List[Optional[str]],
        request: Request,
    ) -> Dict[str, Any]:
        """
        更新用户未完成试卷的答题进度。
        (Updates the progress of a user's unfinished paper.)
        """
        _paper_crud_logger.debug(
            f"用户 '{user_uid}' 尝试更新试卷 '{paper_id}' 的进度。 (User '{user_uid}' attempting to update progress for paper '{paper_id}'.)"
        )
        target_paper_record = await self.repository.get_by_id(
            PAPER_ENTITY_TYPE, str(paper_id)
        )

        if not target_paper_record or target_paper_record.get("user_uid") != user_uid:
            _paper_crud_logger.warning(
                f"试卷 '{paper_id}' 未找到或用户 '{user_uid}' 无权访问。 (Paper '{paper_id}' not found or user '{user_uid}' has no access.)"
            )
            return {
                "code": CODE_INFO_OR_SPECIFIC_CONDITION,
                "status_code": "NOT_FOUND",
                "message": "试卷未找到或无权访问。 (Paper not found or access denied.)",
            }

        if target_paper_record.get("pass_status") in [
            "PASSED",
            "FAILED",
        ]:  # 检查是否已完成
            _paper_crud_logger.info(
                f"试卷 '{paper_id}' 已完成，无法更新进度。 (Paper '{paper_id}' already completed, cannot update progress.)"
            )
            return {
                "code": CODE_INFO_OR_SPECIFIC_CONDITION,
                "status_code": "ALREADY_COMPLETED",
                "message": "此试卷已完成，无法更新。 (This paper has already been completed and cannot be updated.)",
                "paper_id": str(paper_id),
            }

        num_questions_in_paper = len(target_paper_record.get("paper_questions", []))
        if len(submitted_answers) > num_questions_in_paper:  # 检查答案数量
            _paper_crud_logger.warning(
                f"试卷 '{paper_id}' 提交答案数量 ({len(submitted_answers)}) 超出题目总数 ({num_questions_in_paper})。 (Number of submitted answers ({len(submitted_answers)}) for paper '{paper_id}' exceeds total questions ({num_questions_in_paper}).)"
            )
            return {
                "code": CODE_INFO_OR_SPECIFIC_CONDITION,
                "status_code": "INVALID_ANSWERS_LENGTH",
                "message": "提交的答案数量超出题目总数。 (Number of submitted answers exceeds total questions in the paper.)",
            }

        update_time = datetime.now(timezone.utc).isoformat()
        # 更新记录中的字段 (Update fields in the record)
        update_fields = {
            "submitted_answers_card": submitted_answers,
            "last_update_time_utc": update_time,
            "last_update_ip": get_client_ip_from_request(request=request),
        }
        updated_record = await self.repository.update(
            PAPER_ENTITY_TYPE, str(paper_id), update_fields
        )

        if not updated_record:
            _paper_crud_logger.error(
                f"在存储库中更新试卷 '{paper_id}' 失败。 (Failed to update paper '{paper_id}' in repository.)"
            )
            return {
                "code": CODE_INFO_OR_SPECIFIC_CONDITION,
                "status_code": "UPDATE_FAILED",
                "message": "保存试卷更新失败。 (Failed to persist paper updates.)",
            }

        _paper_crud_logger.info(
            f"用户 '{user_uid}' 的试卷 '{paper_id}' 进度已更新并存储。 (Progress for paper '{paper_id}' by user '{user_uid}' updated and stored.)"
        )
        return {
            "code": CODE_SUCCESS,
            "status_code": "PROGRESS_SAVED",
            "message": "试卷进度已成功保存。 (Paper progress saved successfully.)",
            "paper_id": str(paper_id),
            "last_update_time_utc": update_time,
        }

    async def grade_paper_submission(
        self,
        paper_id: UUID,
        user_uid: str,
        submitted_answers: List[Optional[str]],
        request: Request,
    ) -> Dict[str, Any]:
        """
        批改用户提交的试卷答案，计算得分，并确定通过状态。
        (Grades the user's submitted paper answers, calculates the score, and determines pass status.)
        """
        _paper_crud_logger.info(
            f"用户 '{user_uid}' 提交试卷 '{paper_id}' 进行批改。 (User '{user_uid}' submitting paper '{paper_id}' for grading.)"
        )
        target_paper_record = await self.repository.get_by_id(
            PAPER_ENTITY_TYPE, str(paper_id)
        )

        if not target_paper_record or target_paper_record.get("user_uid") != user_uid:
            _paper_crud_logger.warning(
                f"试卷 '{paper_id}' 未找到或用户 '{user_uid}' 无权访问。 (Paper '{paper_id}' not found or user '{user_uid}' has no access.)"
            )
            return {
                "code": CODE_INFO_OR_SPECIFIC_CONDITION,
                "status_code": "NOT_FOUND",
                "message": "试卷未找到或无权访问。",
            }

        if target_paper_record.get("pass_status"):  # 检查是否已批改
            _paper_crud_logger.info(
                f"试卷 '{paper_id}' 已被批改过。 (Paper '{paper_id}' has already been graded.)"
            )
            return {
                "code": CODE_INFO_OR_SPECIFIC_CONDITION,
                "status_code": "ALREADY_GRADED",
                "message": "此试卷已被批改。 (This paper has already been graded.)",
                "previous_result": target_paper_record.get("pass_status"),
                "score": target_paper_record.get("score"),
                "passcode": target_paper_record.get("passcode"),
            }

        paper_questions = target_paper_record.get("paper_questions", [])
        if not isinstance(paper_questions, list) or not paper_questions:
            _paper_crud_logger.error(
                f"试卷 '{paper_id}' 缺少 'paper_questions' 或为空，无法批改。 (Paper '{paper_id}' missing 'paper_questions' or empty, cannot grade.)"
            )
            return {
                "code": CODE_INFO_OR_SPECIFIC_CONDITION,
                "status_code": "INVALID_PAPER_STRUCTURE",
                "message": "试卷结构无效，无法批改。 (Paper structure is invalid, cannot grade.)",
            }

        if len(submitted_answers) != len(
            paper_questions
        ):  # 检查答案数量是否匹配题目数量
            _paper_crud_logger.warning(
                f"试卷 '{paper_id}' 提交答案数 ({len(submitted_answers)}) 与题目数 ({len(paper_questions)}) 不符。 (Number of submitted answers ({len(submitted_answers)}) for paper '{paper_id}' does not match number of questions ({len(paper_questions)}).)"
            )
            return {
                "code": CODE_INFO_OR_SPECIFIC_CONDITION,
                "status_code": "INVALID_SUBMISSION",
                "message": "提交的答案数量与题目总数不匹配。 (Number of submitted answers does not match total questions.)",
            }

        correct_answers_count = 0  # 计算正确答案数
        for i, q_data in enumerate(paper_questions):
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
                _paper_crud_logger.warning(
                    f"用户 '{user_uid}' 的试卷 '{paper_id}' 的问题索引 {i} 结构不正确，跳过计分。 (Question index {i} in paper '{paper_id}' for user '{user_uid}' has incorrect structure, skipping scoring.)"
                )

        current_time_utc_iso = datetime.now(timezone.utc).isoformat()
        score_percentage = (
            (correct_answers_count / len(paper_questions)) * 100
            if len(paper_questions) > 0
            else 0.0
        )

        # 更新试卷记录的字段 (Fields to update in the paper record)
        update_fields = {
            "score": correct_answers_count,
            "score_percentage": round(score_percentage, 2),
            "submitted_answers_card": submitted_answers,
            "submission_time_utc": current_time_utc_iso,
            "submission_ip": get_client_ip_from_request(request=request),
            "last_update_time_utc": current_time_utc_iso,
        }
        update_fields["last_update_ip"] = update_fields[
            "submission_ip"
        ]  # last_update_ip 与 submission_ip 相同

        result_payload: Dict[str, Any] = {
            "score": correct_answers_count,
            "score_percentage": round(score_percentage, 2),
        }

        if score_percentage >= settings.passing_score_percentage:  # 判断是否通过
            update_fields["pass_status"] = "PASSED"
            update_fields["passcode"] = generate_random_hex_string_of_bytes(
                settings.generated_code_length_bytes
            )
            result_payload.update(
                {
                    "code": CODE_SUCCESS,
                    "status_code": "PASSED",
                    "passcode": update_fields["passcode"],
                }
            )
            _paper_crud_logger.info(
                f"用户 '{user_uid}' 试卷 '{paper_id}' 通过，得分 {correct_answers_count}/{len(paper_questions)} ({score_percentage:.2f}%)。 (User '{user_uid}' paper '{paper_id}' PASSED, score {correct_answers_count}/{len(paper_questions)} ({score_percentage:.2f}%).)"
            )
        else:
            update_fields["pass_status"] = "FAILED"
            result_payload.update({"code": CODE_SUCCESS, "status_code": "FAILED"})
            _paper_crud_logger.info(
                f"用户 '{user_uid}' 试卷 '{paper_id}' 未通过，得分 {correct_answers_count}/{len(paper_questions)} ({score_percentage:.2f}%)。 (User '{user_uid}' paper '{paper_id}' FAILED, score {correct_answers_count}/{len(paper_questions)} ({score_percentage:.2f}%).)"
            )

        updated_record = await self.repository.update(
            PAPER_ENTITY_TYPE, str(paper_id), update_fields
        )
        if not updated_record:
            _paper_crud_logger.error(
                f"在存储库中更新已批改的试卷 '{paper_id}' 失败。 (Failed to update graded paper '{paper_id}' in repository.)"
            )
            return {
                "code": CODE_INFO_OR_SPECIFIC_CONDITION,
                "status_code": "GRADING_PERSISTENCE_FAILED",
                "message": "批改完成但保存结果失败。 (Grading complete but failed to save result.)",
            }

        return result_payload

    async def get_user_history(self, user_uid: str) -> List[Dict[str, Any]]:
        """
        获取指定用户的答题历史记录列表。
        (Retrieves the exam history list for a specified user.)
        """
        _paper_crud_logger.debug(
            f"获取用户 '{user_uid}' 的答题历史。 (Fetching exam history for user '{user_uid}'.)"
        )
        user_papers_data = await self.repository.query(
            PAPER_ENTITY_TYPE,
            conditions={"user_uid": user_uid},
            limit=settings.num_questions_per_paper_default * 5,
        )  # 限制返回数量

        history = []
        for paper_data in user_papers_data:
            if paper_data and isinstance(paper_data, dict):  # 确保数据有效
                history.append(
                    {
                        "paper_id": paper_data.get("paper_id"),
                        "difficulty": DifficultyLevel(
                            paper_data.get("difficulty", DifficultyLevel.hybrid.value)
                        ),
                        "score": paper_data.get("score"),
                        "score_percentage": paper_data.get("score_percentage"),
                        "pass_status": paper_data.get("pass_status"),
                        "submission_time_utc": paper_data.get("submission_time_utc"),
                    }
                )
        # 按提交时间（或创建时间，如果未提交）降序排序
        return sorted(
            history,
            key=lambda x: x.get("submission_time_utc")
            or x.get("creation_time_utc", ""),
            reverse=True,
        )

    async def get_user_paper_detail_for_history(
        self, paper_id_str: str, user_uid: str
    ) -> Optional[Dict[str, Any]]:
        """
        获取用户某次历史答题的详细情况。
        (Retrieves detailed information about a specific historical exam paper for a user.)
        """
        _paper_crud_logger.debug(
            f"用户 '{user_uid}' 请求历史试卷 '{paper_id_str}' 的详情。 (User '{user_uid}' requesting details for history paper '{paper_id_str}'.)"
        )
        paper_data = await self.repository.get_by_id(PAPER_ENTITY_TYPE, paper_id_str)

        if paper_data and paper_data.get("user_uid") == user_uid:  # 验证归属权
            history_questions: List[Dict[str, Any]] = []
            submitted_answers = paper_data.get("submitted_answers_card", [])
            if "paper_questions" in paper_data and isinstance(
                paper_data["paper_questions"], list
            ):
                for idx, q_internal in enumerate(
                    paper_data["paper_questions"]
                ):  # 构造客户端视图
                    all_choices_for_client = {
                        **q_internal.get("correct_choices_map", {}),
                        **q_internal.get("incorrect_choices_map", {}),
                    }
                    submitted_choice_id_for_this_q: Optional[str] = (
                        submitted_answers[idx]
                        if idx < len(submitted_answers)
                        and submitted_answers[idx] is not None
                        else None
                    )
                    q_type = q_internal.get("question_type", "single_choice")
                    detail_model = HistoryPaperQuestionClientView(
                        body=q_internal.get("body", "N/A"),
                        question_type=q_type,
                        choices=(
                            shuffle_dictionary_items(all_choices_for_client)
                            if q_type in ["single_choice", "multiple_choice"]
                            else None
                        ),
                        submitted_answer=submitted_choice_id_for_this_q,
                    )
                    history_questions.append(detail_model.model_dump(exclude_none=True))

            return {  # 返回包含所有必要信息的字典
                "paper_id": paper_data["paper_id"],
                "difficulty": DifficultyLevel(
                    paper_data.get("difficulty", DifficultyLevel.hybrid.value)
                ),
                "user_uid": user_uid,
                "paper_questions": history_questions,
                "score": paper_data.get("score"),
                "score_percentage": paper_data.get("score_percentage"),
                "submitted_answers_card": submitted_answers,
                "pass_status": paper_data.get("pass_status"),
                "passcode": paper_data.get("passcode"),
                "submission_time_utc": paper_data.get("submission_time_utc"),
            }
        _paper_crud_logger.warning(
            f"用户 '{user_uid}' 尝试访问不属于自己的试卷 '{paper_id_str}' 或试卷不存在。 (User '{user_uid}' tried to access paper '{paper_id_str}' not belonging to them or paper does not exist.)"
        )
        return None

    # --- Admin 相关方法 (Admin-related methods) ---
    async def admin_get_all_papers_summary(
        self, skip: int = 0, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        管理员获取所有试卷的摘要信息列表。
        (Admin: Get summary list of all papers.)
        """
        _paper_crud_logger.debug(
            f"管理员请求所有试卷摘要，skip={skip}, limit={limit}。 (Admin requesting all paper summaries, skip={skip}, limit={limit}.)"
        )
        all_papers = await self.repository.get_all(
            PAPER_ENTITY_TYPE, skip=skip, limit=limit
        )
        # 假设存储库的 get_all 支持排序或在此处进行排序 (Assume repository's get_all supports sorting or sort here)
        # 当前实现依赖于 get_all 返回的数据顺序，或在repository层面实现排序
        return (
            sorted(
                all_papers, key=lambda p: p.get("creation_time_utc", ""), reverse=True
            )
            if all_papers
            else []
        )

    async def admin_get_paper_detail(
        self, paper_id_str: str
    ) -> Optional[Dict[str, Any]]:
        """
        管理员获取指定ID试卷的完整详细信息。
        (Admin: Get full details of a specific paper by ID.)
        """
        _paper_crud_logger.debug(
            f"管理员请求试卷 '{paper_id_str}' 的详细信息。 (Admin requesting details for paper '{paper_id_str}'.)"
        )
        return await self.repository.get_by_id(PAPER_ENTITY_TYPE, paper_id_str)

    async def admin_delete_paper(self, paper_id_str: str) -> bool:
        """
        管理员删除指定ID的试卷。
        (Admin: Delete a specific paper by ID.)
        """
        _paper_crud_logger.info(
            f"管理员尝试删除试卷 '{paper_id_str}'。 (Admin attempting to delete paper '{paper_id_str}'.)"
        )
        deleted = await self.repository.delete(PAPER_ENTITY_TYPE, paper_id_str)
        if deleted:
            _paper_crud_logger.info(
                f"[Admin] 试卷 '{paper_id_str}' 已从存储库删除。 (Paper '{paper_id_str}' deleted from repository by admin.)"
            )
        else:
            _paper_crud_logger.warning(
                f"[Admin] 删除试卷 '{paper_id_str}' 失败（可能未找到）。 (Failed to delete paper '{paper_id_str}' (possibly not found) by admin.)"
            )
        return deleted


# endregion

__all__ = [
    "PaperCRUD",  # 导出PaperCRUD类 (Export PaperCRUD class)
    "PAPER_ENTITY_TYPE",  # 导出实体类型常量 (Export entity type constant)
]

if __name__ == "__main__":
    # 此模块不应作为主脚本执行。它定义了试卷数据的CRUD操作类。
    # (This module should not be executed as the main script. It defines the CRUD operations class for paper data.)
    _paper_crud_logger.info(
        f"模块 {__name__} 提供了试卷数据的CRUD操作类，不应直接执行。"
    )
    print(
        f"模块 {__name__} 提供了试卷数据的CRUD操作类，不应直接执行。 (This module provides CRUD operations class for paper data and should not be executed directly.)"
    )
