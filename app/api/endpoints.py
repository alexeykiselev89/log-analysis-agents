import os
import tempfile
import aiofiles
import logging
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from app.agents.log_parser import LogParser
from app.agents.error_classifier import ErrorClassifier
from app.agents.prompt_builder import PromptBuilder
from app.agents.gigachat_client import GigaChatClient
from app.agents.json_parser_validator import JSONParserValidator
from app.agents.report_generator import ReportGenerator

# Конфигурация логирования: INFO по умолчанию, включайте DEBUG для промта и ответа LLM
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/analyze-log")
async def analyze_log(file: UploadFile = File(...)):
    logger.info("Начат анализ загруженного лог-файла")
    # Читаем файл логов
    try:
        content = await file.read()
        log_content = content.decode("utf-8")
        logger.info("Получено %d байт логов", len(content))
    except Exception as ex:
        logger.exception("Ошибка при чтении файла: %s", ex)
        raise HTTPException(status_code=400, detail="Ошибка при чтении файла")

    # Анализируем логи через пайплайн агентов
    entries = LogParser.parse_log(log_content)
    logger.info("Распарсено %d записей с уровнем WARN/ERROR", len(entries))
    grouped_entries = LogParser.group_by_normalized_message(entries)
    logger.info("Сгруппировано %d уникальных ошибок", len(grouped_entries))
    classified_errors = ErrorClassifier.classify_errors(grouped_entries)
    logger.info("После классификации получено %d ошибок", len(classified_errors))
    # Строим запрос на основе классифицированных ошибок
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

    # Сопоставляем исходные сообщения из классифицированных ошибок с ответами LLM.
    sorted_errors = sorted(classified_errors, key=lambda err: err.frequency, reverse=True)
    for idx, problem in enumerate(validated_report):
        if idx < len(sorted_errors):
            problem.original_message = sorted_errors[idx].original_message

    json_report = ReportGenerator.generate_json_report(validated_report)

    # Генерируем временный CSV‑файл
    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".csv", dir="app/reports") as tmp:
        csv_path = tmp.name
    ReportGenerator.generate_csv_report(validated_report, csv_path)
    logger.info("CSV-отчёт сохранён: %s", csv_path)

    return {
        "report": json_report,
        "csv_url": f"/api/download-report?path={os.path.basename(csv_path)}"
    }

@router.get("/download-report")
async def download_report(path: str):
    csv_full_path = os.path.join("app/reports", path)
    if not os.path.exists(csv_full_path):
        raise HTTPException(status_code=404, detail="Файл не найден")
    return FileResponse(csv_full_path, filename="problems_report.csv")
