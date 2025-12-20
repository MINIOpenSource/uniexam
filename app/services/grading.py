from typing import List, Optional
from app.db.models import QuestionType, Question, PaperQuestion

class GradingService:
    def grade_question(self, question: Question, user_answer: dict) -> float:
        """
        Auto-grades a single question.
        Returns the score awarded (0.0 to 1.0 multiplier of max_score, or actual score if we simplify).
        Here we return a multiplier (0.0 for wrong, 1.0 for correct).
        """
        if question.type == QuestionType.SINGLE_CHOICE:
            return self._grade_single_choice(question.answer, user_answer)
        elif question.type == QuestionType.MULTIPLE_CHOICE:
            return self._grade_multiple_choice(question.answer, user_answer)
        elif question.type == QuestionType.FILL_IN_BLANK:
            return self._grade_fill_in_blank(question.answer, user_answer)
        elif question.type == QuestionType.ESSAY:
            return 0.0 # Requires manual grading
        return 0.0

    def _grade_single_choice(self, correct_answer: dict, user_answer: dict) -> float:
        # Expecting structure: {"correct_option_id": "A"} vs {"selected_option_id": "A"}
        correct_id = correct_answer.get("correct_option_id")
        selected_id = user_answer.get("selected_option_id")

        if correct_id and selected_id and correct_id == selected_id:
            return 1.0
        return 0.0

    def _grade_multiple_choice(self, correct_answer: dict, user_answer: dict) -> float:
        # Expecting: {"correct_option_ids": ["A", "C"]} vs {"selected_option_ids": ["A", "C"]}
        correct_ids = set(correct_answer.get("correct_option_ids", []))
        selected_ids = set(user_answer.get("selected_option_ids", []))

        if not correct_ids:
            return 0.0

        if correct_ids == selected_ids:
            return 1.0
        # Optional: Partial credit logic can go here
        return 0.0

    def _grade_fill_in_blank(self, correct_answer: dict, user_answer: dict) -> float:
        # Expecting: {"blanks": ["answer1", "answer2"]} (ordered) vs {"answers": ["answer1", "answer2"]}
        correct_blanks = correct_answer.get("blanks", [])
        user_blanks = user_answer.get("answers", [])

        if not correct_blanks:
            return 0.0

        correct_count = 0
        total_blanks = len(correct_blanks)

        for i in range(min(len(correct_blanks), len(user_blanks))):
            if str(correct_blanks[i]).strip().lower() == str(user_blanks[i]).strip().lower():
                correct_count += 1

        return correct_count / total_blanks if total_blanks > 0 else 0.0

grading_service = GradingService()
