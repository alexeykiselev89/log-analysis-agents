import re
from typing import List, Dict
from collections import defaultdict
from datetime import datetime
from app.models.log_entry import LogEntry

LOG_PATTERN = re.compile(
    r'^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) '
    r'\[(?P<level>[A-Z]+)\] '
    r'\[(?P<thread>[^\]]+)\] '
    r'(?P<class>[^\:]+): (?P<message>.+)$'
)

ERROR_LEVELS = {"ERROR", "WARN", "EXCEPTION"}

class LogParser:
    @staticmethod
    def parse_log(log_content: str) -> List[LogEntry]:
        entries = []
        buffer = ""
        last_entry = None

        lines = log_content.strip().splitlines()

        for i, line in enumerate(lines):
            line = line.strip()

            # Если начинается новая строка лога
            match = LOG_PATTERN.match(line)
            if match:
                level = match.group("level").upper()
                if level not in ERROR_LEVELS:
                    continue

                if last_entry:
                    entries.append(last_entry)

                last_entry = LogEntry(
                    timestamp=datetime.strptime(match.group("timestamp"), "%Y-%m-%d %H:%M:%S,%f"),
                    level=level,
                    thread=match.group("thread"),
                    class_name=match.group("class"),
                    message=match.group("message").strip()
                )
            elif last_entry and (line.startswith("at ") or line.startswith("Caused by") or line.startswith("org.")):
                # Продолжение предыдущей ошибки (stacktrace)
                last_entry.message += " " + line.strip()
            else:
                # Неизвестный формат — пропускаем
                continue

        if last_entry:
            entries.append(last_entry)

        print(f"🔎 [SUMMARY] Успешно распарсено строк: {len(entries)}")
        return entries

    @staticmethod
    def group_by_normalized_message(entries: List[LogEntry]) -> Dict[str, List[LogEntry]]:
        grouped = defaultdict(list)
        for entry in entries:
            normalized = LogParser.normalize_message(entry.message)
            if normalized.lower() == "произошла ошибка":
                print(f"⚠️  [SKIPPED] Строка содержит обобщённое сообщение: {entry.message}")
                continue
            grouped[normalized].append(entry)
        return grouped

    @staticmethod
    def normalize_message(message: str) -> str:
        # Сохраняем первые ключевые фразы (например, org.postgresql.PSQLException)
        preserved = ""
        if match := re.match(r'^(org\.[\w\.]+):', message):
            preserved = match.group(1)

        # Удаление ID, HASH, UUID и чисел
        message = re.sub(r'[a-fA-F0-9\-]{36}', '<UUID>', message)
        message = re.sub(r'\b\d{8,}\b', '<NUM>', message)
        message = re.sub(r'[a-fA-F0-9]{32,}', '<HASH>', message)
        message = re.sub(r'([a-zA-Z0-9_-]*id[a-zA-Z0-9_-]*)\s*=\s*[a-zA-Z0-9_-]+', r'\1=<ID>', message, flags=re.IGNORECASE)

        result = preserved + ": " + message if preserved else message
        return result.strip()
