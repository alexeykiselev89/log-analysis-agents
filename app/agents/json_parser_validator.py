import json
import re
from typing import List, Any
from pydantic import BaseModel, ValidationError


class ProblemReport(BaseModel):
    """Модель отчёта об одной проблеме, возвращаемого LLM."""
    message: str
    original_message: str | None = None
    frequency: int
    criticality: str
    recommendation: str


class JSONParserValidator:
    @staticmethod
    def clean_json_response(response: str) -> str:
        """
        Очищает строку от управляющих символов, markdown-обёрток и
        комментариев, затем пытается извлечь JSON-массив.

        Комментарии в ответе (строки, начинающиеся с `//`) удаляются,
        поскольку они являются недопустимыми в стандарте JSON и мешают
        десериализации.
        """
        print("----- СЫРОЙ ОТВЕТ ОТ GIGACHAT -----")
        print(response)
        print("-----------------------------------")

        # Удаляем управляющие символы
        response = re.sub(r'[\x00-\x1F\x7F]+', '', response)
        # Удаляем Markdown‑обёртки (```json ... ```)
        response = re.sub(r'```(?:json)?', '', response)
        # Удаляем комментарии (// ... до конца строки)
        response = re.sub(r'//.*?(?:\r?\n|$)', '', response)

        # Ищем первую '[' и последнюю ']'
        start_idx = response.find('[')
        end_idx = response.rfind(']')
        if 0 <= start_idx < end_idx:
            return response[start_idx:end_idx + 1]
        return ""

    @staticmethod
    def parse_and_validate(response: str) -> List[ProblemReport]:
        """
        Пытается распарсить и валидировать ответ LLM. В случае ошибок
        предпринимает попытки исправить общие проблемы, например
        удаляет хвостовые запятые и корректирует структуры. Если JSON
        восстановить не удаётся, переходит к markdown‑парсеру.
        """
        clean_response = JSONParserValidator.clean_json_response(response)
        if clean_response:
            try:
                data: List[dict[str, Any]] = json.loads(clean_response)
                for item in data:
                    # Если рекомендация возвращена в виде списка строк — объединяем
                    rec = item.get("recommendation")
                    if isinstance(rec, list):
                        item["recommendation"] = "\n".join(str(r) for r in rec)
                    # Если частота возвращена списком — агрегируем значения (сумма)
                    freq = item.get("frequency")
                    if isinstance(freq, list):
                        try:
                            # Суммируем только числовые элементы
                            numeric_values = [int(v) for v in freq if isinstance(v, (int, float, str))]
                            if numeric_values:
                                item["frequency"] = sum(numeric_values)
                            else:
                                item["frequency"] = len(freq)
                        except Exception:
                            item["frequency"] = len(freq)
                return [ProblemReport(**item) for item in data]
            except (json.JSONDecodeError, ValidationError) as e:
                # Попытка скорректировать хвостовые запятые и т.п.
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
                                if numeric_values:
                                    item["frequency"] = sum(numeric_values)
                                else:
                                    item["frequency"] = len(freq)
                            except Exception:
                                item["frequency"] = len(freq)
                    return [ProblemReport(**item) for item in data]
                except Exception as e2:
                    # Если корректировка не помогла — пробуем извлечь отдельные объекты
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
                                    if numeric_values:
                                        obj_data["frequency"] = sum(numeric_values)
                                    else:
                                        obj_data["frequency"] = len(freq)
                                except Exception:
                                    obj_data["frequency"] = len(freq)
                            reports.append(ProblemReport(**obj_data))
                        except Exception:
                            continue
                    if reports:
                        return reports
                    print("⚠️ Переходим к парсингу markdown-формата")
                    return JSONParserValidator.parse_markdown(response)

        # JSON не найден — пробуем распарсить markdown
        print("⚠️ JSON не найден — пробуем распарсить markdown-формат")
        return JSONParserValidator.parse_markdown(response)

    @staticmethod
    def parse_markdown(response: str) -> List[ProblemReport]:
        """
        Парсит markdown-ответ, если LLM по какой‑то причине не вернул JSON.
        Сохраняет основную информацию, даже если формат не соответствует
        ожиданиям.
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
                    recommendation=rec_match.group(1).strip() if rec_match else "—"
                ))
            except Exception:
                continue
        return errors