"""
    Модуль содержит HTTP‑эндпоинты API для анализа лог‑файлов и скачивания
    отчётов.

    Эндпоинт `/analyze-log` принимает загруженный пользователем лог‑файл,
    извлекает важные записи, группирует и классифицирует их, запрашивает
    рекомендации у LLM и возвращает JSON‑отчёт вместе с путём для скачивания
    CSV. Эндпоинт `/download-report` отдаёт готовый CSV‑файл по имени.
"""

import os
import tempfile
import aiofiles
import logging
from collections import defaultdict
from typing import List
import re

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse

from app.agents.log_parser import LogParser
from app.agents.error_classifier import ErrorClassifier, ClassifiedError
from app.agents.prompt_builder import PromptBuilder
from app.agents.gigachat_client import GigaChatClient
from app.agents.json_parser_validator import JSONParserValidator, ProblemReport
from app.agents.report_generator import ReportGenerator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
router = APIRouter()


def group_problems_by_frequency(problems: List[ProblemReport]) -> List[ProblemReport]:
    """
    Группирует проблемы по их сообщению, суммируя частоты и объединяя данные.

    Изначальная реализация объединяла проблемы только по частоте появления, что
    приводило к слиянию разных ошибок, если они происходили одинаковое число
    раз. Эта версия группирует проблемы по тексту поля `message` (нормализованное
    сообщение), чтобы каждая уникальная ошибка учитывалась отдельно.

    Для каждой группы выполняются следующие действия:

    * Суммируется частота (`frequency`).
    * Объединяются исходные сообщения (`original_message`) без дубликатов. При
      объединении строки разделяются по разделителям `|`, `\n---\n` и обычным
      переводам строк, затем уникальные элементы собираются через ` | `.
    * Критичность выбирается по максимальному уровню («высокая» > «средняя» > «низкая»).
    * Рекомендации преобразуются в единый упорядоченный список шагов; номера удаляются,
      дубликаты отфильтровываются и шаги перенумеровываются от 1 до N.
    * Поля `root_cause` и `info_needed` собираются в списки, строки разделяются
      по точкам с запятой и переводам строк, дублирующиеся элементы удаляются.
    """
    grouped: dict[str, List[ProblemReport]] = defaultdict(list)
    for pr in problems:
        key = (pr.message or "").strip()
        grouped[key].append(pr)

    result: List[ProblemReport] = []
    for msg, items in grouped.items():
        if len(items) == 1:
            result.append(items[0])
            continue
        combined_msg = msg
        # Sum frequencies
        freq_sum = sum(it.frequency for it in items if it.frequency)
        # Merge original messages, splitting by '|' and newline separators and '---'
        origs: List[str] = []
        for it in items:
            if it.original_message:
                # Split by |, newlines and the delimiter used in classification ('\n---\n')
                parts = re.split(r'\n---\n|\n|\|', it.original_message)
                for part in parts:
                    part = part.strip()
                    if part and part not in origs:
                        origs.append(part)
        combined_orig = " | ".join(origs) if origs else None
        # Ограничиваем длину собранного исходного сообщения, чтобы отчет
        # показывал не более 200 символов. Это защищает от слишком длинных
        # строк, которые могут появиться после объединения нескольких примеров.
        if combined_orig and len(combined_orig) > 200:
            combined_orig = combined_orig[:200] + "…"
        # Determine highest criticality
        crits = [it.criticality for it in items]
        final_crit = 'низкая'
        if 'высокая' in crits:
            final_crit = 'высокая'
        elif 'средняя' in crits:
            final_crit = 'средняя'
        # Merge recommendations
        all_steps: List[str] = []
        seen_keys: set[str] = set()
        for it in items:
            rec = it.recommendation or ''
            parts = re.split(r'[;\n]+', rec)
            for part in parts:
                step = part.strip()
                if not step:
                    continue
                step = re.sub(r'^\d+\.\s*', '', step)
                if not step:
                    continue
                lower = step.lower().rstrip('.').rstrip(',')
                words = lower.split()
                norm_words: list[str] = []
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
        # Если удалось извлечь шаги рекомендаций, нумеруем их и разделяем переводом строки.
        # Если рекомендаций нет, заполняем дефисом, чтобы поле было строкой (требуется pydantic).
        if all_steps:
            combined_rec = "\n".join(
                f"{idx + 1}. {text}" for idx, text in enumerate(all_steps)
            )
        else:
            combined_rec = '—'
        # Merge root causes
        root_causes: List[str] = []
        for it in items:
            if it.root_cause:
                for rc in re.split(r'[;\n]+', it.root_cause):
                    rc = rc.strip()
                    if rc and rc not in root_causes:
                        root_causes.append(rc)
        combined_root = "; ".join(root_causes) if root_causes else None
        # Merge info needed
        info_needed_list: List[str] = []
        for it in items:
            if it.info_needed:
                for info in re.split(r'[;\n]+', it.info_needed):
                    info = info.strip()
                    if info and info not in info_needed_list:
                        info_needed_list.append(info)
        combined_info = "; ".join(info_needed_list) if info_needed_list else None
        # Create new ProblemReport. Если рекомендаций нет, передаём дефис (см. выше).
        result.append(ProblemReport(
            message=combined_msg,
            original_message=combined_orig,
            frequency=freq_sum,
            criticality=final_crit,
            recommendation=combined_rec,
            root_cause=combined_root,
            info_needed=combined_info,
        ))
    return result


@router.post("/analyze-log")
async def analyze_log(file: UploadFile = File(...)):
    """
    Обрабатывает загруженный лог‑файл: парсит записи, группирует и классифицирует ошибки,
    запрашивает рекомендации у LLM и формирует отчёт.

    :param file: загруженный пользователем лог‑файл (UploadFile).
    :return: словарь с полями ``report`` (JSON‑строка с отчётом) и ``csv_url`` (URL для скачивания CSV‑отчёта).
    """
    logger.info("Начат анализ загруженного лог-файла")
    try:
        content = await file.read()
        log_content = content.decode("utf-8")
        logger.info("Получено %d байт логов", len(content))
    except Exception as ex:
        logger.exception("Ошибка при чтении файла: %s", ex)
        raise HTTPException(status_code=400, detail="Ошибка при чтении файла")

    entries = LogParser.parse_log(log_content)
    logger.info("Распарсено %d записей с интересующими уровнями", len(entries))
    grouped_entries = LogParser.group_by_normalized_message(entries)
    logger.info("Сгруппировано %d уникальных ошибок", len(grouped_entries))
    classified = ErrorClassifier.classify_errors(grouped_entries)
    logger.info("После классификации получено %d ошибок", len(classified))

    prompt = PromptBuilder.build_prompt(classified)
    logger.info("Промт для LLM:\n%s", prompt)

    gigachat = GigaChatClient()
    try:
        response = await gigachat.get_completion(prompt)
    except Exception as e:
        logger.exception("Ошибка при вызове GigaChat: %s", e)
        raise HTTPException(status_code=502, detail=f"Ошибка при вызове GigaChat: {e}")
    logger.info("Сырой ответ LLM (первые 1000 символов): %s", response[:1000])

    validated = JSONParserValidator.parse_and_validate(response)
    if not validated:
        logger.warning("Ответ LLM не валиден или пустой. Используем классификацию без рекомендаций.")
        fallback_reports: List[ProblemReport] = []
        for err in classified:
            fallback_reports.append(ProblemReport(
                message=err.message,
                original_message=err.original_message,
                frequency=err.frequency,
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
    # Preserve original messages according to decreasing frequency
    sorted_errors = sorted(classified, key=lambda e: e.frequency, reverse=True)
    for idx, pr in enumerate(validated):
        if idx < len(sorted_errors):
            pr.original_message = sorted_errors[idx].original_message

    # Group by message, merging data
    grouped_report = group_problems_by_frequency(validated)
    json_report = ReportGenerator.generate_json_report(grouped_report)
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
    Возвращает CSV‑файл отчёта по указанному имени файла.

    :param path: имя CSV‑файла в каталоге ``app/reports``.
    :raises HTTPException: если файл не найден.
    """
    csv_full_path = os.path.join("app/reports", path)
    if not os.path.exists(csv_full_path):
        raise HTTPException(status_code=404, detail="Файл не найден")
    return FileResponse(csv_full_path, filename="problems_report.csv")
