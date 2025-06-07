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
import asyncio  # Added for asyncio.create_task
import datetime
import logging
import random
import uuid
from datetime import timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import Request

from ..core.config import (  # 应用配置及常量 (App config and constants)
    DifficultyLevel,
    settings,
)
from ..core.interfaces import (
    IDataStorageRepository,
)  # 数据存储库接口 (Data storage repository interface)
from ..models.enums import PaperPassStatusEnum, QuestionTypeEnum
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
        self.repository = repository
        if qb_crud_instance is None:
            _paper_crud_logger.critical(
                "PaperCRUD 初始化错误：未提供 QuestionBankCRUD 实例！"
            )
            raise ValueError("QuestionBankCRUD instance is required for PaperCRUD.")
        self.qb_crud: Any = qb_crud_instance

    async def initialize_storage(self) -> None:
        await self.repository.init_storage_if_needed(PAPER_ENTITY_TYPE, initial_data=[])
        _paper_crud_logger.info(
            f"实体类型 '{PAPER_ENTITY_TYPE}' 的存储已初始化（如果需要）。"
        )

    async def create_new_paper(
        self,
        request: Request,
        user_uid: str,
        difficulty: DifficultyLevel,
        num_questions_override: Optional[int] = None,
    ) -> Dict[str, Any]:
        _paper_crud_logger.info(
            f"用户 '{user_uid}' 请求创建难度为 '{difficulty.value}' 的新试卷。"
        )
        full_question_bank = await self.qb_crud.get_question_bank_with_content(
            difficulty
        )

        if not full_question_bank or not full_question_bank.questions:
            _paper_crud_logger.error(
                f"请求了难度 '{difficulty.value}' 但其题库内容为空或元数据未加载。"
            )
            raise ValueError(f"难度 '{difficulty.value}' 的题库不可用或为空。")

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
                f"请求的题目数量 {num_questions_to_select} 无效或超出题库 '{difficulty.value}' (共 {len(current_question_bank_content)} 题) 的范围。"
            )
            raise ValueError(
                f"请求的题目数量 {num_questions_to_select} 无效或超出题库 '{difficulty.value}' 的范围。"
            )

        paper_uuid = str(uuid.uuid4())
        new_paper_data: Dict[str, Any] = {
            "paper_id": paper_uuid,
            "user_uid": user_uid,
            "creation_time_utc": datetime.now(timezone.utc).isoformat(),
            "creation_ip": get_client_ip_from_request(request=request),
            "difficulty": difficulty.value,
            "paper_questions": [],
            "score": None,  # 将代表客观题得分，或在最终批改后代表总分
            "total_score": None,  # 新增：用于存储客观题+主观题的总分
            "score_percentage": None,
            "submitted_answers_card": None,
            "submission_time_utc": None,
            "submission_ip": None,
            "pass_status": PaperPassStatusEnum.PENDING.value,  # 初始状态为待处理
            "passcode": None,
            "last_update_time_utc": None,
            "last_update_ip": None,
            "subjective_questions_count": 0,
            "graded_subjective_questions_count": 0,
            "pending_manual_grading_count": 0,
        }

        selected_question_samples = random.sample(
            current_question_bank_content, num_questions_to_select
        )

        subjective_questions_count = 0
        for item_data in selected_question_samples:
            question_type_str = item_data.get(
                "question_type", QuestionTypeEnum.SINGLE_CHOICE.value
            )
            if question_type_str == QuestionTypeEnum.ESSAY_QUESTION.value:
                subjective_questions_count += 1

            question_entry = {
                "internal_question_id": str(uuid.uuid4()),
                "body": item_data["body"],
                "question_type": question_type_str,
                "ref": item_data.get("ref"),
                "standard_answer_text": item_data.get("standard_answer_text"),
                "scoring_criteria": item_data.get("scoring_criteria"),
                "correct_choices_map": None,
                "incorrect_choices_map": None,
                "student_subjective_answer": None,
                "manual_score": None,
                "teacher_comment": None,
                "is_graded_manually": False,
            }

            if question_type_str == QuestionTypeEnum.SINGLE_CHOICE.value:
                correct_choice_text = (
                    random.sample(
                        item_data.get("correct_choices", ["默认正确答案"]),
                        settings.num_correct_choices_to_select,
                    )[0]
                    if item_data.get("correct_choices")
                    else "默认正确答案"
                )
                correct_choice_id = generate_random_hex_string_of_bytes(
                    settings.generated_code_length_bytes
                )
                num_incorrect_to_sample = min(
                    settings.num_incorrect_choices_to_select,
                    len(item_data.get("incorrect_choices", [])),
                )
                incorrect_choices_texts = random.sample(
                    item_data.get("incorrect_choices", []), num_incorrect_to_sample
                )
                incorrect_choices_with_ids = {
                    generate_random_hex_string_of_bytes(
                        settings.generated_code_length_bytes
                    ): text
                    for text in incorrect_choices_texts
                }
                question_entry["correct_choices_map"] = {
                    correct_choice_id: correct_choice_text
                }
                question_entry["incorrect_choices_map"] = incorrect_choices_with_ids

            new_paper_data["paper_questions"].append(question_entry)

        new_paper_data["subjective_questions_count"] = subjective_questions_count
        new_paper_data["pending_manual_grading_count"] = subjective_questions_count

        created_paper_repo_record = await self.repository.create(
            PAPER_ENTITY_TYPE, new_paper_data
        )
        _paper_crud_logger.debug(
            f"用户 '{user_uid}' 的新试卷 {created_paper_repo_record.get('paper_id')} (难度: {difficulty.value}, 题目数: {num_questions_to_select}) 已创建并存储。"
        )

        client_paper_response_paper_field: List[Dict[str, Any]] = []
        for q_data in new_paper_data["paper_questions"]:
            all_choices = {
                **q_data.get("correct_choices_map", {}),
                **q_data.get("incorrect_choices_map", {}),
            }
            client_paper_response_paper_field.append(
                {
                    "internal_question_id": q_data.get(
                        "internal_question_id"
                    ),  # Pass internal_question_id to client
                    "body": q_data.get("body", "题目内容缺失"),
                    "choices": (
                        shuffle_dictionary_items(all_choices)
                        if q_data.get("question_type")
                        == QuestionTypeEnum.SINGLE_CHOICE.value
                        else None
                    ),
                    "question_type": q_data.get("question_type"),
                }
            )
        return {
            "paper_id": paper_uuid,
            "difficulty": difficulty,
            "paper": client_paper_response_paper_field,
        }

    async def update_paper_progress(
        self,
        paper_id: UUID,
        user_uid: str,
        submitted_answers: List[Optional[str]],  # For choice questions
        # subjective_answers: Dict[str, str], # For subjective questions, keyed by internal_question_id
        request: Request,
    ) -> Dict[str, Any]:
        # Note: This method currently only saves objective answers via submitted_answers.
        # Subjective answers are saved via grade_subjective_question or a future dedicated save endpoint.
        _paper_crud_logger.debug(
            f"用户 '{user_uid}' 尝试更新试卷 '{paper_id}' 的进度。"
        )
        target_paper_record = await self.repository.get_by_id(
            PAPER_ENTITY_TYPE, str(paper_id)
        )

        if not target_paper_record or target_paper_record.get("user_uid") != user_uid:
            _paper_crud_logger.warning(
                f"试卷 '{paper_id}' 未找到或用户 '{user_uid}' 无权访问。"
            )
            return {"status_code": "NOT_FOUND", "message": "试卷未找到或无权访问。"}

        current_pass_status = target_paper_record.get("pass_status")
        if current_pass_status and current_pass_status not in [
            PaperPassStatusEnum.PENDING.value,
            PaperPassStatusEnum.PENDING_REVIEW.value,
        ]:
            _paper_crud_logger.info(
                f"试卷 '{paper_id}' 状态为 {current_pass_status}，无法更新进度。"
            )
            return {
                "status_code": "ALREADY_COMPLETED_OR_GRADING",
                "message": "此试卷已提交或正在批阅中，无法更新进度。",
                "paper_id": str(paper_id),
            }

        paper_questions = target_paper_record.get("paper_questions", [])
        num_questions_in_paper = len(paper_questions)

        # Update submitted_answers_card (for objective questions)
        # Ensure submitted_answers list matches the total number of questions, padding with None if necessary
        # This part primarily handles objective question answers. Subjective answers are handled differently.
        processed_answers = [None] * num_questions_in_paper
        for i, q_data in enumerate(paper_questions):
            if (
                q_data.get("question_type") == QuestionTypeEnum.SINGLE_CHOICE.value
            ):  # Only process for choice questions here
                if i < len(submitted_answers):
                    processed_answers[i] = submitted_answers[i]
            # For subjective questions, student_subjective_answer is updated elsewhere (e.g. during grading or a dedicated save)

        update_time = datetime.now(timezone.utc).isoformat()
        update_fields = {
            "submitted_answers_card": processed_answers,  # Save processed answers for all questions
            "last_update_time_utc": update_time,
            "last_update_ip": get_client_ip_from_request(request=request),
        }

        # Persist changes
        updated_record = await self.repository.update(
            PAPER_ENTITY_TYPE, str(paper_id), update_fields
        )

        if not updated_record:
            _paper_crud_logger.error(f"在存储库中更新试卷 '{paper_id}' 失败。")
            return {"status_code": "UPDATE_FAILED", "message": "保存试卷更新失败。"}

        _paper_crud_logger.info(
            f"用户 '{user_uid}' 的试卷 '{paper_id}' 进度已更新并存储。"
        )
        return {
            "status_code": "PROGRESS_SAVED",
            "message": "试卷进度已成功保存。",
            "paper_id": str(paper_id),
            "last_update_time_utc": update_time,
        }

    async def grade_paper_submission(
        self,
        paper_id: UUID,
        user_uid: str,
        submitted_answers: List[
            Optional[str]
        ],  # Contains answers for objective questions
        # And text for subjective questions, keyed by internal_question_id
        request: Request,
    ) -> Dict[str, Any]:
        _paper_crud_logger.info(f"用户 '{user_uid}' 提交试卷 '{paper_id}' 进行批改。")
        target_paper_record = await self.repository.get_by_id(
            PAPER_ENTITY_TYPE, str(paper_id)
        )

        if not target_paper_record or target_paper_record.get("user_uid") != user_uid:
            _paper_crud_logger.warning(
                f"试卷 '{paper_id}' 未找到或用户 '{user_uid}' 无权访问。"
            )
            return {"status_code": "NOT_FOUND", "message": "试卷未找到或无权访问。"}

        current_pass_status = target_paper_record.get("pass_status")
        if current_pass_status and current_pass_status not in [
            PaperPassStatusEnum.PENDING.value,
            PaperPassStatusEnum.PENDING_REVIEW.value,
        ]:
            _paper_crud_logger.info(
                f"试卷 '{paper_id}' 已被批改过或处于非可提交状态 ({current_pass_status})。"
            )
            return {
                "status_code": "ALREADY_GRADED_OR_INVALID_STATE",
                "message": "此试卷已被批改或当前状态无法提交。",
                "previous_result": current_pass_status,
                "score": target_paper_record.get("score"),
                "passcode": target_paper_record.get("passcode"),
                "pending_manual_grading_count": target_paper_record.get(
                    "pending_manual_grading_count", 0
                ),
            }

        paper_questions = target_paper_record.get("paper_questions", [])
        if not isinstance(paper_questions, list) or not paper_questions:
            _paper_crud_logger.error(
                f"试卷 '{paper_id}' 缺少 'paper_questions' 或为空，无法批改。"
            )
            return {
                "status_code": "INVALID_PAPER_STRUCTURE",
                "message": "试卷结构无效，无法批改。",
            }

        if len(submitted_answers) != len(paper_questions):
            _paper_crud_logger.warning(
                f"试卷 '{paper_id}' 提交答案数 ({len(submitted_answers)}) 与题目数 ({len(paper_questions)}) 不符。"
            )
            return {
                "status_code": "INVALID_SUBMISSION",
                "message": "提交的答案数量与题目总数不匹配。",
            }

        objective_questions_total = 0
        correct_objective_answers_count = 0

        internal_paper_questions = target_paper_record.get("paper_questions", [])
        for i, q_data in enumerate(internal_paper_questions):
            if not isinstance(q_data, dict):
                continue

            q_type = q_data.get("question_type")
            if q_type == QuestionTypeEnum.SINGLE_CHOICE.value:
                objective_questions_total += 1
                correct_map = q_data.get("correct_choices_map")
                if (
                    correct_map
                    and isinstance(correct_map, dict)
                    and len(correct_map) == 1
                ):
                    correct_choice_id = list(correct_map.keys())[0]
                    if (
                        i < len(submitted_answers)
                        and submitted_answers[i] == correct_choice_id
                    ):
                        correct_objective_answers_count += 1
            elif q_type == QuestionTypeEnum.ESSAY_QUESTION.value:
                if i < len(submitted_answers) and submitted_answers[i] is not None:
                    # Store student's subjective answer text
                    internal_paper_questions[i]["student_subjective_answer"] = str(
                        submitted_answers[i]
                    )
            # Other types like MULTIPLE_CHOICE, FILL_IN_BLANK would need their own grading logic here

        current_time_utc_iso = datetime.now(timezone.utc).isoformat()
        objective_score_percentage = (
            (correct_objective_answers_count / objective_questions_total) * 100
            if objective_questions_total > 0
            else 0.0
        )

        update_fields = {
            "score": correct_objective_answers_count,  # Represents objective score at this stage
            "score_percentage": round(objective_score_percentage, 2),
            "submitted_answers_card": submitted_answers,
            "paper_questions": internal_paper_questions,  # Persist updated subjective answers
            "submission_time_utc": current_time_utc_iso,
            "submission_ip": get_client_ip_from_request(request=request),
            "last_update_time_utc": current_time_utc_iso,
        }
        update_fields["last_update_ip"] = update_fields["submission_ip"]

        # Update paper record with objective scores and submitted subjective answers first
        await self.repository.update(PAPER_ENTITY_TYPE, str(paper_id), update_fields)

        # Re-fetch the record to get the latest pending_manual_grading_count (which was set at creation)
        # and subjective_questions_count
        updated_target_paper_record = await self.repository.get_by_id(
            PAPER_ENTITY_TYPE, str(paper_id)
        )
        if (
            not updated_target_paper_record
        ):  # Should not happen if previous update succeeded
            _paper_crud_logger.error(f"提交后无法重新获取试卷 '{paper_id}'。")
            return {
                "status_code": "INTERNAL_ERROR",
                "message": "处理提交时发生内部错误。",
            }

        result_payload: Dict[str, Any] = {
            "score": correct_objective_answers_count,
            "score_percentage": round(objective_score_percentage, 2),
            "pending_manual_grading_count": updated_target_paper_record.get(
                "pending_manual_grading_count", 0
            ),
        }

        has_pending_subjective = (
            updated_target_paper_record.get("pending_manual_grading_count", 0) > 0
        )

        final_pass_status_for_update = ""
        if has_pending_subjective:
            final_pass_status_for_update = PaperPassStatusEnum.PENDING_REVIEW.value
            result_payload["status_code"] = PaperPassStatusEnum.PENDING_REVIEW.value
            result_payload["message"] = (
                "客观题已自动批改。试卷包含主观题，请等待人工批阅完成获取最终结果。"
            )
            _paper_crud_logger.info(
                f"用户 '{user_uid}' 试卷 '{paper_id}' 客观题得分 {correct_objective_answers_count}/{objective_questions_total} ({objective_score_percentage:.2f}%)，包含 {updated_target_paper_record.get('pending_manual_grading_count')} 道主观题待批阅。"
            )
        else:
            # If no subjective questions were pending (e.g. all objective, or all subjective already graded through another flow)
            # then this objective score is the final score.
            if objective_score_percentage >= settings.passing_score_percentage:
                final_pass_status_for_update = PaperPassStatusEnum.PASSED.value
                passcode = generate_random_hex_string_of_bytes(
                    settings.generated_code_length_bytes
                )
                update_fields["passcode"] = passcode  # Add passcode to update_fields
                result_payload.update(
                    {
                        "status_code": PaperPassStatusEnum.PASSED.value,
                        "passcode": passcode,
                        "message": "恭喜，您已通过本次考试！",
                    }
                )
                _paper_crud_logger.info(
                    f"用户 '{user_uid}' 试卷 '{paper_id}' 通过，得分 {correct_objective_answers_count}/{objective_questions_total} ({objective_score_percentage:.2f}%)。"
                )
            else:
                final_pass_status_for_update = PaperPassStatusEnum.FAILED.value
                result_payload.update(
                    {
                        "status_code": PaperPassStatusEnum.FAILED.value,
                        "message": "很遗憾，您未能通过本次考试。",
                    }
                )
                _paper_crud_logger.info(
                    f"用户 '{user_uid}' 试卷 '{paper_id}' 未通过，得分 {correct_objective_answers_count}/{objective_questions_total} ({objective_score_percentage:.2f}%)。"
                )

        update_fields["pass_status"] = final_pass_status_for_update

        # Final update with pass_status
        final_updated_record = await self.repository.update(
            PAPER_ENTITY_TYPE,
            str(paper_id),
            {
                "pass_status": final_pass_status_for_update,
                "passcode": update_fields.get("passcode"),
            },
        )
        if not final_updated_record:
            _paper_crud_logger.error(
                f"在存储库中更新试卷 '{paper_id}' 的最终状态失败。"
            )
            return {
                "status_code": "GRADING_PERSISTENCE_FAILED",
                "message": "批改完成但保存最终状态失败。",
            }

        return result_payload

    async def get_user_history(self, user_uid: str) -> List[Dict[str, Any]]:
        _paper_crud_logger.debug(f"获取用户 '{user_uid}' 的答题历史。")
        user_papers_data = await self.repository.query(
            PAPER_ENTITY_TYPE,
            conditions={"user_uid": user_uid},
            limit=settings.num_questions_per_paper_default * 5,
        )
        history = []
        for paper_data in user_papers_data:
            if paper_data and isinstance(paper_data, dict):
                history.append(
                    {
                        "paper_id": paper_data.get("paper_id"),
                        "difficulty": DifficultyLevel(
                            paper_data.get("difficulty", DifficultyLevel.hybrid.value)
                        ),
                        "score": paper_data.get(
                            "score"
                        ),  # This is objective score or final total if finalized
                        "total_score": paper_data.get(
                            "total_score"
                        ),  # Show total_score if available
                        "score_percentage": paper_data.get("score_percentage"),
                        "pass_status": paper_data.get("pass_status"),
                        "submission_time_utc": paper_data.get("submission_time_utc"),
                        "subjective_questions_count": paper_data.get(
                            "subjective_questions_count"
                        ),
                        "pending_manual_grading_count": paper_data.get(
                            "pending_manual_grading_count"
                        ),
                    }
                )
        return sorted(
            history,
            key=lambda x: x.get("submission_time_utc")
            or x.get("creation_time_utc", ""),
            reverse=True,
        )

    async def get_user_paper_detail_for_history(
        self, paper_id_str: str, user_uid: str
    ) -> Optional[Dict[str, Any]]:
        _paper_crud_logger.debug(
            f"用户 '{user_uid}' 请求历史试卷 '{paper_id_str}' 的详情。"
        )
        paper_data = await self.repository.get_by_id(PAPER_ENTITY_TYPE, paper_id_str)

        if paper_data and paper_data.get("user_uid") == user_uid:
            history_questions: List[Dict[str, Any]] = []
            submitted_answers = paper_data.get("submitted_answers_card", [])
            paper_questions_internal = paper_data.get("paper_questions", [])
            if isinstance(paper_questions_internal, list):
                for idx, q_internal in enumerate(paper_questions_internal):
                    if not isinstance(q_internal, dict):
                        continue
                    all_choices_for_client = {
                        **q_internal.get("correct_choices_map", {}),
                        **q_internal.get("incorrect_choices_map", {}),
                    }
                    submitted_ans_for_this_q = (
                        submitted_answers[idx] if idx < len(submitted_answers) else None
                    )
                    q_type_val = q_internal.get("question_type")

                    client_question = {
                        "internal_question_id": q_internal.get("internal_question_id"),
                        "body": q_internal.get("body", "N/A"),
                        "question_type": q_type_val,
                        "choices": (
                            shuffle_dictionary_items(all_choices_for_client)
                            if q_type_val == QuestionTypeEnum.SINGLE_CHOICE.value
                            else None
                        ),
                        "submitted_answer": None,  # Will be populated based on type
                        "student_subjective_answer": None,
                        "standard_answer_text": None,
                        "manual_score": q_internal.get("manual_score"),
                        "teacher_comment": q_internal.get("teacher_comment"),
                        "is_graded_manually": q_internal.get(
                            "is_graded_manually", False
                        ),
                    }

                    if q_type_val == QuestionTypeEnum.ESSAY_QUESTION.value:
                        client_question["student_subjective_answer"] = q_internal.get(
                            "student_subjective_answer"
                        )
                        client_question["submitted_answer"] = q_internal.get(
                            "student_subjective_answer"
                        )  # For consistency if client uses submitted_answer
                        client_question["standard_answer_text"] = q_internal.get(
                            "standard_answer_text"
                        )
                    else:  # For single_choice etc.
                        client_question["submitted_answer"] = submitted_ans_for_this_q

                    history_questions.append(
                        HistoryPaperQuestionClientView(**client_question).model_dump(
                            exclude_none=True
                        )
                    )

            # Prepare final response dict
            response_dict = {
                "paper_id": paper_data["paper_id"],
                "difficulty": DifficultyLevel(
                    paper_data.get("difficulty", DifficultyLevel.hybrid.value)
                ),
                "user_uid": user_uid,
                "paper_questions": history_questions,
                "score": paper_data.get("score"),
                "total_score": paper_data.get("total_score"),
                "score_percentage": paper_data.get("score_percentage"),
                "submitted_answers_card": submitted_answers,
                "pass_status": paper_data.get("pass_status"),
                "passcode": paper_data.get("passcode"),
                "submission_time_utc": paper_data.get("submission_time_utc"),
                "subjective_questions_count": paper_data.get(
                    "subjective_questions_count"
                ),
                "graded_subjective_questions_count": paper_data.get(
                    "graded_subjective_questions_count"
                ),
                "pending_manual_grading_count": paper_data.get(
                    "pending_manual_grading_count"
                ),
            }
            return response_dict
        _paper_crud_logger.warning(
            f"用户 '{user_uid}' 尝试访问不属于自己的试卷 '{paper_id_str}' 或试卷不存在。"
        )
        return None

    async def admin_get_all_papers_summary(
        self, skip: int = 0, limit: int = 100
    ) -> List[Dict[str, Any]]:
        _paper_crud_logger.debug(
            f"管理员请求所有试卷摘要，skip={skip}, limit={limit}。"
        )
        all_papers = await self.repository.get_all(
            PAPER_ENTITY_TYPE, skip=skip, limit=limit
        )
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
        _paper_crud_logger.debug(f"管理员请求试卷 '{paper_id_str}' 的详细信息。")
        return await self.repository.get_by_id(PAPER_ENTITY_TYPE, paper_id_str)

    async def admin_delete_paper(self, paper_id_str: str) -> bool:
        _paper_crud_logger.info(f"管理员尝试删除试卷 '{paper_id_str}'。")
        deleted = await self.repository.delete(PAPER_ENTITY_TYPE, paper_id_str)
        if deleted:
            _paper_crud_logger.info(f"[Admin] 试卷 '{paper_id_str}' 已从存储库删除。")
        else:
            _paper_crud_logger.warning(
                f"[Admin] 删除试卷 '{paper_id_str}' 失败（可能未找到）。"
            )
        return deleted

    async def grade_subjective_question(
        self,
        paper_id: UUID,
        question_internal_id: str,
        manual_score: float,
        teacher_comment: Optional[str] = None,
    ) -> bool:
        _paper_crud_logger.info(
            f"开始人工批改试卷 '{paper_id}' 中的题目 '{question_internal_id}'。"
        )
        paper_data = await self.repository.get_by_id(PAPER_ENTITY_TYPE, str(paper_id))

        if not paper_data:
            _paper_crud_logger.warning(f"批改主观题失败：试卷 '{paper_id}' 未找到。")
            raise ValueError(f"试卷 '{paper_id}' 未找到。")

        paper_questions = paper_data.get("paper_questions", [])
        if not isinstance(paper_questions, list):
            _paper_crud_logger.error(f"试卷 '{paper_id}' 的题目列表格式不正确。")
            raise ValueError(f"试卷 '{paper_id}' 题目数据损坏。")

        question_found = False
        question_updated = False
        previously_graded = False

        for q_idx, q_data in enumerate(paper_questions):
            if (
                isinstance(q_data, dict)
                and q_data.get("internal_question_id") == question_internal_id
            ):
                question_found = True
                if q_data.get("question_type") != QuestionTypeEnum.ESSAY_QUESTION.value:
                    _paper_crud_logger.warning(
                        f"尝试批改的题目 '{question_internal_id}' (试卷 '{paper_id}') 不是主观题。"
                    )
                    raise ValueError(
                        f"题目 '{question_internal_id}' 不是主观题，无法人工批改。"
                    )

                previously_graded = q_data.get("is_graded_manually", False)
                paper_questions[q_idx]["manual_score"] = manual_score
                paper_questions[q_idx]["teacher_comment"] = teacher_comment
                paper_questions[q_idx]["is_graded_manually"] = True
                question_updated = True
                break

        if not question_found:
            _paper_crud_logger.warning(
                f"批改主观题失败：在试卷 '{paper_id}' 中未找到题目ID '{question_internal_id}'。"
            )
            raise ValueError(
                f"在试卷 '{paper_id}' 中未找到题目ID '{question_internal_id}'。"
            )

        if question_updated:
            update_payload_for_repo = {
                "paper_questions": paper_questions,  # 更新后的题目列表
                "last_update_time_utc": datetime.now(timezone.utc).isoformat(),
            }
            if not previously_graded:
                current_graded_count = paper_data.get(
                    "graded_subjective_questions_count", 0
                )
                current_pending_count = paper_data.get(
                    "pending_manual_grading_count", 0
                )
                update_payload_for_repo["graded_subjective_questions_count"] = (
                    current_graded_count + 1
                )
                update_payload_for_repo["pending_manual_grading_count"] = max(
                    0, current_pending_count - 1
                )

            updated_record_partial = await self.repository.update(
                PAPER_ENTITY_TYPE, str(paper_id), update_payload_for_repo
            )
            if updated_record_partial:
                _paper_crud_logger.info(
                    f"试卷 '{paper_id}' 中题目 '{question_internal_id}' 已成功人工批改。"
                )
                # Trigger finalization check (can run in background, or be awaited by API layer if needed)
                asyncio.create_task(self.finalize_paper_grading_if_ready(paper_id))
                return True
            else:
                _paper_crud_logger.error(
                    f"更新试卷 '{paper_id}' 的主观题批改信息失败（存储库操作返回None）。"
                )
                return False
        return False

    async def get_papers_pending_manual_grading(
        self, skip: int = 0, limit: int = 100
    ) -> List[Dict[str, Any]]:
        _paper_crud_logger.info(f"获取待人工批阅试卷列表，skip={skip}, limit={limit}。")
        # This query needs to be supported by the repository or done in multiple steps/filtered here.
        # Assuming repository query can handle "field > value" or we fetch and filter.
        # For simplicity with current IDataStorageRepository, we might fetch PENDING_REVIEW and then filter.
        all_pending_review_papers = await self.repository.query(
            entity_type=PAPER_ENTITY_TYPE,
            conditions={"pass_status": PaperPassStatusEnum.PENDING_REVIEW.value},
            # Limit might need to be higher if filtering significantly reduces results
            # Or implement proper DB-level filtering for pending_manual_grading_count > 0
            limit=limit * 5,  # Fetch more to allow filtering, adjust as needed
            skip=0,  # Initial skip is 0, pagination handled after filtering
        )

        papers_needing_grading = [
            p
            for p in all_pending_review_papers
            if p.get("pending_manual_grading_count", 0) > 0
            and p.get("subjective_questions_count", 0) > 0
        ]

        # Manual pagination on the filtered list
        paginated_list = papers_needing_grading[skip : skip + limit]
        _paper_crud_logger.info(
            f"发现 {len(papers_needing_grading)} 份试卷待批阅，返回 {len(paginated_list)} 份。"
        )
        return paginated_list

    async def finalize_paper_grading_if_ready(
        self, paper_id: UUID
    ) -> Optional[Dict[str, Any]]:
        _paper_crud_logger.info(f"检查试卷 '{paper_id}' 是否可以最终定版批改。")
        paper_data = await self.repository.get_by_id(PAPER_ENTITY_TYPE, str(paper_id))

        if not paper_data:
            _paper_crud_logger.warning(f"最终定版检查失败：试卷 '{paper_id}' 未找到。")
            return None

        if (
            paper_data.get("pending_manual_grading_count", 0) == 0
            and paper_data.get("pass_status")
            == PaperPassStatusEnum.PENDING_REVIEW.value
        ):
            _paper_crud_logger.info(
                f"试卷 '{paper_id}' 所有主观题已批改，开始最终计分和状态更新。"
            )

            objective_score = paper_data.get(
                "score", 0
            )  # This is current objective score
            total_manual_score = 0.0
            paper_questions = paper_data.get("paper_questions", [])

            # Assume each question (objective or subjective) contributes to total_possible_points.
            # For simplicity, assume each question is worth 1 point for percentage calculation,
            # or that QuestionModel would need a 'points' field for accurate % calculation.
            # Here, we'll sum objective score + all manual scores for a 'total_score'.
            # Percentage calculation requires knowing the max possible score for subjective questions or total paper points.
            # Let's assume for now the 'score' field will store the sum, and 'score_percentage' will be based on len(paper_questions).
            # This part might need refinement based on how max scores for subjective Qs are defined.

            for q_data in paper_questions:
                if (
                    isinstance(q_data, dict)
                    and q_data.get("question_type")
                    == QuestionTypeEnum.ESSAY_QUESTION.value
                    and q_data.get("is_graded_manually")
                ):
                    total_manual_score += q_data.get("manual_score", 0.0)

            final_total_score = objective_score + total_manual_score

            # This percentage calculation needs to be based on total *possible* score.
            # If each question is 1 point, total_possible_points = len(paper_questions).
            # If subjective questions have different max scores, this logic needs to be more complex.
            # For now, let's assume each question is 1 point for simplicity of pass/fail.
            total_possible_points = len(paper_questions) if paper_questions else 0
            final_score_percentage = (
                (final_total_score / total_possible_points) * 100
                if total_possible_points > 0
                else 0.0
            )

            update_fields = {
                "score": round(final_total_score),
                "total_score": round(
                    final_total_score, 2
                ),  # Store the combined score explicitly
                "score_percentage": round(final_score_percentage, 2),
                "last_update_time_utc": datetime.now(timezone.utc).isoformat(),
                "pass_status": "",  # To be set below
            }

            if final_score_percentage >= settings.passing_score_percentage:
                update_fields["pass_status"] = PaperPassStatusEnum.PASSED.value
                update_fields["passcode"] = generate_random_hex_string_of_bytes(
                    settings.generated_code_length_bytes
                )
                _paper_crud_logger.info(
                    f"试卷 '{paper_id}' 最终状态：通过。总分: {final_total_score}, 百分比: {final_score_percentage:.2f}%"
                )
            else:
                update_fields["pass_status"] = PaperPassStatusEnum.FAILED.value
                _paper_crud_logger.info(
                    f"试卷 '{paper_id}' 最终状态：未通过。总分: {final_total_score}, 百分比: {final_score_percentage:.2f}%"
                )

            updated_paper = await self.repository.update(
                PAPER_ENTITY_TYPE, str(paper_id), update_fields
            )
            if not updated_paper:
                _paper_crud_logger.error(f"更新试卷 '{paper_id}' 的最终批改状态失败。")
                return None
            return updated_paper

        _paper_crud_logger.info(
            f"试卷 '{paper_id}' 尚不满足最终定版条件 (待批改主观题: {paper_data.get('pending_manual_grading_count')}, 状态: {paper_data.get('pass_status')})。"
        )
        return None


# endregion

__all__ = [
    "PaperCRUD",
    "PAPER_ENTITY_TYPE",
]

if __name__ == "__main__":
    _paper_crud_logger.info(
        f"模块 {__name__} 提供了试卷数据的CRUD操作类，不应直接执行。"
    )
    print(f"模块 {__name__} 提供了试卷数据的CRUD操作类，不应直接执行。")
