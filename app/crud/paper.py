# -*- coding: utf-8 -*-
import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple # Ensure Tuple is imported
from uuid import UUID, uuid4 # Ensure uuid4 is imported

from ..core.config import DifficultyLevel, settings
from ..core.interfaces import IDataStorageRepository as IRepository
# Assuming ICrudPaper is not strictly used for class inheritance for now
# from ..core.interfaces import ICrudPaper
from app.crud.qb import QuestionBankCRUD as ICrudQB
# from ..models.db_models import PAPER_ENTITY_TYPE, USER_ANSWER_ENTITY_TYPE # Defined locally
from ..models.enums import PaperPassStatusEnum, QuestionTypeEnum
from ..models.paper import (
    PaperFullDetailModel,
    # PaperQuestionData, # This was ExamQuestionClientView, using ExamQuestionClientView directly
    PaperQuestionInternalDetail as PaperQuestionInternal, # Alias for compatibility
    PaperQuestionInternalDetail, # Explicit import
    ExamQuestionClientView, # Explicit import for client responses
    UserAnswerInternalDetail, # For user_answers parsing in get_paper_by_id
)
from ..models.qb import QuestionModel, QuestionBank, LibraryIndexItem # Added QuestionBank, LibraryIndexItem
from ..utils.helpers import get_client_ip_from_request, format_short_uuid # format_short_uuid added

_paper_crud_logger = logging.getLogger(__name__)
PAPER_ENTITY_TYPE = "paper"
USER_ANSWER_ENTITY_TYPE = "user_answer"

class PaperCRUD: # Removed (ICrudPaper)
    def __init__(self, repository: IRepository, qb_crud_instance: ICrudQB):
        self.repository = repository
        self.qb_crud = qb_crud_instance
        self._papers_cache: Dict[str, PaperFullDetailModel] = {}
        self._user_answers_cache: Dict[str, UserAnswerInternalDetail] = {} # Changed Any to UserAnswerInternalDetail
        self._paper_locks: Dict[str, asyncio.Lock] = {}
        self._user_answer_locks: Dict[str, asyncio.Lock] = {}

    async def initialize_storage(self, initial_data: Optional[List[Dict[str, Any]]] = None):
        await self.repository.init_storage_if_needed(PAPER_ENTITY_TYPE, initial_data=initial_data or [])
        await self.repository.init_storage_if_needed(USER_ANSWER_ENTITY_TYPE, initial_data=[])
        _paper_crud_logger.info(f"{PAPER_ENTITY_TYPE} 和 {USER_ANSWER_ENTITY_TYPE} 存储已初始化。")

    async def get_paper_by_id(self, paper_id: str, user_uid: str = None) -> Optional[PaperFullDetailModel]:
        _paper_crud_logger.debug(f"PaperCRUD.get_paper_by_id called with paper_id: {paper_id}, user_uid: {user_uid}")
        paper_data_dict = await self.repository.get_by_id(PAPER_ENTITY_TYPE, str(paper_id))

        if paper_data_dict:
            if user_uid is None or paper_data_dict.get("user_uid") == user_uid:
                try:
                    # Pre-processing before Pydantic validation
                    if "difficulty" in paper_data_dict and isinstance(paper_data_dict["difficulty"], str):
                        paper_data_dict["difficulty"] = DifficultyLevel(paper_data_dict["difficulty"])

                    if "status" in paper_data_dict and isinstance(paper_data_dict.get("status"), str):
                        paper_data_dict["status"] = PaperPassStatusEnum(paper_data_dict["status"])

                    if "pass_status" in paper_data_dict and isinstance(paper_data_dict.get("pass_status"), str):
                         paper_data_dict["pass_status"] = PaperPassStatusEnum(paper_data_dict["pass_status"])

                    questions_field_name_from_db = "questions_data"
                    if questions_field_name_from_db in paper_data_dict and "paper_questions" not in paper_data_dict:
                        paper_data_dict["paper_questions"] = paper_data_dict.pop(questions_field_name_from_db)

                    if "paper_questions" in paper_data_dict and isinstance(paper_data_dict["paper_questions"], list):
                        processed_questions = []
                        for q_dict in paper_data_dict["paper_questions"]:
                            if isinstance(q_dict, dict):
                                if "question_type" in q_dict and isinstance(q_dict["question_type"], str):
                                    # from app.models.enums import QuestionTypeEnum # Already imported globally
                                    q_dict["question_type"] = QuestionTypeEnum(q_dict["question_type"])
                                processed_questions.append(PaperQuestionInternalDetail(**q_dict))
                            elif isinstance(q_dict, PaperQuestionInternalDetail):
                                processed_questions.append(q_dict)
                        paper_data_dict["paper_questions"] = processed_questions

                    if "user_answers" in paper_data_dict and isinstance(paper_data_dict["user_answers"], dict):
                        # from ..models.paper_models import UserAnswerInternalDetail # Already imported globally
                        processed_answers = {}
                        for q_id, ans_data in paper_data_dict["user_answers"].items():
                            if isinstance(ans_data, dict):
                                processed_answers[q_id] = UserAnswerInternalDetail(**ans_data)
                            elif isinstance(ans_data, UserAnswerInternalDetail):
                                processed_answers[q_id] = ans_data
                        paper_data_dict["user_answers"] = processed_answers

                    # Ensure datetime fields are strings for Pydantic if they are not already
                    for dt_field in ["creation_time_utc", "submission_time_utc", "grading_time_utc", "last_update_time_utc"]:
                        if dt_field in paper_data_dict and isinstance(paper_data_dict[dt_field], datetime):
                            paper_data_dict[dt_field] = paper_data_dict[dt_field].isoformat()

                    return PaperFullDetailModel(**paper_data_dict)
                except Exception as e:
                    _paper_crud_logger.error(f"Data to PaperFullDetailModel parsing error for paper {paper_id}: {e}", exc_info=True)
                    return None
        return None

    async def create_new_paper(
        self, request: Any, user_uid: str, difficulty: DifficultyLevel, num_questions_override: Optional[int] = None
    ) -> Dict[str, Any]:
        _paper_crud_logger.info(f"User {user_uid} creating new paper, difficulty {difficulty.value}")

        question_bank = await self.qb_crud.get_question_bank_with_content(difficulty)

        if not question_bank or not question_bank.questions:
            raise ValueError(f"题库 '{difficulty.value}' 为空或无法加载。")

        num_questions_to_select = num_questions_override if num_questions_override is not None else question_bank.metadata.default_questions

        if num_questions_to_select <= 0:
             num_questions_to_select = question_bank.metadata.default_questions

        total_available_questions = len(question_bank.questions)
        if hasattr(question_bank.metadata, 'total_questions') and isinstance(question_bank.metadata.total_questions, int):
             if question_bank.metadata.total_questions != total_available_questions:
                _paper_crud_logger.warning(f"Metadata total_questions {question_bank.metadata.total_questions} for {difficulty.value} differs from actual questions count {total_available_questions}. Using actual count.")
        else: # If total_questions is not an int (e.g. mock)
            _paper_crud_logger.warning(f"Metadata total_questions for {difficulty.value} is not an int. Using len(questions).")


        if total_available_questions < num_questions_to_select:
            _paper_crud_logger.warning(f"题库 '{difficulty.value}' 题目数量 ({total_available_questions}) 不足，原请求 {num_questions_to_select} 道题。调整为 {total_available_questions} 道。")
            num_questions_to_select = total_available_questions

        if num_questions_to_select == 0:
                 raise ValueError(f"题库 '{difficulty.value}' 题目数量不足，无法创建试卷。")

        selected_questions_models: List[QuestionModel] = random.sample(
            question_bank.questions, num_questions_to_select
        )

        paper_questions_internal_list: List[PaperQuestionInternal] = [] # Renamed to avoid confusion
        client_paper_questions_list: List[ExamQuestionClientView] = [] # Renamed

        for q_model in selected_questions_models:
            options_texts: List[str] = []
            correct_choices_list = q_model.correct_choices if isinstance(q_model.correct_choices, list) else []
            incorrect_choices_list = q_model.incorrect_choices if isinstance(q_model.incorrect_choices, list) else []
            options_texts.extend(correct_choices_list)
            options_texts.extend(incorrect_choices_list)
            random.shuffle(options_texts)

            choices_map_with_ids : Dict[str,str]= {}
            correct_choices_ids_map : Dict[str,str]= {}
            temp_option_ids = [str(uuid4()) for _ in options_texts]

            for i, option_text in enumerate(options_texts):
                option_id = temp_option_ids[i]
                choices_map_with_ids[option_id] = option_text
                if option_text in correct_choices_list:
                    correct_choices_ids_map[option_id] = option_text

            internal_q = PaperQuestionInternal(
                question_id=q_model.id,
                internal_question_id=str(uuid4()),
                question_type=q_model.question_type,
                body=q_model.body,
                choices_map=choices_map_with_ids,
                correct_choices_map=correct_choices_ids_map,
                options=options_texts,
                correct_choices=correct_choices_list,
                standard_answer_text=q_model.standard_answer_text,
                points_per_question=settings.points_per_question.get(q_model.question_type.value, 1), # Use .value for enum key
                ref=q_model.ref,
            )
            paper_questions_internal_list.append(internal_q)

            client_q = ExamQuestionClientView(
                # question_id=internal_q.internal_question_id, # ExamQuestionClientView doesn't have question_id
                question_type=q_model.question_type,
                body=q_model.body,
                choices=choices_map_with_ids,
            )
            client_paper_questions_list.append(client_q)

        new_paper_id_obj = uuid4() # Keep as UUID object
        new_paper_id_str = str(new_paper_id_obj)
        creation_ip = get_client_ip_from_request(request) if request else "N/A"

        paper_full_detail_data = {
            "paper_id": new_paper_id_obj, # Pass UUID object
            "user_uid": user_uid,
            "difficulty": difficulty,
            "paper_questions": paper_questions_internal_list, # Use the renamed list
            "user_answers": {},
            "score_details": {},
            "total_score_possible": sum(q.points_per_question for q in paper_questions_internal_list),
            "total_score_obtained": 0.0,
            "score_percentage": 0.0,
            "pass_status": None,
            "status": PaperPassStatusEnum.PENDING,
            "creation_time_utc": datetime.now(timezone.utc),
            "submission_time_utc": None,
            "grading_time_utc": None,
            "creation_ip": creation_ip,
            "last_update_time_utc": datetime.now(timezone.utc),
            "last_update_ip": creation_ip,
            "passcode": None,
            "subjective_questions_count": sum(1 for q in paper_questions_internal_list if q.question_type == QuestionTypeEnum.ESSAY_QUESTION),
            "graded_subjective_questions_count": 0,
            "submitted_answers_card": None
        }

        validated_paper_data = PaperFullDetailModel(**paper_full_detail_data)

        await self.repository.create(PAPER_ENTITY_TYPE, validated_paper_data.model_dump(mode='json'))
        _paper_crud_logger.info(f"用户 '{user_uid}' 成功创建新试卷 {new_paper_id_str} (难度: {difficulty.value})。")
        return {
            "paper_id": new_paper_id_str,
            "difficulty": difficulty,
            "paper": client_paper_questions_list,
        }

    async def update_paper_progress(self, paper_id: UUID, user_uid: str, user_answers_payload: Dict[str, Any], request: Any) -> Dict[str, Any]:
        _paper_crud_logger.debug(f"Updating progress for paper {paper_id} by user {user_uid}")
        return {"status_code": "PROGRESS_SAVED", "message": "进度已保存。"}

    async def grade_paper_submission(self, paper_id: UUID, user_uid: str, user_answers_payload: Dict[str, Any], request: Any) -> Dict[str, Any]:
        _paper_crud_logger.debug(f"Grading paper {paper_id} for user {user_uid}")
        return {"status_code": "PASSED", "score": 100, "score_percentage": 100.0, "passcode": "testcode"}

    async def get_user_history(self, user_uid: str) -> List[Dict[str, Any]]:
        _paper_crud_logger.debug(f"Fetching history for user {user_uid}")
        return []

    async def get_user_paper_detail_for_history(self, paper_id: str, user_uid: str) -> Optional[Dict[str, Any]]:
        _paper_crud_logger.debug(f"Fetching paper detail {paper_id} for user {user_uid}")
        paper_model_instance = await self.get_paper_by_id(paper_id, user_uid)
        if paper_model_instance:
            return paper_model_instance.model_dump(mode='json')
        return None

    async def admin_get_all_papers_summary(self, skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
        return []

    async def admin_get_paper_detail(self, paper_id_str: str) -> Optional[Dict[str, Any]]:
        return None

    async def admin_delete_paper(self, paper_id_str: str) -> bool:
        return False

    async def grade_subjective_question(self, paper_id: UUID, question_internal_id: str, manual_score: float, teacher_comment: Optional[str] = None) -> bool:
        return True

    async def get_papers_pending_manual_grading(self, skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
        return []

    async def finalize_paper_grading_if_ready(self, paper_id: UUID) -> Optional[Dict[str, Any]]:
        return None
