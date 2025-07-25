import os
import aiohttp
from dotenv import load_dotenv

load_dotenv()

GIGACHAT_API_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
GIGACHAT_AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"


class GigaChatClient:
    def __init__(self) -> None:
        self.client_id = os.getenv("GIGACHAT_CLIENT_ID")
        self.auth_key = os.getenv("GIGACHAT_AUTH_KEY")
        self.scope = os.getenv("GIGACHAT_API_SCOPE")
        self.access_token: str | None = None
        # Validate credentials early
        if not (self.client_id and self.auth_key and self.scope):
            raise RuntimeError(
                "GigaChat credentials are missing. Please set GIGACHAT_CLIENT_ID, GIGACHAT_AUTH_KEY and GIGACHAT_API_SCOPE."
            )

    async def authenticate(self) -> None:
        """
        Obtain an access token from the GigaChat authentication endpoint. Raises
        RuntimeError on HTTP errors such as 401 Unauthorized.
        """
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Basic {self.auth_key}",
                    "RqUID": self.client_id,
                    "Content-Type": "application/x-www-form-urlencoded",
                }
                data = {"scope": self.scope}
                async with session.post(GIGACHAT_AUTH_URL, headers=headers, data=data, ssl=False) as resp:
                    # Raise for HTTP errors (4xx, 5xx)
                    resp.raise_for_status()
                    json_resp = await resp.json()
                    self.access_token = json_resp.get("access_token")
        except aiohttp.ClientResponseError as e:
            # Provide a more descriptive error for authentication failures
            raise RuntimeError(f"GigaChat authentication failed: {e.status} {e.message}") from e
        except Exception as e:
            raise RuntimeError(f"Unexpected error during GigaChat authentication: {e}") from e

    async def get_completion(self, prompt: str) -> str:
        """
        Send a prompt to the GigaChat completion endpoint and return the model's
        response. Authentication is performed automatically if needed.
        """
        if not self.access_token:
            await self.authenticate()
        try:
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": "GigaChat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(GIGACHAT_API_URL, json=payload, headers=headers, ssl=False) as resp:
                    resp.raise_for_status()
                    json_resp = await resp.json()
                    return json_resp["choices"][0]["message"]["content"]
        except aiohttp.ClientResponseError as e:
            raise RuntimeError(f"GigaChat API request failed: {e.status} {e.message}") from e
        except Exception as e:
            raise RuntimeError(f"Unexpected error during GigaChat request: {e}") from e