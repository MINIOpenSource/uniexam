import json
import random
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import QuestionBank, Question, QuestionType

DIFFICULTY_MAP = {
    "easy": 1,
    "hybrid": 2,
    "hard": 3,
}

OPTION_LABELS = ["A", "B", "C", "D", "E", "F", "G", "H"]


async def seed_question_banks(session: AsyncSession) -> None:
    """
    Imports legacy question banks from data/library/index.json and corresponding
    JSON files into SQLite if they do not already exist in the database.
    """
    library_dir: Path = settings.DATA_DIR / "library"
    index_file = library_dir / "index.json"
    if not index_file.exists():
        return

    try:
        index_data = json.loads(index_file.read_text(encoding="utf-8"))
    except Exception:
        return

    rng = random.Random(42)

    for bank_meta in index_data:
        bank_key = bank_meta.get("id")
        if not bank_key:
            continue

        result = await session.execute(select(QuestionBank).where(QuestionBank.id == bank_key))
        existing_bank = result.scalars().first()
        if existing_bank:
            continue

        bank_file = library_dir / f"{bank_key}.json"
        if not bank_file.exists():
            continue

        try:
            raw_questions = json.loads(bank_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        bank = QuestionBank(
            id=bank_key,
            name=bank_meta.get("name", bank_key),
            description=bank_meta.get("description"),
        )
        session.add(bank)
        await session.flush()

        difficulty_val = DIFFICULTY_MAP.get(bank_key, 1)

        for item in raw_questions:
            body = item.get("body", "").strip()
            if not body:
                continue

            q_type_str = item.get("question_type", "single_choice")
            if q_type_str == "multiple_choice":
                q_type = QuestionType.MULTIPLE_CHOICE
            elif q_type_str == "fill_in_blank":
                q_type = QuestionType.FILL_IN_BLANK
            elif q_type_str in ("essay", "essay_question"):
                q_type = QuestionType.ESSAY
            else:
                q_type = QuestionType.SINGLE_CHOICE

            if q_type == QuestionType.SINGLE_CHOICE:
                correct_pool = item.get("correct_choices") or []
                incorrect_pool = item.get("incorrect_choices") or []
                if not correct_pool or not incorrect_pool:
                    continue

                correct_text = rng.choice(correct_pool)
                distractors = rng.sample(incorrect_pool, min(3, len(incorrect_pool)))

                combined = [(correct_text, True)] + [(d, False) for d in distractors]
                rng.shuffle(combined)

                options = {}
                correct_option_id = "A"
                for idx, (opt_text, is_corr) in enumerate(combined):
                    label = OPTION_LABELS[idx]
                    options[label] = opt_text
                    if is_corr:
                        correct_option_id = label

                content = {"body": body, "options": options}
                answer = {"correct_option_id": correct_option_id}
            elif q_type == QuestionType.MULTIPLE_CHOICE:
                correct_pool = item.get("correct_choices") or []
                incorrect_pool = item.get("incorrect_choices") or []
                num_correct = item.get("num_correct_to_select") or len(correct_pool)
                chosen_correct = rng.sample(correct_pool, min(num_correct, len(correct_pool)))
                chosen_incorrect = rng.sample(incorrect_pool, min(4, len(incorrect_pool)))
                combined = [(c, True) for c in chosen_correct] + [(d, False) for d in chosen_incorrect]
                rng.shuffle(combined)

                options = {}
                correct_ids = []
                for idx, (opt_text, is_corr) in enumerate(combined[:len(OPTION_LABELS)]):
                    label = OPTION_LABELS[idx]
                    options[label] = opt_text
                    if is_corr:
                        correct_ids.append(label)

                content = {"body": body, "options": options}
                answer = {"correct_option_ids": correct_ids}
            elif q_type == QuestionType.FILL_IN_BLANK:
                content = {"body": body}
                answer = {"blanks": item.get("correct_fillings") or []}
            else:
                content = {"body": body}
                answer = {"reference": item.get("standard_answer_text", "")}

            session.add(
                Question(
                    bank_id=bank.id,
                    type=q_type,
                    content=content,
                    answer=answer,
                    difficulty=difficulty_val,
                )
            )

        await session.commit()
