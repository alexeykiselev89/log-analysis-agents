
"""
Парсер логов: извлекает важные записи из текстовых логов приложений и
группирует их по нормализованным сообщениям.

В этом модуле определяется класс `LogParser`, который содержит методы
для разбора сырых строк логов в объекты `LogEntry`, группировки
сообщений по нормализованному тексту и нормализации сообщений для
объединения похожих ошибок.
"""

import re
from typing import List, Dict
from collections import defaultdict
from datetime import datetime
from app.models.log_entry import LogEntry


# Шаблон для разбора строк лога (временная метка, уровень, поток, класс и сообщение)
LOG_PATTERN = re.compile(
    r'^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) '
    r'\[(?P<level>[A-Z]+)\] '
    r'\[(?P<thread>[^\]]+)\] '
    r'(?P<class>[^\:]+): (?P<message>.+)$'
)

# Множество уровней логирования, которые считаются ошибками
ERROR_LEVELS = {"ERROR", "WARN", "EXCEPTION"}


class LogParser:
    @staticmethod
    def parse_log(log_content: str) -> List[LogEntry]:
        """
        Разбирает текст логов и возвращает список объектов `LogEntry`.

        Сохраняются только строки, уровни которых входят в `ERROR_LEVELS`.
        Строки стектрейса, начинающиеся с ``"at "``, ``"Caused by"`` или ``"org."``,
        присоединяются к сообщению предыдущей записи. Это позволяет
        объединить сообщение об ошибке с его стеком вызовов.
        """
        # Список, в который будем добавлять распарсенные записи
        entries: List[LogEntry] = []
        # Храним последнюю найденную запись, чтобы можно было дополнять её сообщением стектрейса
        last_entry: LogEntry | None = None
        # Разбиваем содержимое лога на отдельные строки
        lines = log_content.strip().splitlines()
        for line in lines:
            # Удаляем пробелы в начале и в конце строки
            line = line.strip()
            # Пытаемся сопоставить строку с шаблоном записи
            match = LOG_PATTERN.match(line)
            if match:
                # Строка соответствует шаблону: извлекаем уровень, поток, класс и сообщение
                level = match.group("level").upper()
                # Пропускаем уровни, которые не считаются ошибками
                if level not in ERROR_LEVELS:
                    continue
                # Перед началом новой записи сохраняем предыдущую
                if last_entry:
                    entries.append(last_entry)
                # Создаём новую запись LogEntry
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
                # Строка относится к стеку вызовов — дополняем сообщение предыдущей записи
                last_entry.message += " " + line.strip()
            else:
                # Остальные строки пропускаем
                continue
        # Добавляем последнюю запись, если она существует
        if last_entry:
            entries.append(last_entry)
        print(f" [SUMMARY] Успешно распарсено строк: {len(entries)}")
        return entries

    @staticmethod
    def group_by_normalized_message(entries: List[LogEntry]) -> Dict[str, List[LogEntry]]:
        """
        Группирует записи лога по их нормализованному сообщению.

        Если нормализованное сообщение равно ``"произошла ошибка"`` (общая
        формулировка без конкретики), такая запись пропускается, чтобы
        не засорять отчёт.
        """
        # Словарь для группировки: ключ — нормализованное сообщение
        grouped: Dict[str, List[LogEntry]] = defaultdict(list)
        for entry in entries:
            # Получаем нормализованное сообщение
            normalized = LogParser.normalize_message(entry.message)
            # Пропускаем обобщённые сообщения без конкретики
            if normalized.lower() == "произошла ошибка":
                print(f"⚠️  [SKIPPED] Строка содержит обобщённое сообщение: {entry.message}")
                continue
            grouped[normalized].append(entry)
        return grouped

    @staticmethod
    def normalize_message(message: str) -> str:
        """
        Создаёт нормализованную версию сообщения об ошибке для группировки
        похожих ошибок.

        - Сохраняет префикс Java‑пакета (например, ``org.postgresql.PSQLException``), если
          он присутствует в начале.
        - Заменяет UUID, длинные числовые последовательности и хеши на
          плейсхолдеры ``<UUID>``, ``<NUM>``, ``<HASH>``.
        - Заменяет пары вида ``ключ=значение`` с ключами, содержащими
          ``id``, на ``<ID>``.
        - Унифицирует сообщения об ошибках идемпотентных транзакций.
        - Обобщает русские сообщения вида ``"Произошла ошибка ... at <Класс>.<Метод>"``
          до шаблона ``"Ошибка в <Класс>.<Метод>"``.
        """
        # Сюда сохраним имя класса/пакета, если оно присутствует в начале сообщения
        preserved = ""
        if match := re.match(r'^(org\.[\w\.]+):', message):
            preserved = match.group(1)

        # Маскируем UUID (36 символов с дефисами)
        message = re.sub(r'[a-fA-F0-9\-]{36}', '<UUID>', message)
        # Маскируем длинные числовые последовательности (8 и более цифр)
        message = re.sub(r'\b\d{8,}\b', '<NUM>', message)
        # Маскируем длинные шестнадцатеричные строки (32 и более символов)
        message = re.sub(r'[a-fA-F0-9]{32,}', '<HASH>', message)
        # Маскируем пары ключ=значение, где ключ содержит "id"
        message = re.sub(
            r'([a-zA-Z0-9_-]*id[a-zA-Z0-9_-]*)\s*=\s*[a-zA-Z0-9_-]+',
            r'\1=<ID>',
            message,
            flags=re.IGNORECASE,
        )

        # Унифицируем англоязычные сообщения об ошибке идемпотентных вызовов
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

        # Обобщаем русские сообщения вида "Произошла ошибка ... at <Class>.<Method>"
        match_pos = re.search(r'Произошла ошибка.*?at\s+([\w.$]+)\.([\w$]+)\(', message)
        if match_pos:
            cls = match_pos.group(1).split('.')[-1]
            method = match_pos.group(2)
            message = f'Ошибка в {cls}.{method}'

        # Возвращаем результат: добавляем сохранённый префикс, если он был
        result = f"{preserved}: {message}" if preserved else message
        return result.strip()
