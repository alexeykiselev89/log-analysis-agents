import json
import re
from typing import List
from pydantic import BaseModel, ValidationError

class ProblemReport(BaseModel):
    """
    Модель отчёта об одной проблеме, возвращаемого LLM.

    Поле ``original_message`` заполняется после парсинга в эндпоинте ``analyze_log``
    исходным текстом ошибки, чтобы его можно было отобразить в отчёте. LLM это
    поле не возвращает, поэтому оно опционально.
    """
    message: str
    original_message: str | None = None
    frequency: int
    criticality: str
    recommendation: str

class JSONParserValidator:
    @staticmethod
    def clean_json_response(response: str) -> str:
        """
        Очищает строку от управляющих символов и markdown-обёрток,
        затем пытается извлечь JSON-массив.
        """
        print("----- СЫРОЙ ОТВЕТ ОТ GIGACHAT -----")
        print(response)
        print("-----------------------------------")

        # Удаляем управляющие символы и markdown-код
        response = re.sub(r'[\x00-\x1F\x7F]+', '', response)
        response = re.sub(r'```(?:json)?', '', response)

        # Находим первую и последнюю квадратные скобки
        start_idx = response.find('[')
        end_idx = response.rfind(']')
        if 0 <= start_idx < end_idx:
            return response[start_idx:end_idx + 1]
        return ""

    @staticmethod
    def parse_and_validate(response: str) -> List[ProblemReport]:
        clean_response = JSONParserValidator.clean_json_response(response)
        if clean_response:
            try:
                data = json.loads(clean_response)
                return [ProblemReport(**item) for item in data]
            except (json.JSONDecodeError, ValidationError) as e:
                print(f"❌ Ошибка парсинга JSON: {e}")
                # Продолжим попытки — возможно, формат markdown
        # Если JSON не найден или возникла ошибка, пробуем распарсить markdown
        print("⚠️ JSON не найден — пробуем распарсить markdown-формат")
        return JSONParserValidator.parse_markdown(response)

    @staticmethod
    def parse_markdown(response: str) -> List[ProblemReport]:
        """
        Парсит markdown-ответ, если LLM по какой‑то причине не вернул валидный JSON.
        """
        errors = []
        blocks = re.split(r'#### Ошибка №\d+:', response)
        for block in blocks[1:]:
            try:
                msg_match = re.search(r'`([^`]+)`', block)
                freq_match = re.search(r'Частота:\s*(\d+)', block)
                crit_match = re.search(r'Критичность:\s*(\w+)', block, re.IGNORECASE)
                rec_match = re.search(r'Рекомендации:\s*[-•]?\s*(.*?)\n\n', block, re.DOTALL)

                errors.append(ProblemReport(
                    message=msg_match.group(1) if msg_match else "Неизвестно",
                    frequency=int(freq_match.group(1)) if freq_match else 1,
                    criticality=crit_match.group(1).lower() if crit_match else "низкая",
                    recommendation=rec_match.group(1).strip() if rec_match else "—"
                ))
            except Exception as e:
                print(f"⚠️ Ошибка разбора блока: {e}")
                continue

        return errors
