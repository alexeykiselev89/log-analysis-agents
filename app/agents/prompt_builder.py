from typing import List
from app.agents.error_classifier import ClassifiedError

class PromptBuilder:
    @staticmethod
    def build_prompt(classified_errors: List[ClassifiedError]) -> str:
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
            '    "message": "Описание ошибки",\n'
            '    "frequency": N,\n'
            '    "criticality": "низкая / средняя / высокая",\n'
            '    "recommendation": "Что сделать"\n'
            "  },\n"
            "  ... (ещё 9 штук)\n"
            "]\n\n"
            "Ошибки для анализа:\n"
        )

        # 🔼 сортируем по частоте, берем топ-10
        top_errors = sorted(classified_errors, key=lambda x: x.frequency, reverse=True)[:10]

        logs_summary = ""
        for error in top_errors:
            logs_summary += (
                f"- Сообщение: {error.message}\n"
                f"  Частота: {error.frequency}\n"
                f"  Уровень: {error.level}\n"
                f"  Предварительная критичность: {error.criticality}\n\n"
            )

        return prompt_intro + logs_summary
