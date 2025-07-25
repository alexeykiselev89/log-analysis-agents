import os
import tempfile
import aiofiles
import logging
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


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
router = APIRouter()


def group_problems_by_frequency(problems: List[ProblemReport]) -> List[ProblemReport]:
    """
    Groups problems by frequency.  Concatenates messages and recommendations,
    and preserves the highest criticality.  If present, root_cause and
    info_needed are combined.
    """
    grouped: dict[int, List[ProblemReport]] = defaultdict(list)
    for pr in problems:
        grouped[pr.frequency].append(pr)
    result: List[ProblemReport] = []
    for freq, items in grouped.items():
        if len(items) == 1:
            result.append(items[0])
            continue
        combined_msg = "; ".join([it.message for it in items])
        combined_orig = " | ".join([it.original_message for it in items if it.original_message]) or None
        crits = [it.criticality for it in items]
        final_crit = 'низкая'
        if 'высокая' in crits:
            final_crit = 'высокая'
        elif 'средняя' in crits:
            final_crit = 'средняя'
        combined_rec = "\n\n".join([it.recommendation for it in items])
        combined_root = "; ".join([it.root_cause for it in items if it.root_cause]) or None
        combined_info = "; ".join([it.info_needed for it in items if it.info_needed]) or None
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
    logger.info("Начат анализ загруженного лог-файла")
    try:
        content = await file.read()
        log_content = content.decode("utf-8")
        logger.info("Получено %d байт логов", len(content))
    except Exception as ex:
        logger.exception("Ошибка при чтении файла: %s", ex)
        raise HTTPException(status_code=400, detail="Ошибка при чтении файла")

    entries = LogParser.parse_log(log_content)
    logger.info("Распарсено %d записей с уровнем WARN/ERROR", len(entries))
    grouped_entries = LogParser.group_by_normalized_message(entries)
    logger.info("Сгруппировано %d уникальных ошибок", len(grouped_entries))
    classified = ErrorClassifier.classify_errors(grouped_entries)
    logger.info("После классификации получено %d ошибок", len(classified))

    # Build prompt (using whichever PromptBuilder is installed)
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
        # If validation failed or LLM returned nothing, fallback to classified errors
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
    # Map original messages to validated problems (by order of frequency)
    sorted_errors = sorted(classified, key=lambda e: e.frequency, reverse=True)
    for idx, pr in enumerate(validated):
        if idx < len(sorted_errors):
            pr.original_message = sorted_errors[idx].original_message

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
    csv_full_path = os.path.join("app/reports", path)
    if not os.path.exists(csv_full_path):
        raise HTTPException(status_code=404, detail="Файл не найден")
    return FileResponse(csv_full_path, filename="problems_report.csv")