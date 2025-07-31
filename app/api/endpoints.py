"""
HTTP‑эндпоинты для анализа лог‑файлов и формирования отчётов.

Этот модуль содержит два HTTP‑эндпоинта для FastAPI:

* `/analyze-log` — принимает лог‑файл, разбирает его, классифицирует уникальные
  ошибки, отправляет краткую сводку в LLM и возвращает JSON‑отчёт вместе с
  ссылкой на скачивание CSV‑файла.
* `/download-report` — отдаёт CSV‑файл по его имени.

Функция `group_problems_by_frequency` агрегирует отчёты из LLM: объединяет
объекты `ProblemReport` с одинаковым нормализованным сообщением, суммирует
частоты, объединяет исходные сообщения без дубликатов, выбирает максимальную
критичность, сливает рекомендации и первопричины и обрезает длинные строки.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
from collections import defaultdict
from typing import List

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse

from app.agents.log_parser import LogParser
from app.agents.error_classifier import ErrorClassifier, ClassifiedError
from app.agents.prompt_builder import PromptBuilder
from app.agents.gigachat_client import GigaChatClient
from app.agents.json_parser_validator import JSONParserValidator, ProblemReport
from app.agents.report_generator import ReportGenerator

# Настраиваем базовый логгер для всего приложения
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Создаём роутер, который затем подключается в app.main
router = APIRouter()


def group_problems_by_frequency(problems: List[ProblemReport]) -> List[ProblemReport]:
    """
    Группирует объекты `ProblemReport` по их нормализованному сообщению.

    Первичная агрегация от LLM может содержать несколько записей для одного и
    того же сообщения (например, если частота или критичность были слегка
    различны). Эта функция объединяет такие записи, суммируя частоты и
    объединяя другие поля.

    Для каждой группы:

    * Частоты (`frequency`) суммируются.
    * Поле `original_message` собирается из уникальных исходных примеров,
      разделённых символами `|`, переводами строк или разделителем `\n---\n`. После
      объединения строка обрезается до 200 символов.
    * Критичность выбирается по максимальному значению: «высокая» > «средняя» > «низкая».
    * Поле `recommendation` объединяется в единый нумерованный список шагов:
      исходные рекомендации разбиваются по точкам с запятой и переводам строк,
      номера удаляются, дубликаты фильтруются по леммам слов, затем шаги
      перенумеровываются.
    * Поля `root_cause` и `info_needed` собираются, строки разбиваются по
      точкам с запятой и переводам строк; дубликаты удаляются.

    Возвращается список агрегированных `ProblemReport`, один для каждого
    уникального сообщения.
    """
    grouped: dict[str, List[ProblemReport]] = defaultdict(list)
    for pr in problems:
        key = (pr.message or "").strip()
        grouped[key].append(pr)

    result: List[ProblemReport] = []
    for msg, items in grouped.items():
        if len(items) == 1:
            # Ничего объединять не нужно
            result.append(items[0])
            continue

        # Суммируем частоту
        freq_sum = sum(it.frequency for it in items if it.frequency)

        # Объединяем исходные сообщения, разбивая по различным разделителям
        origs: List[str] = []
        for it in items:
            if it.original_message:
                parts = re.split(r'\n---\n|\n|\|', it.original_message)
                for part in parts:
                    part = part.strip()
                    if part and part not in origs:
                        origs.append(part)
        combined_orig = " | ".join(origs) if origs else None
        if combined_orig and len(combined_orig) > 200:
            combined_orig = combined_orig[:200] + "…"

        # Определяем максимальную критичность
        crits = [it.criticality for it in items if it.criticality]
        final_crit = 'низкая'
        if 'высокая' in crits:
            final_crit = 'высокая'
        elif 'средняя' in crits:
            final_crit = 'средняя'

        # Объединяем рекомендации: разбиваем на шаги, удаляем номера, фильтруем дубликаты
        all_steps: List[str] = []
        seen_keys: set[str] = set()
        for it in items:
            rec = it.recommendation or ''
            parts = re.split(r'[;\n]+', rec)
            for part in parts:
                step = part.strip()
                if not step:
                    continue
                # Удаляем ведущие порядковые номера (1., 2., …)
                step = re.sub(r'^\d+\.\s*', '', step)
                if not step:
                    continue
                # Нормализуем слова для сравнения (удаляем окончания, букву ё и мягкий знак)
                lower = step.lower().rstrip('.').rstrip(',')
                words = lower.split()
                norm_words: List[str] = []
                for w in words:
                    base = w
                    for suf in ('тесь', 'тесь', 'йтесь', 'итесь', 'итесь', 'йте', 'ите', 'ете', 'те', 'ть'):
                        if base.endswith(suf) and len(base) > len(suf):
                            base = base[:-len(suf)]
                            break
                    base = base.replace('ё', 'е').rstrip('ь')
                    norm_words.append(base)
                key = ''.join(norm_words)[:25]
                if key not in seen_keys:
                    seen_keys.add(key)
                    all_steps.append(step)
        if all_steps:
            combined_rec = "\n".join(f"{idx + 1}. {text}" for idx, text in enumerate(all_steps))
        else:
            combined_rec = '—'

        # Объединяем первопричины
        root_causes: List[str] = []
        for it in items:
            if it.root_cause:
                for rc in re.split(r'[;\n]+', it.root_cause):
                    rc = rc.strip()
                    if rc and rc not in root_causes:
                        root_causes.append(rc)
        combined_root = '; '.join(root_causes) if root_causes else None

        # Объединяем дополнительную информацию
        info_needed_list: List[str] = []
        for it in items:
            if it.info_needed:
                for info in re.split(r'[;\n]+', it.info_needed):
                    info = info.strip()
                    if info and info not in info_needed_list:
                        info_needed_list.append(info)
        combined_info = '; '.join(info_needed_list) if info_needed_list else None

        result.append(ProblemReport(
            message=msg,
            frequency=freq_sum,
            original_message=combined_orig,
            criticality=final_crit,
            recommendation=combined_rec,
            root_cause=combined_root,
            info_needed=combined_info,
        ))

    return result


@router.post("/analyze-log")
async def analyze_log(file: UploadFile = File(...)):
    """
    Обрабатывает загруженный лог‑файл: парсит записи, группирует и классифицирует
    ошибки, запрашивает рекомендации у LLM и формирует отчёт.

    :param file: загруженный пользователем лог‑файл (UploadFile).
    :return: словарь с полями ``report`` (JSON‑строка с отчётом) и ``csv_url``
             (URL для скачивания CSV‑отчёта).
    """
    logger.info("Начат анализ загруженного лог‑файла")
    try:
        content = await file.read()
        log_content = content.decode("utf-8", errors="replace")
        logger.info("Получено %d байт логов", len(content))
    except Exception as ex:
        logger.exception("Ошибка при чтении файла: %s", ex)
        raise HTTPException(status_code=400, detail="Ошибка при чтении файла")

    # Парсим лог и группируем по нормализованному сообщению
    entries = LogParser.parse_log(log_content)
    logger.info("Распарсено %d записей с интересующими уровнями", len(entries))
    grouped_entries = LogParser.group_by_normalized_message(entries)
    logger.info("Сгруппировано %d уникальных ошибок", len(grouped_entries))

    # Классифицируем ошибки по уровню и частоте
    classified: List[ClassifiedError] = ErrorClassifier.classify_errors(grouped_entries)
    logger.info("После классификации получено %d ошибок", len(classified))

    # Строим промт для LLM и вызываем модель
    prompt = PromptBuilder.build_prompt(classified)
    logger.info("Промт для LLM:\n%s", prompt)

    gigachat = GigaChatClient()
    try:
        response = await gigachat.get_completion(prompt)
    except Exception as e:
        logger.exception("Ошибка при вызове GigaChat: %s", e)
        raise HTTPException(status_code=502, detail=f"Ошибка при вызове GigaChat: {e}")
    logger.info("Сырой ответ LLM (первые 1000 символов): %s", response[:1000])

    # Парсим и валидируем JSON‑ответ от LLM
    validated = JSONParserValidator.parse_and_validate(response)
    if not validated:
        logger.warning("Ответ LLM не валиден или пустой. Используем классификацию без рекомендаций.")
        fallback_reports: List[ProblemReport] = []
        for err in classified:
            fallback_reports.append(ProblemReport(
                message=err.message,
                frequency=err.frequency,
                original_message=err.original_message,
                criticality=err.criticality,
                recommendation="Не удалось получить рекомендации от LLM.",
                root_cause=None,
                info_needed=None,
            ))
        validated = fallback_reports
    else:
        logger.info("Распарсено %d проблем из ответа LLM", len(validated))
        for pr in validated:
            logger.info("Проблема: message='%s', frequency=%s, criticality=%s", pr.message, pr.frequency, pr.criticality)

    # Сохраняем примеры оригинальных сообщений, частоты и критичности из классификации.
    # LLM может понизить критичность или изменить частоту; мы не допускаем снижения
    # уровня серьёзности: выбираем максимальную критичность и копируем частоту
    sorted_errors = sorted(classified, key=lambda e: e.frequency, reverse=True)
    severity_order = {'низкая': 0, 'средняя': 1, 'высокая': 2}
    for idx, pr in enumerate(validated):
        if idx < len(sorted_errors):
            cls_err = sorted_errors[idx]
            # Переносим оригинальное сообщение из классификатора
            pr.original_message = cls_err.original_message
            # Обновляем частоту: используем частоту из классификации
            pr.frequency = cls_err.frequency
            # Выбираем более высокую критичность
            classified_crit = cls_err.criticality or 'низкая'
            llm_crit = pr.criticality or 'низкая'
            if severity_order.get(llm_crit, 0) < severity_order.get(classified_crit, 0):
                pr.criticality = classified_crit

    # Группируем результат, объединяя одинаковые сообщения
    grouped_report = group_problems_by_frequency(validated)
    json_report = ReportGenerator.generate_json_report(grouped_report)

    # Создаём временный CSV‑файл
    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".csv", dir="app/reports") as tmp:
        csv_path = tmp.name
    ReportGenerator.generate_csv_report(grouped_report, csv_path)
    logger.info("CSV-отчёт сохранён: %s", csv_path)

    return {
        "report": json_report,
        "csv_url": f"/api/download-report?path={os.path.basename(csv_path)}",
    }


@router.get("/download-report")
async def download_report(path: str):
    """
    Возвращает CSV‑файл отчёта по указанному имени.

    :param path: имя CSV‑файла в каталоге ``app/reports``.
    :raises HTTPException: если файл не найден.
    """
    csv_full_path = os.path.join("app/reports", path)
    if not os.path.exists(csv_full_path):
        raise HTTPException(status_code=404, detail="Файл не найден")
    return FileResponse(csv_full_path, filename="problems_report.csv")