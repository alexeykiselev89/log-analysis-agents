import aiohttp
import os
from dotenv import load_dotenv

load_dotenv()

GIGACHAT_API_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
GIGACHAT_AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"

class GigaChatClient:
    def __init__(self):
        self.client_id = os.getenv("GIGACHAT_CLIENT_ID")
        self.auth_key = os.getenv("GIGACHAT_AUTH_KEY")
        self.scope = os.getenv("GIGACHAT_API_SCOPE")
        self.access_token = None

    async def authenticate(self):
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Basic {self.auth_key}",
                "RqUID": self.client_id,
                "Content-Type": "application/x-www-form-urlencoded"
            }
            data = {"scope": self.scope}
            # 🔒 Отключаем SSL-проверку временно
            async with session.post(GIGACHAT_AUTH_URL, headers=headers, data=data, ssl=False) as resp:
                resp.raise_for_status()
                json_resp = await resp.json()
                self.access_token = json_resp['access_token']

    async def get_completion(self, prompt: str) -> str:
        if not self.access_token:
            await self.authenticate()

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "GigaChat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3
        }

        async with aiohttp.ClientSession() as session:
            # 🔒 Отключаем SSL-проверку временно
            async with session.post(GIGACHAT_API_URL, json=payload, headers=headers, ssl=False) as resp:
                resp.raise_for_status()
                json_resp = await resp.json()
                return json_resp['choices'][0]['message']['content']
