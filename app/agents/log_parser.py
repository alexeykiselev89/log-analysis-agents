import re
from typing import List, Dict
from collections import defaultdict
from datetime import datetime
from app.models.log_entry import LogEntry

# Обновлённый шаблон: поддерживает пробел в [WARN ] и необязательные поля
LOG_PATTERN = re.compile(
    r'(?P<timestamp>[\d\-]+\s[\d:,]+)\s\[(?P<level>[A-Z ]+)\]\s\[(?P<thread>[^\]]*)\]\s(?P<class>[\w\.]+):\s(?P<message>.+)'
)

class LogParser:
    @staticmethod
    def parse_log(log_content: str) -> List[LogEntry]:
        entries = []
        for line in log_content.strip().split("\n"):
            match = LOG_PATTERN.match(line)
            if match:
                try:
                    entry = LogEntry(
                        timestamp=datetime.strptime(match.group('timestamp'), '%Y-%m-%d %H:%M:%S,%f'),
                        level=match.group('level').strip(),
                        thread=match.group('thread'),
                        class_name=match.group('class'),
                        message=match.group('message').strip()
                    )
                    entries.append(entry)
                except Exception as e:
                    print(f"Ошибка парсинга строки: {line} — {e}")
        return entries

    @staticmethod
    def group_by_normalized_message(entries: List[LogEntry]) -> Dict[str, List[LogEntry]]:
        grouped = defaultdict(list)
        for entry in entries:
            normalized = LogParser.normalize_message(entry.message)
            grouped[normalized].append(entry)
        return grouped

    @staticmethod
    def normalize_message(message: str) -> str:
        """
        Мягкая нормализация:
        — убираем ID, UUID, числа больше 5 цифр (таймстемпы, значения, размеры)
        — но оставляем смысл (ключевые слова, текст ошибок)
        """
        message = re.sub(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b', '<UUID>', message)
        message = re.sub(r'user_id=\d+', 'user_id=<ID>', message)
        message = re.sub(r'order_id=\d+', 'order_id=<ID>', message)
        message = re.sub(r'\b\d{5,}\b', '<NUM>', message)
        message = re.sub(r'\b(duration|latency|timeout)=\d+ms\b', r'\1=<MS>', message)
        return message.lower().strip()
