from fastapi import APIRouter, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import os
from app.api.endpoints import analyze_log

router_ui = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router_ui.get("/", response_class=HTMLResponse)
async def main_form(request: Request):
    return templates.TemplateResponse("upload.html", {"request": request})

@router_ui.post("/upload", response_class=HTMLResponse)
async def upload_log(
    request: Request,
    file: UploadFile = File(...),
    mode: str = Form("full")
):
    result = await analyze_log(file)

    # Парсим JSON-строку отчёта
    import json
    report_data = json.loads(result["report"])

    problems = report_data["problems"]
    if mode == "critical":
        problems = [p for p in problems if p["criticality"] == "высокая"]
    elif mode == "short":
        problems = problems[:3]

    return templates.TemplateResponse("report.html", {
        "request": request,
        "parsed": problems,
        "csv_url": result["csv_url"],
        "mode": mode,
        "filename": file.filename
    })
