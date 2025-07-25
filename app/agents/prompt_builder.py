from typing import Iterable, List, Union

from app.agents.error_classifier import ClassifiedError, ErrorClassifier


class PromptBuilder:
    """Utility for constructing prompts for the GigaChat LLM.

    This builder assembles an instruction prompt and a summary of the
    classified errors.  It limits the number of included errors to the
    top 10 by frequency to avoid token overflows.

    The instructions have been revised to request additional fields
    (`root_cause` and `info_needed`) and to demand a numbered list of
    concrete actions in the `recommendation` field, so that an engineer
    reading the report can follow clear steps.
    """

    @staticmethod
    def build_prompt(data: Union[dict, Iterable[ClassifiedError]]) -> str:
        """
        Build a prompt for the language model from either grouped log
        entries or an iterable of ClassifiedError objects.

        Args:
            data: A mapping from normalised messages to lists of log
                entries, or an iterable of ClassifiedError objects.

        Returns:
            A string containing the full prompt to send to the LLM.
        """
        # Normalise the input into a list of ClassifiedError objects
        if isinstance(data, dict):
            classified_errors = ErrorClassifier.classify_errors(data)  # type: ignore[arg-type]
        else:
            classified_errors = list(data)

        # Instruction for the LLM.  We explicitly require the assistant
        # to return a JSON array of objects with fields `message`,
        # `frequency`, `criticality`, `root_cause`, `recommendation`, and
        # `info_needed`.  The `recommendation` must be a numbered list of
        # at least five concrete steps.  We also instruct the model to
        # adjust criticality only when justified (e.g. frequency and log
        # level suggest otherwise) and to explain why it did so.
        prompt_intro = (
            "Ты опытный инженер по разработке и эксплуатации backend‑"
            "приложений (например, Java/Spring). Тебе предоставлен список "
            "уникальных ошибок из логов. Каждая запись содержит "
            "нормализованное описание ошибки, примеры исходных сообщений "
            "(включая stacktrace), имя класса, частоту и предварительную "
            "критичность.\n"
            "Твоя задача для каждой ошибки:\n"
            "1. При необходимости скорректируй оценку критичности "
            "(низкая/средняя/высокая), опираясь на частоту появления, "
            "уровень логирования и серьёзность последствий. Если ты "
            "изменяешь критичность, укажи причину в описании первопричины.\n"
            "2. Используя примеры сообщений и stacktrace, заполни поле "
            "`root_cause`: кратко опиши, какие компоненты, конфигурации, "
            "таблицы, методы или внешние сервисы являются вероятной "
            "первопричиной ошибки.\n"
            "3. В поле `recommendation` перечисли конкретные действия для "
            "устранения проблемы, в виде пронумерованного списка (1., 2., 3., …). "
            "Укажи как минимум пять последовательных шагов: какие классы, методы, "
            "таблицы, поля, индексы или параметры конфигурации нужно проверить, "
            "изменить или создать; какие команды или SQL‑запросы выполнить; какие "
            "логи, метрики или конфигурации дополнительно изучить.\n"
            "4. При возможности приведи пример кода, SQL‑запроса или "
            "конфигурации, который поможет исправить ошибку.\n"
            "5. Опиши, как проверить эффективность решения: какие тесты "
            "выполнить, какие логи или отчёты проанализировать.\n"
            "6. Если для точного диагноза недостаточно информации, заполни поле "
            "`info_needed` — перечисли, какие данные необходимо собрать (например, "
            "полный stacktrace, конкретный SQL‑запрос, конфигурационный файл, "
            "дамп таблицы и т. д.). Если всей информации достаточно, укажи null.\n\n"
            "Верни ответ строго в виде JSON‑массива без поясняющих текстов и без "
            "комментариев `//`. Каждый объект в массиве должен иметь поля:\n"
            "    \"message\" — нормализованное описание ошибки;\n"
            "    \"frequency\" — частота появления в логах (одно число);\n"
            "    \"criticality\" — окончательная оценка критичности;\n"
            "    \"root_cause\" — краткое описание первопричины;\n"
            "    \"recommendation\" — пронумерованный список шагов по исправлению;\n"
            "    \"info_needed\" — какие дополнительные данные собрать, либо null.\n\n"
            "Пример структуры ответа:\n"
            "[\n"
            "  {\n"
            "    \"message\": \"duplicate key value violates unique constraint ...\",\n"
            "    \"frequency\": 42,\n"
            "    \"criticality\": \"высокая\",\n"
            "    \"root_cause\": \"Отсутствие уникального индекса на поле appeal_id в таблице appeals_dzo, что приводит к конфликтам при вставке.\",\n"
            "    \"recommendation\": \"1. Проверьте существование уникального индекса на appeals_dzo.appeal_id; 2. При необходимости создайте индекс; 3. Проанализируйте код saveAppeal() на предмет проверки дубликатов; 4. Дополнительно логируйте идентификаторы при сохранении; 5. Проверьте связанные таблицы на наличие неконсистентных данных.\",\n"
            "    \"info_needed\": null\n"
            "  },\n"
            "  ...\n"
            "]\n\n"
            "Ниже приведён список ошибок для анализа:\n\n"
            "Важно: не добавляй комментариев (строки, начинающиеся с //) и "
            "не вводи дополнительные поля, и обязательно указывай частоту как "
            "одно целое число.\n"
        )

        # Sort errors by descending frequency and limit to the top 10
        top_errors = sorted(classified_errors, key=lambda x: x.frequency, reverse=True)[:10]

        # Compose a summary of the errors for the LLM
        logs_summary = ""
        for err in top_errors:
            example_message = err.original_message or err.message
            if '\n---\n' in example_message:
                examples_label = "Примеры сообщений"
            else:
                examples_label = "Пример сообщения"
            logs_summary += (
                f"- Ошибка: {err.message}\n"
                f"  {examples_label}: {example_message}\n"
                f"  Источник (класс): {err.class_name}\n"
                f"  Частота: {err.frequency}\n"
                f"  Уровень лога: {err.level}\n"
                f"  Предварительная критичность: {err.criticality}\n\n"
            )

        return prompt_intro + logs_summary