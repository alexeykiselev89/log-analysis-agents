import json
import re
from typing import List
from pydantic import BaseModel, ValidationError

class ProblemReport(BaseModel):
    """
    Модель отчёта об одной проблеме, возвращаемого LLM.
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
        Очищает ответ LLM от управляющих символов и markdown,
        возвращает содержимое от первой '[' до последней ']'.
        """
        print("----- СЫРОЙ ОТВЕТ ОТ GIGACHAT -----")
        print(response)
        print("-----------------------------------")

        # убираем управляющие символы и markdown
        response = re.sub(r'[\x00-\x1F\x7F]+', '', response)
        response = re.sub(r'```(?:json)?', '', response)

        start_idx = response.find('[')
        end_idx = response.rfind(']')
        if 0 <= start_idx < end_idx:
            return response[start_idx:end_idx + 1]
        return ""

    @staticmethod
    def parse_and_validate(response: str) -> List[ProblemReport]:
        """
        Валидирует ответ LLM. Пытается распарсить JSON,
        при ошибке корректирует хвостовые запятые и извлекает объекты по отдельности.
        Если всё равно не удаётся — парсит markdown.
        """
        clean_response = JSONParserValidator.clean_json_response(response)
        if clean_response:
            try:
                data = json.loads(clean_response)
                return [ProblemReport(**item) for item in data]
            except (json.JSONDecodeError, ValidationError) as e:
                # пытаемся исправить хвостовые запятые
                print(f"❌ Ошибка парсинга JSON: {e}")
                fixed = clean_response.strip()
                fixed = re.sub(r',\\s*\\]$', ']', fixed)
                fixed = re.sub(r',\\s*\\}$', '}', fixed)
                if fixed and not fixed.endswith(']'):
                    fixed = fixed + ']'
                try:
                    data = json.loads(fixed)
                    return [ProblemReport(**item) for item in data]
                except Exception as e2:
                    # пытаемся извлечь отдельные объекты
                    print(f"⚠️ Не удалось корректировать JSON: {e2}")
                    reports: List[ProblemReport] = []
                    for obj_str in re.findall(r'\\{[^\\{\\}]*\\}', clean_response):
                        try:
                            obj_data = json.loads(obj_str)
                            reports.append(ProblemReport(**obj_data))
                        except Exception:
                            continue
                    if reports:
                        return reports
                    # окончательно fallback на markdown
                    print("⚠️ Переходим к парсингу markdown-формата")
                    return JSONParserValidator.parse_markdown(response)

        # JSON не найден — парсим markdown
        print("⚠️ JSON не найден — пробуем распарсить markdown-формат")
        return JSONParserValidator.parse_markdown(response)

    @staticmethod
    def parse_markdown(response: str) -> List[ProblemReport]:
        """
        Парсит markdown-ответ, если LLM по какой‑то причине не вернул JSON.
        """
        errors = []
        blocks = re.split(r'#### Ошибка №\\d+:', response)
        for block in blocks[1:]:
            try:
                msg_match = re.search(r'`([^`]+)`', block)
                freq_match = re.search(r'Частота:\\s*(\\d+)', block)
                crit_match = re.search(r'Критичность:\\s*(\\w+)', block, re.IGNORECASE)
                rec_match = re.search(r'Рекомендации:\\s*[-•]?\\s*(.*?)\\n\\n', block, re.DOTALL)

                errors.append(ProblemReport(
                    message=msg_match.group(1) if msg_match else "Неизвестно",
                    frequency=int(freq_match.group(1)) if freq_match else 1,
                    criticality=crit_match.group(1).lower() if crit_match else "низкая",
                    recommendation=rec_match.group(1).strip() if rec_match else "—"
                ))
            except Exception:
                continue

        return errors