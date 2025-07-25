from typing import Dict, List
from app.models.log_entry import LogEntry
from pydantic import BaseModel


class ClassifiedError(BaseModel):
    """
    Представление классифицированной ошибки.

    Атрибуты:
      message: нормализованное сообщение об ошибке (используется для запроса
                к LLM);
      original_message: несколько исходных сообщений (до 3), объединённых
                через пустую строку, чтобы дать LLM больше контекста;
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
    CRITICALITY_MAP = {
        'ERROR': 'высокая',
        'WARN': 'средняя',
        'INFO': 'низкая',
        'TRACE': 'низкая'
    }

    @staticmethod
    def classify_errors(grouped_entries: Dict[str, List[LogEntry]]) -> List[ClassifiedError]:
        """
        Классифицирует сгруппированные записи журнала. Для каждого
        нормализованного сообщения собирает до трёх исходных сообщений для
        предоставления более насыщенного контекста.

        Args:
            grouped_entries: словарь, где ключ — нормализованное сообщение,
                а значение — список LogEntry для этой группы.

        Returns:
            Список экземпляров ClassifiedError с заполненными полями.
        """
        classified: List[ClassifiedError] = []
        for normalized_msg, entries in grouped_entries.items():
            # определяем наиболее критичный уровень в группе
            levels = [entry.level for entry in entries]
            most_critical_level = ErrorClassifier.determine_most_critical_level(levels)

            # собрать до трёх уникальных исходных сообщений
            examples: List[str] = []
            seen: set[str] = set()
            for entry in entries:
                if entry.message not in seen:
                    examples.append(entry.message)
                    seen.add(entry.message)
                if len(examples) >= 3:
                    break
            original_combined = "\n---\n".join(examples)

            class_name = entries[0].class_name if entries else ""

            classified.append(ClassifiedError(
                message=normalized_msg,
                original_message=original_combined,
                frequency=len(entries),
                level=most_critical_level,
                class_name=class_name,
                criticality=ErrorClassifier.CRITICALITY_MAP.get(most_critical_level, 'низкая')
            ))
        return classified

    @staticmethod
    def determine_most_critical_level(levels: List[str]) -> str:
        priority_order = ['ERROR', 'WARN', 'INFO', 'TRACE']
        for level in priority_order:
            if level in levels:
                return level
        return 'INFO'