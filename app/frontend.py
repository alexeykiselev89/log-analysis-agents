from fastapi import APIRouter, Request, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import os

router_ui = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router_ui.get("/", response_class=HTMLResponse)
async def main_form(request: Request):
    return templates.TemplateResponse("upload.html", {"request": request})

@router_ui.post("/upload", response_class=HTMLResponse)
async def upload_log(request: Request, file: UploadFile = File(...)):
    from app.api.endpoints import analyze_log
    result = await analyze_log(file)
    return templates.TemplateResponse("report.html", {
        "request": request,
        "json_report": result["report"],
        "csv_url": result["csv_url"]
    })
