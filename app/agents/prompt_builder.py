from typing import List
from app.agents.error_classifier import ClassifiedError

class PromptBuilder:
    @staticmethod
    def build_prompt(classified_errors: List[ClassifiedError]) -> str:
        prompt_intro = (
            "Проанализируй следующий лог приложения. "
            "Определи ошибки и сбои в работе, их возможные причины, "
            "предложи рекомендации для устранения, оцени критичность каждой проблемы.\n\n"
            "Формат ответа: JSON с полями:\n"
            "[\n"
            "  {\n"
            '    "message": "Описание ошибки",\n'
            '    "frequency": N,\n'
            '    "criticality": "низкая / средняя / высокая",\n'
            '    "recommendation": "Что сделать"\n'
            "  }\n"
            "]\n\n"
            "Логи для анализа:\n"
        )

        logs_summary = ""
        for error in classified_errors:
            logs_summary += (
                f"- Сообщение: {error.message}\n"
                f"  Частота: {error.frequency}\n"
                f"  Уровень: {error.level}\n"
                f"  Предварительная критичность: {error.criticality}\n\n"
            )

        return prompt_intro + logs_summary
