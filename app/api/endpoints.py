
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
    Группирует проблемы по частоте появления.

    При объединении нескольких записей с одинаковой частотой выполняются
    следующие действия:

    * Объединяются сообщения об ошибках, убирая дубли — итоговая строка
      содержит уникальные сообщения, разделённые точкой с запятой.
    * Объединяются оригинальные сообщения (если присутствуют), разделённые
      вертикальной чертой.
    * Критичность выбирается по максимальному уровню («высокая» >
      «средняя» > «низкая»).
    * Список рекомендаций преобразуется в единый упорядоченный список: из
      каждой рекомендации извлекаются отдельные шаги (нумерованные строки),
      номера удаляются, затем все шаги собираются в общую последовательность,
      уникальные шаги сохраняются в исходном порядке и перенумеровываются
      от 1 до N.
    * Первопричины (`root_cause`) и требуемая информация (`info_needed`)
      собираются в списки, дублирующиеся элементы удаляются.
    """

    grouped: dict[int, List[ProblemReport]] = defaultdict(list)
    for pr in problems:
        grouped[pr.frequency].append(pr)

    result: List[ProblemReport] = []
    for freq, items in grouped.items():
        # Если только одна запись с такой частотой, возвращаем её как есть
        if len(items) == 1:
            result.append(items[0])
            continue

        # Объединяем сообщения и оставляем только уникальные
        messages: List[str] = []
        for it in items:
            for msg in it.message.split(';'):
                msg = msg.strip()
                if msg and msg not in messages:
                    messages.append(msg)
        combined_msg = "; ".join(messages)

        # Объединяем исходные сообщения без дубликатов
        origs: List[str] = []
        for it in items:
            if it.original_message:
                for part in it.original_message.split('|'):
                    part = part.strip()
                    if part and part not in origs:
                        origs.append(part)
        combined_orig = " | ".join(origs) if origs else None

        # Определяем наибольший уровень критичности
        crits = [it.criticality for it in items]
        final_crit = 'низкая'
        if 'высокая' in crits:
            final_crit = 'высокая'
        elif 'средняя' in crits:
            final_crit = 'средняя'

        # Собираем и перенумеровываем рекомендации
        # В каждой рекомендации могут быть несколько шагов, разделённых точкой с запятой или переводом строки.
        all_steps: List[str] = []
        # Для удаления почти одинаковых шагов (например, "Проверьте" и "Проверить")
        seen_keys: set[str] = set()
        for it in items:
            rec = it.recommendation or ''
            # Разделяем по точке с запятой и переводам строк
            parts = re.split(r'[;\n]+', rec)
            for part in parts:
                step = part.strip()
                if not step:
                    continue
                # Удаляем ведущую нумерацию вида "1. " или "2." (с пробелом или без)
                step = re.sub(r'^\d+\.\s*', '', step)
                if not step:
                    continue
                # Формируем ключ для дедупликации: переводим в нижний регистр,
                # убираем точки/запятые и снимаем некоторые окончания у слов.
                lower = step.lower().rstrip('.').rstrip(',')
                words = lower.split()
                norm_words: list[str] = []
                for w in words:
                    base = w
                    # Обрезаем наиболее частые суффиксы глаголов и причастий, чтобы унифицировать
                    # формы типа «создайте/создать», «удалите/удалить», «проверьте/проверить».
                    for suf in ('тесь', 'тесь', 'йтесь', 'итесь', 'итесь', 'йте', 'ите', 'ете', 'те', 'ть'):
                        if base.endswith(suf) and len(base) > len(suf):
                            base = base[:-len(suf)]
                            break
                    # Убираем мягкий знак и лишние ё/е для упрощения сравнения
                    base = base.replace('ё', 'е').rstrip('ь')
                    norm_words.append(base)
                # Формируем ключ: склеиваем нормализованные слова и берём первые 25 символов
                key = ''.join(norm_words)[:25]
                if key not in seen_keys:
                    seen_keys.add(key)
                    all_steps.append(step)
        # Создаём перенумерованный список
        combined_rec = "\n".join([
            f"{idx + 1}. {text}" for idx, text in enumerate(all_steps)
        ]) if all_steps else ''

        # Убираем дубликаты из root_cause и info_needed
        root_causes: List[str] = []
        for it in items:
            if it.root_cause:
                for rc in it.root_cause.split(';'):
                    rc = rc.strip()
                    if rc and rc not in root_causes:
                        root_causes.append(rc)
        combined_root = "; ".join(root_causes) if root_causes else None

        info_needed_list: List[str] = []
        for it in items:
            if it.info_needed:
                for info in it.info_needed.split(';'):
                    info = info.strip()
                    if info and info not in info_needed_list:
                        info_needed_list.append(info)
        combined_info = "; ".join(info_needed_list) if info_needed_list else None

        result.append(ProblemReport(
            message=combined_msg,
            original_message=combined_orig,
            frequency=freq,
            criticality=final_crit,
            recommendation=combined_rec,
            root_cause=combined_root,
            info_needed=combined_info,
        ))
    return result


@router.post("/analyze-log")
async def analyze_log(file: UploadFile = File(...)):
    """
    Обрабатывает загруженный лог‑файл: парсит записи, группирует и
    классифицирует ошибки, запрашивает рекомендации у LLM и формирует
    отчёт.

    :param file: загруженный пользователем лог‑файл (UploadFile).
    :return: словарь с полями ``report`` (JSON‑строка с отчётом) и
        ``csv_url`` (URL для скачивания CSV‑отчёта).
    """
    logger.info("Начат анализ загруженного лог-файла")
    try:
        content = await file.read()
        # Читаем файл и получаем его содержимое в байтах
        log_content = content.decode("utf-8")
        # Декодируем байты файла в строку
        logger.info("Получено %d байт логов", len(content))
    except Exception as ex:
        logger.exception("Ошибка при чтении файла: %s", ex)
        raise HTTPException(status_code=400, detail="Ошибка при чтении файла")

    # Извлекаем только записи уровней WARN/ERROR
    entries = LogParser.parse_log(log_content)
    logger.info("Распарсено %d записей с уровнем WARN/ERROR", len(entries))
    # Группируем записи по нормализованному сообщению
    grouped_entries = LogParser.group_by_normalized_message(entries)
    logger.info("Сгруппировано %d уникальных ошибок", len(grouped_entries))
    # Классифицируем группы ошибок и определяем уровни критичности
    classified = ErrorClassifier.classify_errors(grouped_entries)
    logger.info("После классификации получено %d ошибок", len(classified))

    # Формируем промт для LLM с помощью PromptBuilder
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
    # Парсим и валидируем JSON‑ответ LLM
    if not validated:
        # Если валидация не удалась или LLM вернул пустой ответ,
        # используем классификацию без рекомендаций
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
    # Назначаем исходные сообщения в соответствии с убыванием частоты
    sorted_errors = sorted(classified, key=lambda e: e.frequency, reverse=True)
    for idx, pr in enumerate(validated):
        if idx < len(sorted_errors):
            pr.original_message = sorted_errors[idx].original_message

    # Группируем проблемы по частоте, объединяя сообщения и рекомендации
    grouped_report = group_problems_by_frequency(validated)
    json_report = ReportGenerator.generate_json_report(grouped_report)
    # Генерируем JSON‑отчёт из списка проблем
    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".csv", dir="app/reports") as tmp:
        csv_path = tmp.name
    ReportGenerator.generate_csv_report(grouped_report, csv_path)
    # Сохраняем CSV‑отчёт в файл
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
