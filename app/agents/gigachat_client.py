"""
Клиент для взаимодействия с API GigaChat.

Этот модуль загружает конфигурацию из переменных окружения, выполняет
аутентификацию по протоколу OAuth и отправляет запросы к endpoint‑ам
GigaChat. При ошибках сети или авторизации генерируются исключения
`RuntimeError`, чтобы вызывающий код мог корректно обработать проблемы.
"""

import os
import aiohttp
from dotenv import load_dotenv


# Загружаем переменные из .env файла, если он существует
load_dotenv()

# Константы с URL‑ами API GigaChat. Первый используется для получения
# ответов (completion) от модели, второй — для запроса токена.
GIGACHAT_API_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
GIGACHAT_AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"


class GigaChatClient:
    """
    Клиент для общения с языковой моделью GigaChat.

    При инициализации объект считывает параметры доступа из переменных
    окружения: идентификатор клиента (`GIGACHAT_CLIENT_ID`), ключ
    базовой аутентификации (`GIGACHAT_AUTH_KEY`) и область
    (`GIGACHAT_API_SCOPE`). Эти данные нужны для получения токена доступа
    через endpoint авторизации. Полученный `access_token` затем
    используется при вызове метода `get_completion()` для отправки
    пользовательского промта и получения ответа модели.

    Атрибуты:
        client_id (str | None): идентификатор клиента, передаваемый в заголовке `RqUID`.
        auth_key (str | None): базовый ключ для аутентификации в виде строки base64.
        scope (str | None): запрашиваемая область доступа API.
        access_token (str | None): токен доступа, выдаваемый GigaChat после авторизации.
    """

    def __init__(self) -> None:
        # Читаем значения из переменных окружения. Если что‑то не установлено,
        # хранится None. Эти данные требуются для авторизации.
        self.client_id = os.getenv("GIGACHAT_CLIENT_ID")
        self.auth_key = os.getenv("GIGACHAT_AUTH_KEY")
        self.scope = os.getenv("GIGACHAT_API_SCOPE")
        self.access_token: str | None = None
        # Сразу проверяем наличие всех необходимых параметров и выдаём
        # понятную ошибку, если хотя бы один отсутствует.
        if not (self.client_id and self.auth_key and self.scope):
            raise RuntimeError(
                "Не заданы параметры GigaChat. Необходимо установить переменные "
                "GIGACHAT_CLIENT_ID, GIGACHAT_AUTH_KEY и GIGACHAT_API_SCOPE."
            )

    async def authenticate(self) -> None:
        """
        Получает access token от GigaChat и сохраняет его в `self.access_token`.

        Этот метод отправляет POST‑запрос на endpoint аутентификации с
        указанием области доступа. При HTTP‑ошибках (например, 401 или 500)
        возбуждается исключение `RuntimeError`. Даже если токен был ранее,
        новый запрос перезапишет `access_token`.
        """
        try:
            # Создаём HTTP‑сессию; закрывается автоматически.
            async with aiohttp.ClientSession() as session:
                # Заголовки для Basic‑аутентификации; RqUID идентифицирует клиента.
                headers = {
                    "Authorization": f"Basic {self.auth_key}",
                    "RqUID": self.client_id,
                    "Content-Type": "application/x-www-form-urlencoded",
                }
                # В теле запроса передаётся только область (scope).
                data = {"scope": self.scope}
                # POST‑запрос к серверу авторизации; отключаем SSL‑проверку на тестовых средах.
                async with session.post(GIGACHAT_AUTH_URL, headers=headers, data=data, ssl=False) as resp:
                    # Проверяем статус; raise_for_status() генерирует исключение при 4xx/5xx.
                    resp.raise_for_status()
                    json_resp = await resp.json()
                    # Сохраняем полученный токен.
                    self.access_token = json_resp.get("access_token")
        except aiohttp.ClientResponseError as e:
            # Перехватываем ошибки HTTP и поясняем их.
            raise RuntimeError(f"Не удалось пройти аутентификацию GigaChat: {e.status} {e.message}") from e
        except Exception as e:
            # Прочие исключения оборачиваем в RuntimeError.
            raise RuntimeError(f"Неожиданная ошибка при аутентификации GigaChat: {e}") from e

    async def get_completion(self, prompt: str) -> str:
        """
        Отправляет промт в GigaChat и возвращает ответ модели.

        При первом вызове автоматически выполняется аутентификация. Затем
        формируется JSON‑запрос с моделью `GigaChat`, списком сообщений и
        параметром temperature. В случае ошибок сети или сервера
        возбуждается `RuntimeError`.

        :param prompt: текст запроса, сформированный другим компонентом.
        :return: ответ модели (содержимое поля `message.content`).
        :raises RuntimeError: при ошибках HTTP или сетевых исключениях.
        """
        # При отсутствии токена запрашиваем его у сервера
        if not self.access_token:
            await self.authenticate()
        try:
            # Заголовки с токеном Bearer
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }
            # Формируем запрос: указываем модель, сообщения и температурный режим
            payload = {
                "model": "GigaChat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(GIGACHAT_API_URL, json=payload, headers=headers, ssl=False) as resp:
                    # Проверяем ответ на ошибки
                    resp.raise_for_status()
                    json_resp = await resp.json()
                    # Извлекаем контент из первой альтернативы
                    return json_resp["choices"][0]["message"]["content"]
        except aiohttp.ClientResponseError as e:
            raise RuntimeError(f"Запрос к API GigaChat завершился ошибкой: {e.status} {e.message}") from e
        except Exception as e:
            raise RuntimeError(f"Неожиданная ошибка при запросе к GigaChat: {e}") from e