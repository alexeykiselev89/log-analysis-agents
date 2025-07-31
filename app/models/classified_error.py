from pydantic import BaseModel

class ClassifiedError(BaseModel):
    """
    Результат классификации одной ошибки, используемый для дальнейшего анализа.

    Поля:
        original_message: исходное сообщение (или объединённые примеры), предоставляющее контекст;
        normalized_message: нормализованный вариант сообщения для группировки сходных ошибок;
        frequency: сколько раз такая ошибка встретилась в логе;
        level: уровень логирования ошибки (``ERROR``, ``WARN``, ``INFO``, ``TRACE``);
        criticality: строка, отражающая оценку критичности (по умолчанию "низкая").
    """

    original_message: str
    normalized_message: str
    frequency: int
    level: str
    criticality: str = "низкая"
