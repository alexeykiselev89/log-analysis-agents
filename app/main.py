"""
Главная точка входа FastAPI‑приложения.

Этот модуль инициализирует объект приложения, подключает маршруты
API и веб‑интерфейса, а также, при наличии каталога `static`,
обслуживает статические файлы. Структура файла проста: сначала
создаётся приложение FastAPI, затем подключаются два маршрутизатора
(`router` для JSON‑API и `router_ui` для HTML‑интерфейса), после чего
определяется путь к статическим ресурсам и, если каталог существует,
монтируется путь `/static`.
"""

import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.api.endpoints import router
from app.frontend import router_ui


app = FastAPI(title="AI Log Analysis Agent", version="1.0")

# Подключаем маршруты API и веб‑интерфейса. Маршрутизатор `router`
# обслуживает JSON‑эндпоинты (prefixed с `/api`), а `router_ui` —
# HTML‑формы и шаблоны.
app.include_router(router, prefix="/api")
app.include_router(router_ui)

# Монтируем обработчик статики `/static` только если каталог существует.
# Это позволяет избежать ошибки при запуске в окружениях без каталога
# `static`. В таких случаях приложение просто пропускает монтирование.
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")