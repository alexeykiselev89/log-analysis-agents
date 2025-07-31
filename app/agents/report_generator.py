"""
Генератор отчётов для результатов анализа логов.

Этот модуль содержит класс `ReportGenerator`, предоставляющий методы для
создания отчётов в форматах JSON и CSV на основе списка объектов
`ProblemReport`. JSON‑отчёт может быть возвращён напрямую через API,
а CSV‑файл сохраняется на диск для последующей загрузки.
"""

import pandas as pd
from typing import List
from app.agents.json_parser_validator import ProblemReport
import json
from datetime import datetime
import os

class ReportGenerator:
    """
    Служебный класс для генерации отчётов о найденных проблемах.

    Методы этого класса не требуют создания экземпляра: они принимают
    список объектов `ProblemReport` и формируют отчёт в одном из двух
    форматов. JSON‑отчёт возвращается в виде строки, а CSV‑отчёт
    сохраняется по указанному пути и возвращает путь к файлу.
    """

    @staticmethod
    def generate_json_report(problems: List[ProblemReport]) -> str:
        """
        Формирует JSON‑отчёт по списку обнаруженных проблем.

        :param problems: список объектов `ProblemReport`.
        :return: строка JSON с полями `summary`, `total_problems` и
            `problems`. Поле `problems` содержит сериализованные
            представления проблем.
        """
        report = {
            # Заголовок отчёта с текущей датой и временем
            "summary": f"Анализ логов от {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            # Общее количество проблем
            "total_problems": len(problems),
            # Конвертируем каждый Pydantic‑объект в словарь
            "problems": [problem.dict() for problem in problems],
        }
        # Сериализуем словарь в строку JSON, сохраняя кириллицу
        return json.dumps(report, ensure_ascii=False, indent=4)

    @staticmethod
    def generate_csv_report(problems: List[ProblemReport], filepath: str) -> str:
        """
        Сохраняет отчёт в формате CSV по указанному пути.

        :param problems: список объектов `ProblemReport`.
        :param filepath: полный путь к CSV‑файлу, который будет создан.
        :return: путь к созданному CSV‑файлу.
        """
        # Преобразуем список проблем в DataFrame для удобной записи в CSV
        df = pd.DataFrame([problem.dict() for problem in problems])
        # Создаём директорию для файла, если её ещё нет
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        # Записываем CSV без индексов и с BOM‑меткой для корректного
        # отображения русских символов в Excel
        df.to_csv(filepath, index=False, encoding='utf-8-sig')
        return filepath

