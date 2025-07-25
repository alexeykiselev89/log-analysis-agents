import os
import tempfile
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from app.agents.log_parser import LogParser
from app.agents.error_classifier import ErrorClassifier
from app.agents.prompt_builder import PromptBuilder
from app.agents.gigachat_client import GigaChatClient
from app.agents.json_parser_validator import JSONParserValidator
from app.agents.report_generator import ReportGenerator

router = APIRouter()

@router.post("/analyze-log")
async def analyze_log(file: UploadFile = File(...)):
    try:
        content = await file.read()
        log_content = content.decode("utf-8")
    except Exception:
        raise HTTPException(status_code=400, detail="Ошибка при чтении файла")

    # Сбор данных
    entries = LogParser.parse_log(log_content)
    grouped_entries = LogParser.group_by_normalized_message(entries)
    classified_errors = ErrorClassifier.classify_errors(grouped_entries)

    # Формируем запрос
    prompt = PromptBuilder.build_prompt(classified_errors)

    gigachat = GigaChatClient()
    response = await gigachat.get_completion(prompt)

    # Парсим ответ LLM
    validated_report = JSONParserValidator.parse_and_validate(response)
    if not validated_report:
        raise HTTPException(status_code=422, detail="Ответ LLM не валиден или пустой")

    # Сохраняем original_message в отчёте, сортируя по частоте
    sorted_errors = sorted(classified_errors, key=lambda err: err.frequency, reverse=True)
    for idx, problem in enumerate(validated_report):
        if idx < len(sorted_errors):
            problem.original_message = sorted_errors[idx].original_message

    json_report = ReportGenerator.generate_json_report(validated_report)

    # Создаём CSV
    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".csv", dir="app/reports") as tmp:
        csv_path = tmp.name
    ReportGenerator.generate_csv_report(validated_report, csv_path)

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
