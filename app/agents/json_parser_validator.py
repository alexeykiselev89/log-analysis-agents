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
    """
    Улучшенный парсер и валидатор JSON‑ответа от LLM.

    Этот класс пытается извлечь массив объектов из сырой строки,
    очищает от markdown‑обёрток и управляющих символов, удаляет
    комментарии и лишние запятые, а затем валидирует полученные
    элементы. Если разобрать JSON не удаётся, он пробует извлечь
    отдельные объекты и валидирует их по одному.
    """

    @staticmethod
    def clean_json_response(response: str) -> str:
        """
        Очищает строку от управляющих символов, markdown‑обёрток и
        комментариев, затем пытается извлечь JSON‑массив.

        Комментарии (строки, начинающиеся с `//`) удаляются, поскольку
        стандарт JSON их не допускает.
        """
        # Удаляем управляющие символы, которые могут мешать парсингу
        response = re.sub(r'[\x00-\x1F\x7F]+', '', response)
        # Убираем markdown‑обрамление вида ``` и ```json
        response = re.sub(r'```(?:json)?', '', response)
        # Удаляем однострочные комментарии, начинающиеся с //
        response = re.sub(r'//.*?(?:\r?\n|$)', '', response)

        start_idx = response.find('[')
        end_idx = response.rfind(']')
        if 0 <= start_idx < end_idx:
            return response[start_idx:end_idx + 1]
        return ""

    @staticmethod
    def parse_and_validate(response: str) -> List[ProblemReport]:
        """
        Разбирает и валидирует JSON‑ответ, возвращённый LLM.

        Метод пытается восстановить корректный JSON: преобразует элементы,
        представленные списками, в словари, объединяет списковые значения
        частоты в одно число, а рекомендации в виде списка — в строку
        (разделяя элементы переводом строки). Если парсинг JSON не
        удаётся, извлекает отдельные объекты из строки и валидирует их
        по одному.
        """
        clean_response = JSONParserValidator.clean_json_response(response)
        if clean_response:
            # Первой попытка: загрузить как список целиком
            try:
                data: List[Any] = json.loads(clean_response)
                normalized: List[dict[str, Any]] = []
                for raw_item in data:
                    if not isinstance(raw_item, dict) and isinstance(raw_item, (list, tuple)):
                        # Конвертируем списковый элемент в словарь
                        if len(raw_item) >= 4:
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
                            continue
                    elif isinstance(raw_item, dict):
                        item = raw_item.copy()
                    else:
                        continue
                    # Объединяем список рекомендаций в строку
                    rec = item.get("recommendation")
                    if isinstance(rec, list):
                        item["recommendation"] = "\n".join(str(r) for r in rec)
                    # Агрегируем список частоты
                    freq = item.get("frequency")
                    if isinstance(freq, list):
                        try:
                            numeric_values = [int(v) for v in freq if isinstance(v, (int, float, str))]
                            item["frequency"] = sum(numeric_values) if numeric_values else len(freq)
                        except Exception:
                            item["frequency"] = len(freq)
                    normalized.append(item)
                return [ProblemReport(**item) for item in normalized]
            except (json.JSONDecodeError, ValidationError):
                pass

            # Вторая попытка: удаляем запятые перед закрывающими скобками
            fixed = clean_response.strip()
            fixed = re.sub(r',\s*\]', ']', fixed)
            fixed = re.sub(r',\s*\}', '}', fixed)
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
            except Exception:
                pass

            # Третья попытка: парсим отдельно каждую JSON‑структуру
            reports: List[ProblemReport] = []
            for obj_str in re.findall(r'\{[^\{\}]*\}', clean_response):
                try:
                    # Удаляем запятые перед закрывающими скобками и скобками
                    obj_clean = re.sub(r',\s*([}\]])', r'\1', obj_str)
                    obj_data = json.loads(obj_clean)
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

        # Если ничего не удалось распарсить, возвращаем пустой список
        return []