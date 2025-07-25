from typing import Dict, List
from app.models.log_entry import LogEntry
from pydantic import BaseModel

class ClassifiedError(BaseModel):
    """
    Представление классифицированной ошибки.

    Атрибуты:
      message: нормализованное сообщение об ошибке (используется для запроса к LLM);
      original_message: одно из исходных сообщений, из которых построена эта группа;
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
        Классифицирует сгруппированные записи журнала.
        """
        classified: List[ClassifiedError] = []
        for normalized_msg, entries in grouped_entries.items():
            # определяем наиболее критичный уровень в группе
            levels = [entry.level for entry in entries]
            most_critical_level = ErrorClassifier.determine_most_critical_level(levels)

            # берём первое исходное сообщение и имя класса для отчёта
            original = entries[0].message if entries else normalized_msg
            class_name = entries[0].class_name if entries else ""

            classified.append(ClassifiedError(
                message=normalized_msg,
                original_message=original,
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
