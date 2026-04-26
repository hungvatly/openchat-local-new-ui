"""
OpenChat Local — Ollama Client
Async client for Ollama API with streaming support.
"""
import json
from typing import AsyncGenerator, List, Dict, Optional
import aiohttp

from config import settings


from utils.local_llm import SYSTEM_PROMPT


class OllamaClient:
    def __init__(self):
        self._base_url = settings.OLLAMA_BASE_URL

    @property
    def base_url(self) -> str:
        return self._base_url

    @base_url.setter
    def base_url(self, url: str):
        self._base_url = url.rstrip("/")
        settings.OLLAMA_BASE_URL = self._base_url
        print(f"  [Ollama] Base URL updated to: {self._base_url}")

    async def check_health(self) -> bool:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/api/tags", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    return resp.status == 200
        except Exception:
            return False

    async def list_models(self) -> List[Dict]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/api/tags") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        models = data.get("models", [])
                        return [
                            {
                                "name": m["name"],
                                "size": m.get("size", 0),
                                "modified": m.get("modified_at", ""),
                                "family": m.get("details", {}).get("family", ""),
                                "parameter_size": m.get("details", {}).get("parameter_size", ""),
                                "quantization": m.get("details", {}).get("quantization_level", ""),
                            }
                            for m in models
                        ]
        except Exception:
            pass
        return []

    async def stream_chat(
        self,
        message: str,
        model: str = None,
        context: str = "",
        history: List[Dict] = None,
        images: List[str] = None,
        system_prompt: str = None,
    ) -> AsyncGenerator[str, None]:
        """Stream a chat completion from Ollama. images = list of base64 strings."""
        model = model or settings.DEFAULT_MODEL
        prompt = system_prompt or SYSTEM_PROMPT
        messages = [{"role": "system", "content": prompt}]

        if history:
            for h in history[-10:]:
                messages.append({"role": h["role"], "content": h["content"]})

        user_content = message
        if context:
            user_content = (
                f"Use the following context from the user's documents to answer the question.\n\n"
                f"--- DOCUMENT CONTEXT ---\n{context}\n--- END CONTEXT ---\n\n"
                f"Question: {message}"
            )

        user_msg = {"role": "user", "content": user_content}
        if images:
            user_msg["images"] = images
        messages.append(user_msg)

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=300),
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        yield f"[Error: Ollama returned {resp.status}: {error_text}]"
                        return

                    async for line in resp.content:
                        line = line.decode("utf-8").strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            token = data.get("message", {}).get("content", "")
                            if token:
                                yield token
                            if data.get("done", False):
                                return
                        except json.JSONDecodeError:
                            continue
        except aiohttp.ClientConnectorError:
            yield "[Error: Cannot connect to Ollama. Make sure Ollama is running on " + self.base_url + "]"
        except Exception as e:
            yield f"[Error: {str(e)}]"

    async def generate_title(self, message: str, model: str = None) -> str:
        """Generate a short title for a conversation."""
        model = model or settings.DEFAULT_MODEL
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "Generate a very short title (3-6 words) for this conversation. Reply with ONLY the title, nothing else."},
                {"role": "user", "content": message},
            ],
            "stream": False,
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("message", {}).get("content", "New Chat").strip()
        except Exception:
            pass
        return "New Chat"


ollama_client = OllamaClient()
