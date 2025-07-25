import re
from typing import List, Dict
from collections import defaultdict
from datetime import datetime
from app.models.log_entry import LogEntry


# Pattern to parse log entries (timestamp, level, thread, class and message)
LOG_PATTERN = re.compile(
    r'^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) '
    r'\[(?P<level>[A-Z]+)\] '
    r'\[(?P<thread>[^\]]+)\] '
    r'(?P<class>[^\:]+): (?P<message>.+)$'
)

# Levels considered as problems
ERROR_LEVELS = {"ERROR", "WARN", "EXCEPTION"}


class LogParser:
    @staticmethod
    def parse_log(log_content: str) -> List[LogEntry]:
        """
        Parse raw log content into a list of LogEntry objects. Only lines with
        levels from ERROR_LEVELS are kept, and stacktrace lines prefixed by
        "at ", "Caused by" or "org." are concatenated to the previous
        entry's message.
        """
        entries: List[LogEntry] = []
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
            elif last_entry and (
                line.startswith("at ")
                or line.startswith("Caused by")
                or line.startswith("org.")
            ):
                last_entry.message += " " + line.strip()
            else:
                continue
        if last_entry:
            entries.append(last_entry)
        print(f" [SUMMARY] Успешно распарсено строк: {len(entries)}")
        return entries

    @staticmethod
    def group_by_normalized_message(entries: List[LogEntry]) -> Dict[str, List[LogEntry]]:
        """
        Group log entries by their normalised message. Entries whose normalised
        message equals "произошла ошибка" (generic message) are skipped.
        """
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
        - Preserves the first Java package prefix (e.g. org.postgresql.PSQLException).
        - Replaces UUIDs, long numeric sequences and long hashes with placeholders.
        - Replaces patterns like userId=123 or transaction_id = abc with <ID>.
        - Unifies idempotent transaction errors into a single template.
        - Generalises messages like "Произошла ошибка ... at <Class>.<Method>" by
          extracting the class and method name.
        """
        # Preserve the fully qualified class name if present at the start
        preserved = ""
        if match := re.match(r'^(org\.[\w\.]+):', message):
            preserved = match.group(1)

        # Mask UUIDs (36 chars with hyphens)
        message = re.sub(r'[a-fA-F0-9\-]{36}', '<UUID>', message)
        # Mask long numeric sequences (8+ digits)
        message = re.sub(r'\b\d{8,}\b', '<NUM>', message)
        # Mask long hex strings (32+ characters)
        message = re.sub(r'[a-fA-F0-9]{32,}', '<HASH>', message)
        # Mask key=value pairs containing "id" in the key name
        message = re.sub(
            r'([a-zA-Z0-9_-]*id[a-zA-Z0-9_-]*)\s*=\s*[a-zA-Z0-9_-]+',
            r'\1=<ID>',
            message,
            flags=re.IGNORECASE,
        )

        # Unify English transaction errors related to idempotency
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
        match_pos = re.search(r'Произошла ошибка.*?at\s+([\w.$]+)\.([\w$]+)\(', message)
        if match_pos:
            cls = match_pos.group(1).split('.')[-1]
            method = match_pos.group(2)
            message = f'Ошибка в {cls}.{method}'

        result = f"{preserved}: {message}" if preserved else message
        return result.strip()
