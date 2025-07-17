import re
from typing import List, Dict
from collections import defaultdict
from datetime import datetime
from app.models.log_entry import LogEntry

LOG_PATTERN = re.compile(
    r'(?P<timestamp>[\d-]+\s[\d:,]+)\s\[(?P<level>[A-Z]+)\]\s\[(?P<thread>[^\]]+)\]\s(?P<class>[\w\.]+):\s(?P<message>.+)'
)

class LogParser:
    @staticmethod
    def parse_log(log_content: str) -> List[LogEntry]:
        entries = []
        for line in log_content.strip().split("\n"):
            match = LOG_PATTERN.match(line)
            if match:
                entry = LogEntry(
                    timestamp=datetime.strptime(match.group('timestamp'), '%Y-%m-%d %H:%M:%S,%f'),
                    level=match.group('level'),
                    thread=match.group('thread'),
                    class_name=match.group('class'),
                    message=match.group('message').strip()
                )
                entries.append(entry)
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
        # Удаление цифр, UUID, ID обращений и т.п. для нормализации
        message = re.sub(r'[\d\-]{8,}', '<NUM>', message)
        message = re.sub(r'[a-fA-F0-9\-]{36}', '<UUID>', message)
        message = re.sub(r'(\w+Id\s?=\s?[\w-]+)', r'\1=<ID>', message)
        return message
