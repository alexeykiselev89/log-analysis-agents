from typing import Dict, List

from app.models.log_entry import LogEntry
from pydantic import BaseModel


class ClassifiedError(BaseModel):
    """
    Представление классифицированной ошибки.

    message: нормализованное сообщение об ошибке (для запроса к LLM);
    original_message: до пяти различных исходных сообщений, объединённых
      через пустую строку (даёт модели больше контекста);
    frequency: количество вхождений ошибки в логе;
    level: наиболее критичный уровень логирования среди элементов группы;
    class_name: имя класса (например, Java‑класс) первой записи в группе;
    criticality: оценка критичности (высокая/средняя/низкая).
    """

    message: str
    original_message: str
    frequency: int
    level: str
    class_name: str
    criticality: str


class ErrorClassifier:
    """
    Классифицирует группы ошибок по уровню и частоте.

    В новой версии учитывает не только уровень логирования, но и
    количество повторов: часто повторяющиеся предупреждения повышают
    критичность, а редкие ошибки могут быть средней важности. Также
    собирает до пяти уникальных примеров сообщений для каждой ошибки,
    чтобы передать LLM больше контекста.
    """

    LEVEL_CRITICALITY = {
        'ERROR': 'высокая',
        'WARN': 'средняя',
        'INFO': 'низкая',
        'TRACE': 'низкая',
    }

    @staticmethod
    def classify_errors(grouped_entries: Dict[str, List[LogEntry]]) -> List[ClassifiedError]:
        """
        Преобразует сгруппированные записи логов в список объектов `ClassifiedError`.

        Для каждой группы записей с одинаковым нормализованным сообщением:
        - определяется наиболее критичный уровень логирования;
        - по уровню выбирается базовая оценка критичности;
        - собираются до пяти уникальных примеров исходных сообщений для контекста;
        - извлекается имя класса из первой записи и подсчитывается частота повторений;
        - при необходимости критичность корректируется в зависимости от частоты.

        :param grouped_entries: словарь, где ключ — нормализованное сообщение, а
            значение — список записей `LogEntry` с таким сообщением.
        :return: список объектов `ClassifiedError`.
        """
        # Инициализируем список для классифицированных ошибок
        classified: List[ClassifiedError] = []
        # normalized_msg — нормализованное сообщение, entries — список записей с таким сообщением
        for normalized_msg, entries in grouped_entries.items():
            # Определяем наиболее критичный уровень в группе
            levels = [entry.level for entry in entries]
            base_level = ErrorClassifier.determine_most_critical_level(levels)
            # Получаем базовую критичность из словаря по уровню
            base_crit = ErrorClassifier.LEVEL_CRITICALITY.get(base_level, 'низкая')

            # Собираем до пяти уникальных сообщений для контекста, чтобы дать LLM больше информации
            examples: List[str] = []
            seen: set[str] = set()
            for entry in entries:
                if entry.message not in seen:
                    examples.append(entry.message)
                    seen.add(entry.message)
                if len(examples) >= 5:
                    break
            original_combined = "\n---\n".join(examples)

            # Имя класса первой записи и количество повторов
            class_name = entries[0].class_name if entries else ""
            frequency = len(entries)
            # Корректируем критичность с учётом частоты появлений
            criticality = ErrorClassifier.adjust_criticality(base_crit, base_level, frequency)

            # Формируем объект ClassifiedError и добавляем его в список
            classified.append(ClassifiedError(
                message=normalized_msg,
                original_message=original_combined,
                frequency=frequency,
                level=base_level,
                class_name=class_name,
                criticality=criticality,
            ))
        return classified

    @staticmethod
    def determine_most_critical_level(levels: List[str]) -> str:
        """
        Возвращает наиболее приоритетный уровень из списка уровней.

        Приоритет определяется в порядке: ``ERROR`` > ``WARN`` > ``INFO`` > ``TRACE``.  Если
        ни один из этих уровней не найден, возвращается ``'INFO'``.

        :param levels: список уровней логирования, обнаруженных в группе.
        :return: строковое значение уровня с наивысшим приоритетом.
        """
        priority_order = ['ERROR', 'WARN', 'INFO', 'TRACE']
        for lvl in priority_order:
            if lvl in levels:
                return lvl
        return 'INFO'

    @staticmethod
    def adjust_criticality(base_crit: str, level: str, frequency: int) -> str:
        """
        Корректирует критичность на основании уровня логирования и частоты:
        * для ERROR: > 50 повторов → высокая, иначе средняя;
        * для WARN: 51–200 → средняя, > 200 → высокая;
        * INFO и TRACE остаются низкими.
        """
        if level == 'ERROR':
            if frequency > 50:
                return 'высокая'
            return 'средняя'
        if level == 'WARN':
            if frequency > 200:
                return 'высокая'
            if frequency > 50:
                return 'средняя'
            return base_crit
        return base_crit