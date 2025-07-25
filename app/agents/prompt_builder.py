from typing import List
from app.agents.error_classifier import ClassifiedError

class PromptBuilder:
    @staticmethod
    def build_prompt(data) -> str:
        """
        Формирует промт для LLM на основе классифицированных ошибок.
        Принимает либо словарь, либо список ClassifiedError.
        """
        from app.agents.error_classifier import ErrorClassifier

        if isinstance(data, dict):
            classified_errors = ErrorClassifier.classify_errors(data)  # type: ignore[arg-type]
        else:
            classified_errors = list(data)

        prompt_intro = (
            "Ты выступаешь в роли AI-эксперта по анализу логов приложений.\n"
            "Проанализируй 10 ошибок ниже. Для каждой из них:\n"
            "- Определи её критичность: высокая / средняя / низкая\n"
            "- Сформулируй краткую причину возникновения\n"
            "- Дай рекомендацию для устранения\n\n"
            "Важно: строго проанализируй все 10 ошибок!\n"
            "Ответ верни строго в JSON-массиве такого вида:\n"
            "[\n"
            "  {\n"
            '    \"message\": \"Описание ошибки\",\n'
            '    \"frequency\": N,\n'
            '    \"criticality\": \"низкая / средняя / высокая\",\n'
            '    \"recommendation\": \"Что сделать\"\n'
            "  },\n"
            "  ... (ещё 9)\n"
            "]\n\n"
            "Ошибки для анализа:\n"
        )

        # берём топ-10 ошибок по частоте
        top_errors = sorted(classified_errors, key=lambda x: x.frequency, reverse=True)[:10]

        logs_summary = ""
        for error in top_errors:
            # включаем имя класса для большего контекста
            logs_summary += (
                f"- Сообщение: {error.message}\n"
                f"  Класс: {error.class_name}\n"
                f"  Частота: {error.frequency}\n"
                f"  Уровень: {error.level}\n"
                f"  Предварительная критичность: {error.criticality}\n\n"
            )

        return prompt_intro + logs_summary