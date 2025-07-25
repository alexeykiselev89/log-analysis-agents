import os
import tempfile
import aiofiles
import logging
from collections import defaultdict
from typing import List

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from app.agents.log_parser import LogParser
from app.agents.error_classifier import ErrorClassifier
from app.agents.prompt_builder import PromptBuilder
from app.agents.gigachat_client import GigaChatClient
from app.agents.json_parser_validator import JSONParserValidator, ProblemReport
from app.agents.report_generator import ReportGenerator

# Configure logging: INFO by default, enable DEBUG for more detailed output
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()


def group_problems_by_frequency(problems: List[ProblemReport]) -> List[ProblemReport]:
    """
    Aggregate problem reports with identical frequency values into a single
    report. When multiple entries share the same frequency, their messages
    and recommendations are concatenated, and the highest criticality level
    (высокая > средняя > низкая) is preserved. The original messages are
    combined using vertical bars.

    Args:
        problems: A list of ProblemReport instances returned by the LLM.

    Returns:
        A new list of ProblemReport instances with grouped entries.
    """
    grouped: dict[int, List[ProblemReport]] = defaultdict(list)
    for pr in problems:
        grouped[pr.frequency].append(pr)

    result: List[ProblemReport] = []
    for freq, items in grouped.items():
        if len(items) == 1:
            result.append(items[0])
            continue
        # Concatenate messages and recommendations
        combined_message = "; ".join([item.message for item in items])
        combined_original = " | ".join([item.original_message for item in items if item.original_message]) or None
        # Determine the most severe criticality
        criticalities = [item.criticality for item in items]
        final_crit = 'низкая'
        if 'высокая' in criticalities:
            final_crit = 'высокая'
        elif 'средняя' in criticalities:
            final_crit = 'средняя'
        # Concatenate recommendations separated by blank lines
        combined_recommendation = "\n\n".join([item.recommendation for item in items])
        result.append(ProblemReport(
            message=combined_message,
            original_message=combined_original,
            frequency=freq,
            criticality=final_crit,
            recommendation=combined_recommendation,
        ))
    return result


@router.post("/analyze-log")
async def analyze_log(file: UploadFile = File(...)):
    logger.info("Начат анализ загруженного лог-файла")
    # Read the uploaded log file
    try:
        content = await file.read()
        log_content = content.decode("utf-8")
        logger.info("Получено %d байт логов", len(content))
    except Exception as ex:
        logger.exception("Ошибка при чтении файла: %s", ex)
        raise HTTPException(status_code=400, detail="Ошибка при чтении файла")

    # Analyse logs via the agent pipeline
    entries = LogParser.parse_log(log_content)
    logger.info("Распарсено %d записей с уровнем WARN/ERROR", len(entries))
    grouped_entries = LogParser.group_by_normalized_message(entries)
    logger.info("Сгруппировано %d уникальных ошибок", len(grouped_entries))
    classified_errors = ErrorClassifier.classify_errors(grouped_entries)
    logger.info("После классификации получено %d ошибок", len(classified_errors))

    # Build prompt for the LLM
    prompt = PromptBuilder.build_prompt(classified_errors)
    logger.debug("Промт для LLM:\n%s", prompt)

    gigachat = GigaChatClient()
    response = await gigachat.get_completion(prompt)
    logger.debug("Сырой ответ от LLM (первые 500 символов): %s", response[:500])

    validated_report = JSONParserValidator.parse_and_validate(response)
    if not validated_report:
        logger.error("Ответ LLM не валиден или пустой")
        raise HTTPException(status_code=422, detail="Ответ LLM не валиден или пустой")
    logger.info("Распарсено %d проблем из ответа LLM", len(validated_report))

    # Map original messages from classified errors to the LLM responses
    sorted_errors = sorted(classified_errors, key=lambda err: err.frequency, reverse=True)
    for idx, problem in enumerate(validated_report):
        if idx < len(sorted_errors):
            problem.original_message = sorted_errors[idx].original_message

    # Group problems by frequency to avoid duplicate rows with the same count
    grouped_report = group_problems_by_frequency(validated_report)

    json_report = ReportGenerator.generate_json_report(grouped_report)

    # Generate a temporary CSV file
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