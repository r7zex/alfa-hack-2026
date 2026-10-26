"""Bounded OpenAI-compatible Qwen transport. No tools, redirects or raw errors."""

import json

import httpx
from pydantic import BaseModel, ValidationError

from app.settings import Settings


class QwenUnavailable(Exception):
    pass


class QwenClient:
    def __init__(self, settings: Settings, transport=None):
        self.settings = settings
        self.transport = transport

    async def complete(
        self, system: str, data: dict, schema: type[BaseModel]
    ) -> BaseModel:
        key = self.settings.qwen_api_key.get_secret_value()
        headers = {"Authorization": "Bearer " + key} if key else {}
        payload = {
            "model": self.settings.qwen_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(data, ensure_ascii=False)},
            ],
            "temperature": 0,
            "stream": False,
            "response_format": {"type": "json_object"},
            # A truncated JSON response is rejected, never shown to the user.
            "max_tokens": 512 if "answer" in schema.model_fields else 48,
        }
        # Ollama enables thinking by default for Qwen 3.8. Disable it so the
        # scope checks and generator return their final JSON within the budget.
        model_name = (
            self.settings.qwen_model.casefold().rsplit("/", 1)[-1].split(":", 1)[0]
        )
        effort = self.settings.qwen_reasoning_effort
        if effort == "none" or (effort == "auto" and model_name == "qwen3.8"):
            payload["reasoning_effort"] = "none"
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(
                    self.settings.assistant_timeout_seconds, connect=10
                ),
                follow_redirects=False,
                trust_env=True,
                transport=self.transport,
            ) as client:
                async with client.stream(
                    "POST",
                    self.settings.qwen_base_url + "/chat/completions",
                    headers=headers,
                    json=payload,
                ) as response:
                    if response.status_code != 200:
                        raise QwenUnavailable("Model service rejected the request")
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > 131072:
                            raise QwenUnavailable("Model response is too large")
            result = json.loads(content)
            choice = result["choices"][0]
            if choice.get("finish_reason") != "stop" or choice["message"].get(
                "tool_calls"
            ):
                raise QwenUnavailable("Model response is incomplete")
            return schema.model_validate_json(choice["message"]["content"])
        except (
            httpx.HTTPError,
            ValueError,
            KeyError,
            IndexError,
            TypeError,
            ValidationError,
        ) as exc:
            raise QwenUnavailable(
                "Model service is unavailable or returned invalid JSON"
            ) from exc


def get_qwen_client(settings: Settings) -> QwenClient:
    return QwenClient(settings)
