from typing import Dict, List
from app.models.log_entry import LogEntry
from pydantic import BaseModel

class ClassifiedError(BaseModel):
    message: str
    frequency: int
    level: str
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
        classified = []
        for normalized_msg, entries in grouped_entries.items():
            levels = [entry.level for entry in entries]
            most_critical_level = ErrorClassifier.determine_most_critical_level(levels)

            classified.append(ClassifiedError(
                message=normalized_msg,
                frequency=len(entries),
                level=most_critical_level,
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
