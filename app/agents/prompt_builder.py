from typing import List
from app.agents.error_classifier import ClassifiedError

class PromptBuilder:
    @staticmethod
    def build_prompt(data) -> str:
        """
        Формирует промт для LLM на основе классифицированных ошибок.
        Принимает либо словарь сгруппированных логов, либо список ClassifiedError.
        """
        from app.agents.error_classifier import ErrorClassifier

        if isinstance(data, dict):
            classified_errors = ErrorClassifier.classify_errors(data)  # type: ignore[arg-type]
        else:
            classified_errors = list(data)

        # Инструкция для LLM: акцент на конкретных шагах по исправлению
        prompt_intro = (
            "Ты выступаешь в роли AI-эксперта по анализу логов приложений.\n"
            "Ниже перечислены ошибки из журнала. Твоя задача — для каждой ошибки:\n"
            "- определить её критичность (низкая / средняя / высокая);\n"
            "- дать краткую, понятную причину возникновения;\n"
            "- составить подробную рекомендацию по устранению: перечисли конкретные шаги, которые инженер должен выполнить.\n"
            "  Рекомендации должны быть максимально конкретными: укажи, какие классы, методы, таблицы или поля нужно проверить,\n"
            "  нужно ли создать индекс, изменить конфигурацию, добавить проверку на существование, исправить код или данные.\n"
            "Верни ответ **строго** в виде JSON-массива без пояснений, такого вида:\n"
            "[\n"
            "  {\n"
            '    \"message\": \"Описание ошибки\",\n'
            '    \"frequency\": <число>,\n'
            '    \"criticality\": \"низкая | средняя | высокая\",\n'
            '    \"recommendation\": \"Конкретные шаги по исправлению\"\n'
            "  },\n"
            "  ...\n"
            "]\n\n"
            "Ошибки для анализа:\n"
        )

        # берём топ-10 ошибок по частоте
        top_errors = sorted(classified_errors, key=lambda x: x.frequency, reverse=True)[:10]

        logs_summary = ""
        for error in top_errors:
            # включаем имя класса для контекста
            logs_summary += (
                f"- Сообщение: {error.message}\n"
                f"  Класс: {error.class_name}\n"
                f"  Частота: {error.frequency}\n"
                f"  Уровень: {error.level}\n"
                f"  Предварительная критичность: {error.criticality}\n\n"
            )

        return prompt_intro + logs_summary
