from app.db.models import QuestionType, Question


class GradingService:
    def grade_question(self, question: Question, user_answer: dict) -> float:
        """
        Auto-grades a single question.
        Returns a multiplier (0.0 for wrong, 1.0 for correct).
        """
        if not isinstance(user_answer, dict):
            return 0.0
        if question.type == QuestionType.SINGLE_CHOICE:
            return self._grade_single_choice(question, user_answer)
        elif question.type == QuestionType.MULTIPLE_CHOICE:
            return self._grade_multiple_choice(question.answer, user_answer)
        elif question.type == QuestionType.FILL_IN_BLANK:
            return self._grade_fill_in_blank(question.answer, user_answer)
        elif question.type == QuestionType.ESSAY:
            return 0.0  # Requires manual grading
        return 0.0

    def _grade_single_choice(self, question: Question, user_answer: dict) -> float:
        correct_answer = question.answer or {}
        correct_id = correct_answer.get("correct_option_id")
        selected_id = user_answer.get("selected_option_id")

        if correct_id and selected_id and str(correct_id) == str(selected_id):
            return 1.0

        options = (question.content or {}).get("options", {})
        if correct_id and isinstance(options, dict):
            correct_text = options.get(str(correct_id))
            selected_text = user_answer.get("selected_text")
            if correct_text is not None and selected_text is not None and str(correct_text) == str(selected_text):
                return 1.0

        return 0.0

    def _grade_multiple_choice(self, correct_answer: dict, user_answer: dict) -> float:
        correct_ids = set(correct_answer.get("correct_option_ids", []))
        selected_ids = set(user_answer.get("selected_option_ids", []))

        if not correct_ids:
            return 0.0

        if correct_ids == selected_ids:
            return 1.0
        return 0.0

    def _grade_fill_in_blank(self, correct_answer: dict, user_answer: dict) -> float:
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
