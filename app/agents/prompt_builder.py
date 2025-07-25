from typing import Iterable, List, Union
from app.agents.error_classifier import ClassifiedError, ErrorClassifier


class PromptBuilder:
    """Utility for constructing prompts for the GigaChat LLM."""

    @staticmethod
    def build_prompt(data: Union[dict, Iterable[ClassifiedError]]) -> str:
        """
        Build a prompt for the language model from either grouped log entries
        (a mapping of normalized messages to lists of log entries) or an iterable
        of ClassifiedError objects. Only the top 10 most frequent errors are
        included to keep the prompt concise.

        Args:
            data: Either a dictionary returned by LogParser.group_by_normalized_message
                or an iterable of ClassifiedError instances.

        Returns:
            A string containing the complete prompt to send to the LLM.
        """
        # Normalize the input into a list of ClassifiedError objects
        if isinstance(data, dict):
            classified_errors = ErrorClassifier.classify_errors(data)  # type: ignore[arg-type]
        else:
            # Ensure we have a concrete list, not just a generator
            classified_errors = list(data)

        # Instructional preamble for the LLM. This text explains the role and
        # responsibilities of the assistant, sets expectations for the style and
        # depth of the response, and defines the JSON schema for the output.
        prompt_intro = (
            "Ты опытный инженер по разработке и эксплуатации backend‑приложений "
            "(например, Java/Spring). Тебе предоставлен список уникальных ошибок, "
            "обнаруженных в логах приложения. Каждая запись содержит нормализованное "
            "описание ошибки, пример исходного сообщения из лога, имя класса, "
            "частоту появления и предварительную оценку критичности.\n"
            "Твоя задача для каждой ошибки:\n"
            "1. При необходимости скорректировать оценку критичности (низкая/средняя/высокая) с учётом контекста.\n"
            "2. Кратко описать возможную первопричину возникновения проблемы: какие компоненты, конфигурации, таблицы, методы или внешние сервисы могут вызывать эту ошибку.\n"
            "3. Сформулировать подробную и конкретную рекомендацию по устранению проблемы. Избегай общих фраз; перечисли конкретные шаги, которые должен выполнить инженер: какие классы, методы, таблицы, поля, индексы или параметры конфигурации нужно проверить, изменить или создать; какие команды выполнить; какие логи или конфигурации дополнительно изучить.\n"
            "4. Если для точного диагноза недостаточно информации, укажи, какую дополнительную информацию нужно собрать (например, полный stacktrace, SQL-запрос или конфигурационный файл).\n\n"
            "Верни ответ строго в виде JSON‑массива без какого‑либо поясняющего текста. "
            "Каждый элемент массива должен иметь следующие поля:\n"
            "    \"message\" — нормализованное описание ошибки;\n"
            "    \"frequency\" — частота появления в логах;\n"
            "    \"criticality\" — окончательная оценка критичности (низкая/средняя/высокая);\n"
            "    \"recommendation\" — подробные конкретные шаги по исправлению (в виде одного текстового поля).\n\n"
            "Пример структуры ответа:\n"
            "[\n"
            "  {\n"
            "    \"message\": \"duplicate key value violates unique constraint ...\",\n"
            "    \"frequency\": 42,\n"
            "    \"criticality\": \"высокая\",\n"
            "    \"recommendation\": \"Проверьте таблицу ...: убедитесь, что поле ... является уникальным; добавьте индекс ...; скорректируйте код метода ... для обработки дубликатов.\"\n"
            "  },\n"
            "  ...\n"
            "]\n\n"
            "Ниже приведён список ошибок для анализа:\n"
            "\n"
            "Важно: не добавляй комментариев (строки, начинающиеся с //) и лишних полей в JSON, и обязательно указывай частоту как одно целое число, без массивов.\n"
        )

        # Sort errors by descending frequency and limit to the top 10
        top_errors = sorted(classified_errors, key=lambda x: x.frequency, reverse=True)[:10]

        # Build the summary section that presents each error to the LLM. Including
        # both the normalized message and an example original message provides
        # additional context that improves the quality of the LLM's recommendations.
        logs_summary = ""
        for err in top_errors:
            example_message = err.original_message or err.message
            logs_summary += (
                f"- Ошибка: {err.message}\n"
                f"  Пример сообщения: {example_message}\n"
                f"  Источник (класс): {err.class_name}\n"
                f"  Частота: {err.frequency}\n"
                f"  Уровень лога: {err.level}\n"
                f"  Предварительная критичность: {err.criticality}\n\n"
            )

        return prompt_intro + logs_summary