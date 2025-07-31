from pydantic import BaseModel
from datetime import datetime

class LogEntry(BaseModel):
    """
    Представляет одну запись лога, распознанную парсером.

    Поля:
        timestamp: `datetime` объекта времени, когда была создана запись;
        level: строка с уровнем логирования (например, ``ERROR``, ``WARN``);
        thread: имя потока, откуда было записано сообщение;
        class_name: имя класса или компонента, который сгенерировал сообщение;
        message: текст сообщения, включая описание ошибки и, возможно, stacktrace.
    """

    timestamp: datetime
    level: str
    thread: str
    class_name: str
    message: str
