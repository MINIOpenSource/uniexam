import hashlib
import json
import random
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Paper, PaperHash, PaperQuestion
from app.services.font_obfuscator import obfuscate_question_texts

_sys_rng = random.SystemRandom()

# In-memory cache of issued paper hashes: paper_id -> set of SHA-256 hex digests
_issued_paper_hashes: Dict[str, Set[str]] = {}

# Track last option permutation per (paper_id, pq_id) so consecutive issuances
# of the same paper are guaranteed to have a different option order.
_last_issued_option_order: Dict[Tuple[str, str], Tuple[str, ...]] = {}


def _extract_choices_dict(q_item: Any) -> Dict[str, str]:
    if isinstance(q_item, dict):
        if "choices" in q_item and isinstance(q_item["choices"], dict):
            return {str(k): str(v) for k, v in q_item["choices"].items()}
        content = q_item.get("content")
        if isinstance(content, dict) and isinstance(content.get("options"), dict):
            return {str(k): str(v) for k, v in content["options"].items()}
        if "options" in q_item and isinstance(q_item["options"], dict):
            return {str(k): str(v) for k, v in q_item["options"].items()}
        return {}
    choices = getattr(q_item, "choices", None)
    if isinstance(choices, dict):
        return {str(k): str(v) for k, v in choices.items()}
    content = getattr(q_item, "content", None)
    if isinstance(content, dict) and isinstance(content.get("options"), dict):
        return {str(k): str(v) for k, v in content["options"].items()}
    return {}


def _extract_body(q_item: Any) -> str:
    if isinstance(q_item, dict):
        if "body" in q_item:
            return str(q_item["body"] or "")
        content = q_item.get("content")
        if isinstance(content, dict) and "body" in content:
            return str(content["body"] or "")
        return ""
    body = getattr(q_item, "body", None)
    if body is not None:
        return str(body)
    content = getattr(q_item, "content", None)
    if isinstance(content, dict) and "body" in content:
        return str(content["body"] or "")
    return ""


def compute_paper_hash(paper_id: str, questions: List[Any]) -> str:
    """
    Computes a deterministic SHA-256 hash of a paper issuance:
    binds paper_id, question order, each question's obfuscated body, and the exact ordered
    (option_uuid, obfuscated_option_text) pairs.
    """
    normalized_questions = []
    for q in questions:
        body = _extract_body(q)
        choices = _extract_choices_dict(q)
        normalized_questions.append({
            "body": body,
            "choices": [[k, v] for k, v in choices.items()],
        })

    canonical = json.dumps(
        {"paper_id": str(paper_id), "questions": normalized_questions},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class PaperIssuanceService:
    def resolve_canon_ids_for_hash(
        self, paper_hash: Optional[str], selected_canon_ids: List[Optional[str]]
    ) -> Optional[List[Optional[str]]]:
        """
        Given a specific client issuance's paper_hash and a list of canonical option IDs
        (e.g. ["A", None, "C"]), returns the corresponding option UUIDs for that issuance.
        """
        if not paper_hash:
            return None
        hash_map = _issued_uuid_maps.get(paper_hash)
        if not hash_map:
            return None
        resolved_uuids: List[Optional[str]] = []
        for idx, canon_id in enumerate(selected_canon_ids):
            if not canon_id or idx >= len(hash_map):
                resolved_uuids.append(None)
                continue
            q_map = hash_map[idx]
            matched_uuid = next(
                (u for u, (c_key, _) in q_map.items() if c_key == canon_id),
                None,
            )
            resolved_uuids.append(matched_uuid)
        return resolved_uuids

    async def register_hash(
        self, paper_id: str, paper_hash: str, db: Optional[AsyncSession] = None
    ) -> None:
        bucket = _issued_paper_hashes.setdefault(paper_id, set())
        if paper_hash not in bucket:
            bucket.add(paper_hash)
            if db is not None:
                db.add(PaperHash(paper_id=paper_id, paper_hash=paper_hash))

    async def is_valid_hash(
        self, paper_id: str, paper_hash: str, db: Optional[AsyncSession] = None
    ) -> bool:
        bucket = _issued_paper_hashes.get(paper_id)
        if bucket and paper_hash in bucket:
            return True
        if db is not None:
            try:
                res = await db.execute(
                    select(PaperHash).where(
                        PaperHash.paper_id == paper_id,
                        PaperHash.paper_hash == paper_hash,
                    )
                )
                row = res.scalars().first()
                if row:
                    _issued_paper_hashes.setdefault(paper_id, set()).add(paper_hash)
                    return True
            except Exception:
                pass
        return False

    def clear_paper_hashes(self, paper_id: str) -> None:
        _issued_paper_hashes.pop(paper_id, None)

    def _build_shuffled_uuid_choices(
        self, paper_id: str, pq: PaperQuestion
    ) -> Tuple[Dict[str, str], Dict[str, str], Dict[str, str], List[str]]:
        """
        Generates a fresh UUID for each option of pq.question and shuffles option order,
        guaranteeing that consecutive issuances of the same (paper_id, pq.id) never
        share the same option order when len(options) > 1.
        Returns: (choices_uuid_to_plain_text, canon_key_to_uuid, text_to_uuid, ordered_canon_keys)
        """
        q = pq.question
        orig_options: Dict[str, str] = (q.content or {}).get("options", {})
        items: List[Tuple[str, str]] = [(str(k), str(v)) for k, v in orig_options.items()]

        if len(items) > 1:
            last_order = _last_issued_option_order.get((paper_id, pq.id))
            _sys_rng.shuffle(items)
            current_order = tuple(k for k, _ in items)
            if last_order is not None and current_order == last_order:
                # Rotate by 1 to guarantee strictly different option ordering
                items = items[1:] + items[:1]
                current_order = tuple(k for k, _ in items)
            _last_issued_option_order[(paper_id, pq.id)] = current_order

        choices: Dict[str, str] = {}
        canon_to_uuid: Dict[str, str] = {}
        text_to_uuid: Dict[str, str] = {}
        ordered_canon_keys: List[str] = []

        for canon_key, opt_text in items:
            opt_uuid = str(uuid.uuid4())
            choices[opt_uuid] = opt_text
            canon_to_uuid[canon_key] = opt_uuid
            text_to_uuid[opt_text] = opt_uuid
            ordered_canon_keys.append(canon_key)

        return choices, canon_to_uuid, text_to_uuid, ordered_canon_keys

    def _map_saved_answer_to_uuid(
        self,
        user_answer: Optional[Dict[str, Any]],
        canon_to_uuid: Dict[str, str],
        text_to_uuid: Dict[str, str],
    ) -> Optional[str]:
        if not isinstance(user_answer, dict):
            return None
        saved_canon = user_answer.get("selected_option_id")
        if saved_canon and saved_canon in canon_to_uuid:
            return canon_to_uuid[saved_canon]
        saved_text = user_answer.get("selected_text")
        if saved_text and saved_text in text_to_uuid:
            return text_to_uuid[saved_text]
        return None

    async def issue_legacy_paper(
        self, paper: Paper, db: Optional[AsyncSession] = None
    ) -> Tuple[List[Dict[str, Any]], List[str], str]:
        """
        Builds the client-facing paper questions with:
        1. UUID option IDs and shuffled option order
        2. Per-question scrambled font (`obfuscated_font`) and completely randomized
           character-instance codepoints in `body` and `choices` (even identical characters
           in the same sentence use distinct codepoints and distinct glyph entries)
        3. Maps any existing answers to the newly issued UUIDs
        4. Computes the paper hash and retains it on the server.
        Returns: (client_questions, submitted_answers_card, paper_hash)
        """
        client_questions: List[Dict[str, Any]] = []
        submitted_card: List[str] = []

        for pq in paper.paper_questions:
            q = pq.question
            q_type = q.type.value if hasattr(q.type, "value") else str(q.type)
            plain_choices, canon_to_uuid, text_to_uuid, ordered_canon = (
                self._build_shuffled_uuid_choices(paper.id, pq)
            )
            mapped_uuid = self._map_saved_answer_to_uuid(
                pq.user_answer, canon_to_uuid, text_to_uuid
            )
            submitted_card.append(mapped_uuid if mapped_uuid else "-1")

            plain_body = (q.content or {}).get("body", "")
            obf_body, obf_choices, font_data_uri = obfuscate_question_texts(
                plain_body, plain_choices
            )

            # Persist the latest issued UUID -> canonical option mapping in memory metadata
            # and also allow position/UUID resolution when client submits obfuscated paper
            client_questions.append({
                "body": obf_body,
                "choices": obf_choices,
                "question_type": q_type,
                "obfuscated_font": font_data_uri,
                "_canon_order": ordered_canon,
            })

        # Strip internal helper before returning, or encode into hash?
        # Wait: if we map UUIDs via a server-side lookup keyed by (paper_hash, q_idx, opt_uuid)
        # or deterministic HMAC, client never sees canonical order at all!
        paper_questions_clean: List[Dict[str, Any]] = []
        uuid_map_for_hash: List[Dict[str, Tuple[str, str]]] = []

        for idx, cq in enumerate(client_questions):
            pq = paper.paper_questions[idx]
            orig_options: Dict[str, str] = (pq.question.content or {}).get("options", {})
            ordered_canon = cq.pop("_canon_order")
            opt_uuids = list(cq["choices"].keys())
            q_uuid_map: Dict[str, Tuple[str, str]] = {}
            for u_idx, opt_uuid in enumerate(opt_uuids):
                c_key = ordered_canon[u_idx]
                c_txt = str(orig_options.get(c_key, ""))
                q_uuid_map[opt_uuid] = (c_key, c_txt)
            uuid_map_for_hash.append(q_uuid_map)
            paper_questions_clean.append(cq)

        paper_hash = compute_paper_hash(paper.id, paper_questions_clean)
        _issued_uuid_maps[paper_hash] = uuid_map_for_hash
        await self.register_hash(paper.id, paper_hash, db=db)
        return paper_questions_clean, submitted_card, paper_hash

    async def issue_v1_paper_questions(
        self, paper: Paper, db: Optional[AsyncSession] = None
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        Builds the v1 API PaperQuestionResponse dicts with UUID option IDs, shuffled order,
        and per-question obfuscated font & text.
        """
        pqs: List[Dict[str, Any]] = []
        uuid_map_for_hash: List[Dict[str, Tuple[str, str]]] = []

        for pq in paper.paper_questions:
            q = pq.question
            orig_options: Dict[str, str] = (q.content or {}).get("options", {})
            plain_choices, canon_to_uuid, text_to_uuid, ordered_canon = (
                self._build_shuffled_uuid_choices(paper.id, pq)
            )
            mapped_uuid = self._map_saved_answer_to_uuid(
                pq.user_answer, canon_to_uuid, text_to_uuid
            )
            client_user_ans = (
                {"selected_option_id": mapped_uuid}
                if mapped_uuid
                else pq.user_answer
            )
            plain_body = (q.content or {}).get("body", "")
            obf_body, obf_choices, font_data_uri = obfuscate_question_texts(
                plain_body, plain_choices
            )

            opt_uuids = list(obf_choices.keys())
            q_uuid_map: Dict[str, Tuple[str, str]] = {}
            for u_idx, opt_uuid in enumerate(opt_uuids):
                c_key = ordered_canon[u_idx]
                c_txt = str(orig_options.get(c_key, ""))
                q_uuid_map[opt_uuid] = (c_key, c_txt)
            uuid_map_for_hash.append(q_uuid_map)

            pqs.append({
                "id": pq.id,
                "question_type": q.type,
                "content": {
                    "body": obf_body,
                    "options": obf_choices,
                    "obfuscated_font": font_data_uri,
                },
                "score_awarded": pq.score_awarded,
                "max_score": pq.max_score,
                "user_answer": client_user_ans,
                "is_correct": pq.is_correct,
                "manual_comment": pq.manual_comment,
            })

        paper_hash = compute_paper_hash(paper.id, pqs)
        _issued_uuid_maps[paper_hash] = uuid_map_for_hash
        await self.register_hash(paper.id, paper_hash, db=db)
        return pqs, paper_hash

    def _resolve_option_choice(
        self,
        computed_hash: str,
        q_idx: int,
        pq: PaperQuestion,
        ans_uuid: str,
        choices_map: Dict[str, str],
    ) -> Tuple[str, str]:
        """
        Resolves an option UUID from a verified submission to (canonical_key, canonical_plain_text).
        Supports both obfuscated issuances (via _issued_uuid_maps) and direct plaintext fallback.
        """
        hash_map = _issued_uuid_maps.get(computed_hash)
        if hash_map and q_idx < len(hash_map):
            q_map = hash_map[q_idx]
            if ans_uuid in q_map:
                return q_map[ans_uuid]

        # Fallback if server restarted or plaintext was submitted in tests
        selected_text = choices_map[ans_uuid]
        orig_options: Dict[str, str] = (pq.question.content or {}).get("options", {})
        for k, v in orig_options.items():
            if str(v) == selected_text:
                return str(k), str(v)
        # Fallback by character length or index if obfuscated after restart
        opt_keys = list(choices_map.keys())
        pos = opt_keys.index(ans_uuid) if ans_uuid in opt_keys else 0
        orig_items = list(orig_options.items())
        if orig_items:
            k, v = orig_items[pos % len(orig_items)]
            return str(k), str(v)
        return selected_text, selected_text

    async def verify_and_resolve_legacy_submission(
        self,
        paper: Paper,
        submitted_paper: Optional[List[Any]],
        submitted_result: List[Optional[str]],
        submitted_hash: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> Tuple[List[Optional[Dict[str, Any]]], List[Optional[str]]]:
        """
        Verifies the client-submitted paper against the server's retained hash,
        and resolves the client's UUID selections to canonical option keys and option texts.
        Returns: (resolved_user_answers, selected_texts)
        Raises ValueError if paper is missing, tampered with, or has invalid option UUIDs.
        """
        if not submitted_paper or not isinstance(submitted_paper, list):
            raise ValueError("ISSUED_PAPER_REQUIRED")

        if len(submitted_paper) != len(paper.paper_questions):
            raise ValueError("PAPER_LENGTH_MISMATCH")

        computed_hash = compute_paper_hash(paper.id, submitted_paper)
        if submitted_hash and submitted_hash != computed_hash:
            raise ValueError("PAPER_HASH_MISMATCH")

        is_valid = await self.is_valid_hash(paper.id, computed_hash, db=db)
        if not is_valid:
            raise ValueError("INVALID_PAPER_HASH")

        resolved_answers: List[Optional[Dict[str, Any]]] = []
        selected_texts: List[Optional[str]] = []

        for idx, pq in enumerate(paper.paper_questions):
            ans_uuid = submitted_result[idx] if idx < len(submitted_result) else None
            if ans_uuid and ans_uuid != "-1":
                choices_map = _extract_choices_dict(submitted_paper[idx])
                if ans_uuid not in choices_map:
                    raise ValueError(f"INVALID_OPTION_UUID_AT_{idx}")
                canon_key, canon_text = self._resolve_option_choice(
                    computed_hash, idx, pq, ans_uuid, choices_map
                )
                resolved_answers.append({
                    "selected_option_id": canon_key,
                    "selected_text": canon_text,
                    "selected_uuid": ans_uuid,
                })
                selected_texts.append(canon_text)
            else:
                resolved_answers.append(None)
                selected_texts.append(None)

        return resolved_answers, selected_texts

    async def verify_and_resolve_v1_submission(
        self,
        paper: Paper,
        submitted_questions: Optional[List[Any]],
        answers_map: Dict[str, Dict[str, Any]],
        submitted_hash: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Verifies v1 PaperSubmission with issued questions + answers map.
        """
        if not submitted_questions or not isinstance(submitted_questions, list):
            raise ValueError("ISSUED_PAPER_REQUIRED")

        computed_hash = compute_paper_hash(paper.id, submitted_questions)
        if submitted_hash and submitted_hash != computed_hash:
            raise ValueError("PAPER_HASH_MISMATCH")

        is_valid = await self.is_valid_hash(paper.id, computed_hash, db=db)
        if not is_valid:
            raise ValueError("INVALID_PAPER_HASH")

        if len(submitted_questions) != len(paper.paper_questions):
            raise ValueError("PAPER_LENGTH_MISMATCH")

        resolved_map: Dict[str, Dict[str, Any]] = {}
        for idx, pq in enumerate(paper.paper_questions):
            ans_dict = answers_map.get(pq.id)
            if not ans_dict:
                continue
            sel_uuid = ans_dict.get("selected_option_id")
            if sel_uuid:
                choices_map = _extract_choices_dict(submitted_questions[idx])
                if sel_uuid not in choices_map:
                    raise ValueError(f"INVALID_OPTION_UUID_FOR_{pq.id}")
                canon_key, canon_text = self._resolve_option_choice(
                    computed_hash, idx, pq, sel_uuid, choices_map
                )
                resolved_map[pq.id] = {
                    "selected_option_id": canon_key,
                    "selected_text": canon_text,
                    "selected_uuid": sel_uuid,
                }
            else:
                resolved_map[pq.id] = ans_dict

        return resolved_map


# Map of paper_hash -> list of {opt_uuid: (canon_key, canon_text)} per question index
_issued_uuid_maps: Dict[str, List[Dict[str, Tuple[str, str]]]] = {}

paper_issuance_service = PaperIssuanceService()
