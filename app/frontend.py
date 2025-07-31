"""
Обработчики FastAPI для веб‑интерфейса (HTML‑формы загрузки логов и
отображения отчётов).

Здесь определены два эндпоинта: `main_form` возвращает форму загрузки
файла, а `upload_log` принимает загруженный лог‑файл, отправляет его
на анализ и отображает результаты в HTML‑шаблоне. Дополнительно
присутствует механизм фильтрации списка проблем в зависимости от
выбранного пользователем режима.
"""

from fastapi import APIRouter, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import os
from app.api.endpoints import analyze_log

router_ui = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router_ui.get("/", response_class=HTMLResponse)
async def main_form(request: Request):
    """
    Отображает HTML‑форму на главной странице, позволяющую загрузить лог‑файл.

    :param request: объект запроса, который передаётся в шаблон для
        корректного рендеринга.
    :return: HTML‑страница с формой загрузки.
    """
    return templates.TemplateResponse("upload.html", {"request": request})

@router_ui.post("/upload", response_class=HTMLResponse)
async def upload_log(
    request: Request,
    file: UploadFile = File(...),
    mode: str = Form("full")
) -> HTMLResponse:
    """
    Обрабатывает загрузку лог‑файла, отправляет его на анализ и
    отображает полученный отчёт в HTML‑виде.

    :param request: объект запроса FastAPI, используемый в шаблоне.
    :param file: загруженный пользователем файл логов.
    :param mode: режим фильтрации отображения —
        ``full`` (показать все ошибки), ``critical`` (только с высокой
        критичностью) или ``short`` (только первые три).  Значение по
        умолчанию — ``full``.
    :return: HTML‑страница с отчётом о проблемах.
    """
    # Отправляем файл в API для анализа и получаем JSON‑отчёт и ссылку на CSV
    result = await analyze_log(file)

    # Импортируем модуль json для разбора строки отчёта, полученной от API
    import json
    # Преобразуем JSON‑строку отчёта в Python‑объект (словарь)
    report_data = json.loads(result["report"])

    problems = report_data["problems"]
    # Фильтруем список проблем в зависимости от выбранного режима
    if mode == "critical":
        problems = [p for p in problems if p["criticality"] == "высокая"]
    elif mode == "short":
        problems = problems[:3]

    # Передаём данные в HTML‑шаблон отчёта для отображения
    return templates.TemplateResponse("report.html", {
        "request": request,
        "parsed": problems,
        "csv_url": result["csv_url"],
        "mode": mode,
        "filename": file.filename
    })
