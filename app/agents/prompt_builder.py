from typing import List, Dict
from app.agents.error_classifier import ClassifiedError

class PromptBuilder:
    @staticmethod
    def build_prompt(data) -> str:
        """
        Формирует промт для LLM на основе классифицированных ошибок.

        Поддерживает два формата входных данных:
        1. Список объектов ClassifiedError.
        2. Словарь вида {нормализованное_сообщение: [LogEntry, ...]}.
        """
        from app.agents.error_classifier import ErrorClassifier

        # Принимаем либо словарь, либо список.
        if isinstance(data, dict):
            classified_errors = ErrorClassifier.classify_errors(data)  # type: ignore[arg-type]
        else:
            classified_errors = list(data)

        prompt_intro = (
            "Ты выступаешь в роли AI-эксперта по анализу логов приложений.\n\n"
            "Ниже представлен список ошибок из логов информационной системы.\n"
            "Твоя задача — для каждой ошибки:\n"
            "- определить критичность (низкая / средняя / высокая),\n"
            "- дать краткую причину возникновения ошибки,\n"
            "- дать конкретную рекомендацию — что инженер должен сделать, чтобы устранить проблему.\n\n"
            "Рекомендация должна быть **конкретной инструкцией к действию**, например:\n"
            "- завести задачу на разработку с указанием типа ошибки,\n"
            "- проверить настройки конкретного сервиса,\n"
            "- изменить конфигурацию, пересоздать данные, исправить код и т.п.\n\n"
            "Формат ответа — строго в JSON-массиве **без пояснений**, например:\n"
            "[\n"
            "  {\n"
            '    \"message\": \"<оригинальное сообщение>\",\n'
            '    \"frequency\": <число>,\n'
            '    \"criticality\": \"низкая | средняя | высокая\",\n'
            '    \"recommendation\": \"<что конкретно сделать>\"\n'
            "  },\n"
            "  ...\n"
            "]\n\n"
            "Вот список ошибок:\n"
        )

        # Берём топ-10 ошибок по частоте
        top_errors = sorted(classified_errors, key=lambda x: x.frequency, reverse=True)[:10]

        logs_summary = ""
        for error in top_errors:
            logs_summary += (
                f"- ({error.level}) {error.message} [class: {error.level}, count: {error.frequency}]\n"
            )

        return prompt_intro + logs_summary
