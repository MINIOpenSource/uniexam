# region 模块导入
import json
import os
import secrets
import asyncio
import copy # 用于深拷贝
import logging
import random
import datetime
from pathlib import Path # uuid was missing
from typing import List, Optional, Dict, Any, Union
from uuid import UUID
from fastapi import Request # Import Request for type hinting

# 使用相对导入
from ..models.paper_models import (
    ExamPaperResponse, GradingResultResponse, UpdateProgressResponse,
    HistoryItem, HistoryPaperQuestionClientView, HistoryPaperDetailResponse,
    PaperAdminView, PaperQuestionInternalDetail, PaperFullDetailModel
)
import uuid # Import the uuid module
from ..models.qb_models import QuestionModel # 用于类型提示
from ..core.config import settings, DifficultyLevel, CODE_SUCCESS, CODE_INFO_OR_SPECIFIC_CONDITION # This is correct
from ..utils.helpers import (
    get_client_ip_from_request,
    format_short_uuid,
    shuffle_dictionary_items,
    generate_random_hex_string_of_bytes
)
# qb_crud 实例将在主应用或依赖注入系统中创建并传递进来，或通过全局实例访问
# from .qb_crud import QuestionBankCRUD # 避免直接导入实例，以防循环依赖
# 更好的方式是在 __init__ 中接收 qb_crud 实例
# endregion

# region 全局变量与初始化
_paper_crud_logger = logging.getLogger(__name__)
# endregion

# region 试卷数据管理类 (PaperCRUD)
class PaperCRUD:
    """
    试卷数据管理类 (PaperCRUD - Create, Read, Update, Delete)。
    负责试卷数据的增删改查操作，数据主要在内存中处理，并定期持久化到文件。
    依赖 QuestionBankCRUD 来获取题库内容。
    """

    def __init__(
        self,
        papers_file_path: Optional[Path] = None,
        qb_crud_instance: Optional[Any] = None # 期望是 QuestionBankCRUD 的实例
    ):
        """
        初始化 PaperCRUD。

        参数:
            papers_file_path: 试卷数据库JSON文件的路径。
            qb_crud_instance: QuestionBankCRUD 的实例，用于获取题库信息。
        """
        if papers_file_path is None:
            self.papers_file_path: Path = settings.get_db_file_path("papers")
        else:
            self.papers_file_path: Path = papers_file_path
        
        self.in_memory_papers: List[Dict[str, Any]] = []
        self.papers_file_lock = asyncio.Lock()
        self._load_papers_from_file()

        # 题库内容现在通过 qb_crud_instance 获取
        # self.question_banks_content: Dict[DifficultyLevel, List[Dict[str, Any]]] = {}
        # self.question_banks_meta: Dict[DifficultyLevel, LibraryIndexItem] = {}
        if qb_crud_instance is None:
            _paper_crud_logger.critical("PaperCRUD 初始化错误：未提供 QuestionBankCRUD 实例！")
            # 实际应用中应该抛出异常或有更好的处理机制
            raise ValueError("QuestionBankCRUD instance is required for PaperCRUD.")
        self.qb_crud: Any = qb_crud_instance # 类型提示为 Any 以避免循环导入，实际应为 QuestionBankCRUD


    def _load_papers_from_file(self) -> None: # ... (逻辑不变)
        """从JSON文件加载试卷数据到内存 `self.in_memory_papers`。"""
        try:
            if self.papers_file_path.exists() and self.papers_file_path.is_file():
                with open(self.papers_file_path, "r", encoding="utf-8") as f: data = json.load(f)
                if isinstance(data, list): self.in_memory_papers = data; _paper_crud_logger.info(f"成功从 '{self.papers_file_path}' 加载 {len(self.in_memory_papers)} 条试卷记录到内存。")
                else: _paper_crud_logger.warning(f"试卷数据库文件 '{self.papers_file_path}' 内容不是列表，内存试卷数据库初始化为空。"); self.in_memory_papers = []
            else: _paper_crud_logger.info(f"试卷数据库文件 '{self.papers_file_path}' 未找到，内存试卷数据库初始化为空。"); self.in_memory_papers = []
        except (json.JSONDecodeError, ValueError) as e: _paper_crud_logger.error(f"从 '{self.papers_file_path}' 加载试卷数据失败: {e}。内存试卷数据库初始化为空。"); self.in_memory_papers = []
        except Exception as e: _paper_crud_logger.error(f"从 '{self.papers_file_path}' 加载试卷数据时发生未知错误: {e}。", exc_info=True); self.in_memory_papers = []

    async def _persist_papers_to_file_async(self) -> None: # ... (逻辑不变)
        """异步地将内存中的试卷数据持久化到JSON文件。"""
        async with self.papers_file_lock:
            try:
                papers_to_write = copy.deepcopy(self.in_memory_papers)
                self.papers_file_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.papers_file_path, "w", encoding="utf-8") as f: json.dump(papers_to_write, f, indent=4, ensure_ascii=False)
                _paper_crud_logger.info(f"成功将 {len(papers_to_write)} 条试卷记录持久化到 '{self.papers_file_path}'。")
            except Exception as e: _paper_crud_logger.error(f"持久化试卷数据库到 '{self.papers_file_path}' 失败: {e}", exc_info=True)

    # 题库加载和重载逻辑现在依赖于 qb_crud 实例
    # PaperCRUD 自身不再直接读取题库文件或 index.json
    # 它会在需要时从 qb_crud 获取最新的题库内容

    async def create_new_paper(
        self,
        request: Request,
        user_uid: str,
        difficulty: DifficultyLevel,
        num_questions_override: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        创建一份新试卷，关联用户UID，并将其添加到内存中。
        题目从 qb_crud 获取。
        """
        # 从 qb_crud 获取题库元数据和内容
        full_question_bank = await self.qb_crud.get_question_bank_with_content(difficulty)
        
        if not full_question_bank or not full_question_bank.questions:
            _paper_crud_logger.error(
                f"请求了难度 '{difficulty.value}' 但其题库内容为空或元数据未加载。"
            )
            raise ValueError(f"难度 '{difficulty.value}' 的题库不可用或为空。")

        current_question_bank_content = [q.model_dump() for q in full_question_bank.questions] # 获取题目字典列表
        current_question_bank_meta = full_question_bank.metadata

        num_questions_to_select = num_questions_override \
            if num_questions_override is not None \
            else current_question_bank_meta.default_questions
        
        num_questions_to_select = min(num_questions_to_select, current_question_bank_meta.total_questions)

        if not (0 < num_questions_to_select <= len(current_question_bank_content)):
            raise ValueError(
                f"请求的题目数量 {num_questions_to_select} 无效或超出题库 "
                f"'{difficulty.value}' (共 {len(current_question_bank_content)} 题) 的范围。"
            )

        paper_uuid = str(uuid.uuid4())
        new_paper_data: Dict[str, Any] = {
            "paper_id": paper_uuid, "user_uid": user_uid,
            "creation_time_utc": datetime.datetime.now(timezone.utc).isoformat(),
            "creation_ip": get_client_ip_from_request(request=request, cloudflare_ipv4_cidrs=None, cloudflare_ipv6_cidrs=None), # 传递CF IP范围
            "difficulty": difficulty.value,
            "paper_questions": [], "score": None, "submitted_answers_card": None,
            "submission_time_utc": None, "submission_ip": None, "pass_status": None,
            "passcode": None, "last_update_time_utc": None, "last_update_ip": None,
        }

        selected_question_samples = random.sample(current_question_bank_content, num_questions_to_select)
        for item_data in selected_question_samples: # item_data 是字典
            correct_choice_text = random.sample(
                item_data["correct_choices"], settings.num_correct_choices_to_select
            )[0]
            # 使用 settings.generated_code_length_bytes
            correct_choice_id = generate_random_hex_string_of_bytes(settings.generated_code_length_bytes)
            
            num_incorrect_to_sample = min(
                settings.num_incorrect_choices_to_select, len(item_data["incorrect_choices"])
            )
            incorrect_choices_texts = random.sample(
                item_data["incorrect_choices"], num_incorrect_to_sample
            )
            incorrect_choices_with_ids = {
                generate_random_hex_string_of_bytes(settings.generated_code_length_bytes): text
                for text in incorrect_choices_texts
            }
            question_entry = {
                "body": item_data["body"],
                "correct_choices_map": {correct_choice_id: correct_choice_text},
                "incorrect_choices_map": incorrect_choices_with_ids
                # 如果题目模型包含 question_type, ref 等，也应在这里加入到 question_entry
                # "question_type": item_data.get("question_type", "single_choice"),
                # "ref": item_data.get("ref")
            }
            new_paper_data["paper_questions"].append(question_entry)
        
        self.in_memory_papers.append(new_paper_data)
        _paper_crud_logger.debug(
            f"用户 '{user_uid}' 的新试卷 {paper_uuid} (难度: {difficulty.value}, "
            f"题目数: {num_questions_to_select}) 已添加到内存。"
        )

        client_paper_response_paper_field: List[Dict[str, Any]] = []
        for q_data in new_paper_data["paper_questions"]:
            all_choices = {
                **q_data.get("correct_choices_map", {}),
                **q_data.get("incorrect_choices_map", {})
            }
            client_paper_response_paper_field.append({
                "body": q_data.get("body", "题目内容缺失"),
                "choices": shuffle_dictionary_items(all_choices)
                # "question_type": q_data.get("question_type") # 如果需要返回给客户端
            })
        
        return {
            "paper_id": paper_uuid,
            "difficulty": difficulty,
            "paper": client_paper_response_paper_field
        }

    # update_paper_progress, grade_paper_submission, get_user_history,
    # get_user_paper_detail_for_history, admin_* 方法基本不变，
    # 因为它们主要操作 self.in_memory_papers，而试卷的内部结构
    # (paper_questions) 在创建时已经确定。
    # 确保 get_client_ip 调用方式正确。

    def update_paper_progress(self, paper_id: UUID, user_uid: str, submitted_answers: List[str], request: Request) -> Dict[str, Any]:
        target_paper_record: Optional[Dict[str, Any]] = None
        for paper_record in self.in_memory_papers:
            if str(paper_record.get("paper_id")) == str(paper_id) and paper_record.get("user_uid") == user_uid: target_paper_record = paper_record; break
        if target_paper_record is None: return {"code": CODE_INFO_OR_SPECIFIC_CONDITION, "status_code": "NOT_FOUND", "message": "Paper not found or access denied."}
        pass_status = target_paper_record.get("pass_status")
        if pass_status in ["PASSED", "FAILED"]: return {"code": CODE_INFO_OR_SPECIFIC_CONDITION, "status_code": "ALREADY_COMPLETED", "message": "This paper has already been completed and cannot be updated.", "paper_id": str(paper_id)}
        num_questions_in_paper = len(target_paper_record.get("paper_questions", []))
        if len(submitted_answers) > num_questions_in_paper: return {"code": CODE_INFO_OR_SPECIFIC_CONDITION, "status_code": "INVALID_ANSWERS_LENGTH", "message": "Number of submitted answers exceeds total questions in the paper."} # type: ignore
        update_time = datetime.datetime.now(timezone.utc).isoformat()
        target_paper_record["submitted_answers_card"] = submitted_answers; target_paper_record["last_update_time_utc"] = update_time; target_paper_record["last_update_ip"] = get_client_ip(request=request) # 移除CF参数，让其使用全局
        _paper_crud_logger.debug(f"用户 '{user_uid}' 的试卷 {paper_id} 进度已在内存中更新。")
        return {"code": CODE_SUCCESS, "status_code": "PROGRESS_SAVED", "message": "Paper progress saved successfully.", "paper_id": str(paper_id), "last_update_time_utc": update_time}

    def grade_paper_submission(self, paper_id: UUID, user_uid: str, submitted_answers: List[str], request: Request) -> Dict[str, Any]:
        target_paper_record: Optional[Dict[str, Any]] = None
        for paper_record in self.in_memory_papers: 
            if str(paper_record.get("paper_id")) == str(paper_id) and paper_record.get("user_uid") == user_uid: target_paper_record = paper_record; break
        if target_paper_record is None: return {"code": CODE_INFO_OR_SPECIFIC_CONDITION, "status_code": "NOT_FOUND", "message": "Paper not found or access denied."}
        if "pass_status" in target_paper_record and target_paper_record["pass_status"]: return {"code": CODE_INFO_OR_SPECIFIC_CONDITION, "status_code": "ALREADY_GRADED", "message": "This paper has already been graded.", "previous_result": target_paper_record.get("pass_status"), "score": target_paper_record.get("score"), "passcode": target_paper_record.get("passcode")}
        paper_questions = target_paper_record.get("paper_questions", [])
        if not isinstance(paper_questions, list) or not paper_questions: _paper_crud_logger.error(f"试卷 {paper_id} 缺少 'paper_questions' 或为空。"); return {"code": CODE_INFO_OR_SPECIFIC_CONDITION, "status_code": "INVALID_PAPER_STRUCTURE", "message": "Paper structure is invalid, cannot grade."}
        if len(submitted_answers) != len(paper_questions): return {"code": CODE_INFO_OR_SPECIFIC_CONDITION, "status_code": "INVALID_SUBMISSION", "message": "Number of submitted answers does not match total questions."}
        correct_answers_count = 0
        for i, q_data in enumerate(paper_questions):
            if isinstance(q_data, dict) and "correct_choices_map" in q_data and isinstance(q_data["correct_choices_map"], dict) and q_data["correct_choices_map"]:
                correct_choice_id = list(q_data["correct_choices_map"].keys())[0]
                if i < len(submitted_answers) and submitted_answers[i] == correct_choice_id: correct_answers_count += 1
            else: _paper_crud_logger.warning(f"用户 '{user_uid}' 的试卷 {paper_id} 的问题索引 {i} 结构不正确，跳过计分。")
        current_time_utc_iso = datetime.datetime.now(timezone.utc).isoformat()
        score_percentage = (correct_answers_count / len(paper_questions)) * 100 if len(paper_questions) > 0 else 0.0
        target_paper_record["score"] = correct_answers_count; target_paper_record["score_percentage"] = round(score_percentage, 2); target_paper_record["submitted_answers_card"] = submitted_answers; target_paper_record["submission_time_utc"] = current_time_utc_iso; target_paper_record["submission_ip"] = get_client_ip_from_request(request=request); target_paper_record["last_update_time_utc"] = current_time_utc_iso; target_paper_record["last_update_ip"] = target_paper_record["submission_ip"]
        result_payload: Dict[str, Any] = {"score": correct_answers_count, "score_percentage": round(score_percentage, 2)}
        if score_percentage >= settings.passing_score_percentage: target_paper_record["pass_status"] = "PASSED"; target_paper_record["passcode"] = generate_random_hex_string_of_bytes(settings.generated_code_length_bytes); result_payload.update({"code": CODE_SUCCESS, "status_code": "PASSED", "passcode": target_paper_record["passcode"]})
        else: target_paper_record["pass_status"] = "FAILED"; result_payload.update({"code": CODE_SUCCESS, "status_code": "FAILED"})
        _paper_crud_logger.debug(f"用户 '{user_uid}' 的试卷 {paper_id} 已在内存中批改。")
        return result_payload

    def get_user_history(self, user_uid: str) -> List[Dict[str, Any]]: # ... (逻辑不变)
        history = []
        for paper in self.in_memory_papers:
            if paper.get("user_uid") == user_uid: history.append({"paper_id": paper.get("paper_id"), "difficulty": DifficultyLevel(paper.get("difficulty", DifficultyLevel.hybrid.value)), "score": paper.get("score"), "score_percentage": paper.get("score_percentage"), "pass_status": paper.get("pass_status"), "submission_time_utc": paper.get("submission_time_utc")})
        return sorted(history, key=lambda x: x.get("submission_time_utc") or x.get("creation_time_utc", ""), reverse=True)

    def get_user_paper_detail_for_history(self, paper_id_str: str, user_uid: str) -> Optional[Dict[str, Any]]: # ... (逻辑不变)
        for paper_data in self.in_memory_papers:
            if str(paper_data.get("paper_id")) == paper_id_str and paper_data.get("user_uid") == user_uid:
                history_questions: List[Dict[str, Any]] = []
                submitted_answers = paper_data.get("submitted_answers_card", [])
                if "paper_questions" in paper_data and isinstance(paper_data["paper_questions"], list):
                    for idx, q_internal in enumerate(paper_data["paper_questions"]):
                        all_choices_for_client = {**q_internal.get("correct_choices_map", {}), **q_internal.get("incorrect_choices_map", {})}
                        submitted_choice_id_for_this_q: Optional[str] = None
                        if idx < len(submitted_answers) and submitted_answers[idx] is not None: submitted_choice_id_for_this_q = submitted_answers[idx] # 确保 submitted_answers[idx] 不是 None
                        
                        # 假设 q_internal 包含 question_type
                        q_type = q_internal.get("question_type", "single_choice") # 默认为单选

                        detail_model = HistoryPaperQuestionClientView(
                            body=q_internal.get("body", "N/A"),
                            question_type=q_type,
                            choices=shuffle_dictionary_items(all_choices_for_client) if q_type in ["single_choice", "multiple_choice"] else None,
                            submitted_answer=submitted_choice_id_for_this_q # 对于选择题是ID，其他题型可能不同
                        )
                        history_questions.append(detail_model.model_dump(exclude_none=True))
                return {"paper_id": paper_data["paper_id"], "difficulty": DifficultyLevel(paper_data.get("difficulty", DifficultyLevel.hybrid.value)), "user_uid": user_uid, "paper_questions": history_questions, "score": paper_data.get("score"), "score_percentage": paper_data.get("score_percentage"), "submitted_answers_card": submitted_answers, "pass_status": paper_data.get("pass_status"), "passcode": paper_data.get("passcode"), "submission_time_utc": paper_data.get("submission_time_utc")}
        return None

    # --- Admin 相关方法操作内存 (逻辑不变) ---
    def admin_get_all_papers_summary_from_memory(self, skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
        papers_copy = copy.deepcopy(self.in_memory_papers); sorted_papers = sorted(papers_copy, key=lambda p: p.get("creation_time_utc", ""), reverse=True); return sorted_papers[skip : skip + limit]
    def admin_get_paper_detail_from_memory(self, paper_id_str: str) -> Optional[Dict[str, Any]]:
        for paper_data in self.in_memory_papers:
            if str(paper_data.get("paper_id")) == paper_id_str: return copy.deepcopy(paper_data)
        return None
    def admin_delete_paper_from_memory(self, paper_id_str: str) -> bool:
        initial_len = len(self.in_memory_papers); self.in_memory_papers = [p for p in self.in_memory_papers if str(p.get("paper_id")) != paper_id_str]; deleted = len(self.in_memory_papers) < initial_len
        if deleted: _paper_crud_logger.info(f"[Admin] 试卷 {paper_id_str} 已从内存中删除。")
        return deleted
# endregion
