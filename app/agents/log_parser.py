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
        last_entry: LogEntry | None = None
        lines = log_content.strip().splitlines()
        for line in lines:
            line = line.strip()
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
                    message=match.group("message").strip(),
                )
            elif last_entry and (line.startswith("at ") or line.startswith("Caused by") or line.startswith("org.")):
                # Append stacktrace lines to the previous entry
                last_entry.message += " " + line.strip()
            else:
                continue
        if last_entry:
            entries.append(last_entry)
        print(f" [SUMMARY] Успешно распарсено строк: {len(entries)}")
        return entries

    @staticmethod
    def group_by_normalized_message(entries: List[LogEntry]) -> Dict[str, List[LogEntry]]:
        grouped: Dict[str, List[LogEntry]] = defaultdict(list)
        for entry in entries:
            normalized = LogParser.normalize_message(entry.message)
            if normalized.lower() == "произошла ошибка":
                print(f"⚠️  [SKIPPED] Строка содержит обобщённое сообщение: {entry.message}")
                continue
            grouped[normalized].append(entry)
        return grouped

    @staticmethod
    def normalize_message(message: str) -> str:
        """
        Produce a normalised version of the log message to group similar errors.
        This implementation preserves the first Java package prefix (e.g.
        `org.postgresql.PSQLException`), replaces UUIDs and long hashes with
        placeholders and unifies idempotency-related transaction errors.
        """
        # Preserve the fully qualified class name if present at the start
        preserved = ""
        if match := re.match(r'^(org\.[\w\.]+):', message):
            preserved = match.group(1)

        # Replace UUIDs (36 characters with hyphens) with <UUID>
        message = re.sub(r'[a-fA-F0-9\-]{36}', '<UUID>', message)
        # Replace long numeric sequences (8+ digits) with <NUM>
        message = re.sub(r'\b\d{8,}\b', '<NUM>', message)
        # Replace long hex strings (32+ characters) with <HASH>
        message = re.sub(r'[a-fA-F0-9]{32,}', '<HASH>', message)
        # Replace patterns like userId=123 or transaction_id = abc with <ID>
        message = re.sub(r'([a-zA-Z0-9_-]*id[a-zA-Z0-9_-]*)\s*=\s*[a-zA-Z0-9_-]+', r'\1=<ID>', message, flags=re.IGNORECASE)

        # Unify English transaction errors related to idempotency
        # After IDs and hashes have been normalised, collapse specific
        # idempotent call messages into a single template. This helps group
        # multiple log entries referring to the same root cause.
        message = re.sub(
            r'An error occurred when calling original method for key\s*=?.*<HASH>.*?Transactions will be rolled back\.',
            'Idempotent call error (rolling back transaction)',
            message,
            flags=re.IGNORECASE,
        )
        message = re.sub(
            r'Rolling back transaction for key\s*<HASH>\.',
            'Idempotent call error (rolling back transaction)',
            message,
            flags=re.IGNORECASE,
        )

        # Generalise Russian messages like "Произошла ошибка: at <Class>.<Method>"
        # Extract the class and method to create a concise identifier. This
        # allows grouping errors by their origin within the codebase.
        match_pos = re.search(r'Произошла ошибка.*?at\s+([\w.$]+)\.([\w$]+)\(', message)
        if match_pos:
            cls = match_pos.group(1).split('.')[-1]
            method = match_pos.group(2)
            message = f'Ошибка в {cls}.{method}'

        result = f"{preserved}: {message}" if preserved else message
        return result.strip()import re
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
        last_entry: LogEntry | None = None
        lines = log_content.strip().splitlines()
        for line in lines:
            line = line.strip()
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
                    message=match.group("message").strip(),
                )
            elif last_entry and (line.startswith("at ") or line.startswith("Caused by") or line.startswith("org.")):
                # Append stacktrace lines to the previous entry
                last_entry.message += " " + line.strip()
            else:
                continue
        if last_entry:
            entries.append(last_entry)
        print(f" [SUMMARY] Успешно распарсено строк: {len(entries)}")
        return entries

    @staticmethod
    def group_by_normalized_message(entries: List[LogEntry]) -> Dict[str, List[LogEntry]]:
        grouped: Dict[str, List[LogEntry]] = defaultdict(list)
        for entry in entries:
            normalized = LogParser.normalize_message(entry.message)
            if normalized.lower() == "произошла ошибка":
                print(f"⚠️  [SKIPPED] Строка содержит обобщённое сообщение: {entry.message}")
                continue
            grouped[normalized].append(entry)
        return grouped

    @staticmethod
    def normalize_message(message: str) -> str:
        """
        Produce a normalised version of the log message to group similar errors.
        This implementation preserves the first Java package prefix (e.g.
        `org.postgresql.PSQLException`), replaces UUIDs and long hashes with
        placeholders and unifies idempotency-related transaction errors.
        """
        # Preserve the fully qualified class name if present at the start
        preserved = ""
        if match := re.match(r'^(org\.[\w\.]+):', message):
            preserved = match.group(1)

        # Replace UUIDs (36 characters with hyphens) with <UUID>
        message = re.sub(r'[a-fA-F0-9\-]{36}', '<UUID>', message)
        # Replace long numeric sequences (8+ digits) with <NUM>
        message = re.sub(r'\b\d{8,}\b', '<NUM>', message)
        # Replace long hex strings (32+ characters) with <HASH>
        message = re.sub(r'[a-fA-F0-9]{32,}', '<HASH>', message)
        # Replace patterns like userId=123 or transaction_id = abc with <ID>
        message = re.sub(r'([a-zA-Z0-9_-]*id[a-zA-Z0-9_-]*)\s*=\s*[a-zA-Z0-9_-]+', r'\1=<ID>', message, flags=re.IGNORECASE)

        # Unify English transaction errors related to idempotency
        # After IDs and hashes have been normalised, collapse specific
        # idempotent call messages into a single template. This helps group
        # multiple log entries referring to the same root cause.
        message = re.sub(
            r'An error occurred when calling original method for key\s*=?.*<HASH>.*?Transactions will be rolled back\.',
            'Idempotent call error (rolling back transaction)',
            message,
            flags=re.IGNORECASE,
        )
        message = re.sub(
            r'Rolling back transaction for key\s*<HASH>\.',
            'Idempotent call error (rolling back transaction)',
            message,
            flags=re.IGNORECASE,
        )

        # Generalise Russian messages like "Произошла ошибка: at <Class>.<Method>"
        # Extract the class and method to create a concise identifier. This
        # allows grouping errors by their origin within the codebase.
        match_pos = re.search(r'Произошла ошибка.*?at\s+([\w.$]+)\.([\w$]+)\(', message)
        if match_pos:
            cls = match_pos.group(1).split('.')[-1]
            method = match_pos.group(2)
            message = f'Ошибка в {cls}.{method}'

        result = f"{preserved}: {message}" if preserved else message
        return result.strip()