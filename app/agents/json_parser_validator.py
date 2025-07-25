import json
import re
from typing import List, Any

from pydantic import BaseModel, ValidationError


class ProblemReport(BaseModel):
    """
    Модель отчёта об одной проблеме, возвращаемого LLM.

    Помимо стандартных полей добавлены опциональные `root_cause` и
    `info_needed`, чтобы сохранять первопричину и список дополнительной
    информации, если модель сообщает, что данных недостаточно.
    """

    message: str
    original_message: str | None = None
    frequency: int
    criticality: str
    recommendation: str
    root_cause: str | None = None
    info_needed: str | None = None

    class Config:
        # Игнорировать лишние поля, если LLM вернёт что‑то ещё
        extra = "ignore"


class JSONParserValidator:
    @staticmethod
    def clean_json_response(response: str) -> str:
        """
        Очищает строку от управляющих символов, markdown‑обёрток и
        комментариев, затем пытается извлечь JSON‑массив.

        Комментарии (строки, начинающиеся с `//`) удаляются, поскольку
        стандарт JSON их не допускает.
        """
        print("----- СЫРОЙ ОТВЕТ ОТ GIGACHAT -----")
        print(response)
        print("-----------------------------------")

        # Remove control characters
        response = re.sub(r'[\x00-\x1F\x7F]+', '', response)
        # Remove code fences like ```json
        response = re.sub(r'```(?:json)?', '', response)
        # Remove inline comments starting with //
        response = re.sub(r'//.*?(?:\r?\n|$)', '', response)

        start_idx = response.find('[')
        end_idx = response.rfind(']')
        if 0 <= start_idx < end_idx:
            return response[start_idx:end_idx + 1]
        return ""

    @staticmethod
    def parse_and_validate(response: str) -> List[ProblemReport]:
        """
        Parses and validates the LLM response. Attempts to correct common
        formatting issues and aggregates list‑based frequency values. Falls back
        to markdown parsing if JSON cannot be recovered.
        """
        clean_response = JSONParserValidator.clean_json_response(response)
        if clean_response:
            try:
                # Decode JSON into Python objects
                data: List[Any] = json.loads(clean_response)
                normalized: List[dict[str, Any]] = []
                for raw_item in data:
                    # If the item is a list (e.g., returned by LLM as
                    # [msg, freq, crit, rec]) convert to dict
                    if not isinstance(raw_item, dict) and isinstance(raw_item, (list, tuple)):
                        # We expect at least 4 items: message, frequency,
                        # criticality, recommendation. Optional positions 4 and 5
                        # can contain root_cause and info_needed.
                        if len(raw_item) >= 4:
                            # Pre-fill dict
                            item = {
                                "message": raw_item[0],
                                "frequency": raw_item[1],
                                "criticality": raw_item[2],
                                "recommendation": raw_item[3],
                            }
                            if len(raw_item) > 4:
                                item["root_cause"] = raw_item[4]
                            if len(raw_item) > 5:
                                item["info_needed"] = raw_item[5]
                        else:
                            # Skip malformed items
                            continue
                    elif isinstance(raw_item, dict):
                        item = raw_item.copy()
                    else:
                        # Skip unknown structures
                        continue
                    # Flatten recommendation lists
                    rec = item.get("recommendation")
                    if isinstance(rec, list):
                        item["recommendation"] = "\n".join(str(r) for r in rec)
                    # Aggregate frequency lists
                    freq = item.get("frequency")
                    if isinstance(freq, list):
                        try:
                            numeric_values = [int(v) for v in freq if isinstance(v, (int, float, str))]
                            item["frequency"] = sum(numeric_values) if numeric_values else len(freq)
                        except Exception:
                            item["frequency"] = len(freq)
                    normalized.append(item)
                return [ProblemReport(**item) for item in normalized]
            except (json.JSONDecodeError, ValidationError) as e:
                print(f"❌ Ошибка парсинга JSON: {e}")
                fixed = clean_response.strip()
                fixed = re.sub(r',\s*\]$', ']', fixed)
                fixed = re.sub(r',\s*\}$', '}', fixed)
                if fixed and not fixed.endswith(']'):
                    fixed = fixed + ']'
                try:
                    data = json.loads(fixed)
                    for item in data:
                        rec = item.get("recommendation")
                        if isinstance(rec, list):
                            item["recommendation"] = "\n".join(str(r) for r in rec)
                        freq = item.get("frequency")
                        if isinstance(freq, list):
                            try:
                                numeric_values = [int(v) for v in freq if isinstance(v, (int, float, str))]
                                item["frequency"] = sum(numeric_values) if numeric_values else len(freq)
                            except Exception:
                                item["frequency"] = len(freq)
                    return [ProblemReport(**item) for item in data]
                except Exception as e2:
                    print(f"⚠️ Не удалось корректировать JSON: {e2}")
                    reports: List[ProblemReport] = []
                    for obj_str in re.findall(r'\{[^\{\}]*\}', clean_response):
                        try:
                            obj_data = json.loads(obj_str)
                            rec = obj_data.get("recommendation")
                            if isinstance(rec, list):
                                obj_data["recommendation"] = "\n".join(str(r) for r in rec)
                            freq = obj_data.get("frequency")
                            if isinstance(freq, list):
                                try:
                                    numeric_values = [int(v) for v in freq if isinstance(v, (int, float, str))]
                                    obj_data["frequency"] = sum(numeric_values) if numeric_values else len(freq)
                                except Exception:
                                    obj_data["frequency"] = len(freq)
                            reports.append(ProblemReport(**obj_data))
                        except Exception:
                            continue
                    if reports:
                        return reports
                    print("⚠️ Переходим к парсингу markdown-формата")
                    return JSONParserValidator.parse_markdown(response)

        print("⚠️ JSON не найден — пробуем распарсить markdown-формат")
        return JSONParserValidator.parse_markdown(response)

    @staticmethod
    def parse_markdown(response: str) -> List[ProblemReport]:
        """
        Parses markdown‑formatted responses when JSON cannot be extracted.
        """
        errors: List[ProblemReport] = []
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
                    recommendation=rec_match.group(1).strip() if rec_match else "—",
                ))
            except Exception:
                continue
        return errors