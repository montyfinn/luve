from __future__ import annotations

from typing import Any

import httpx

from src.llm_grader import LLMGraderError

_GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqClient:
    """Async HTTP client for the Groq chat completions API.

    Satisfies GraderClient Protocol: async def grade(self, prompt: str) -> str.
    Does not read env vars — caller supplies all config via constructor.
    Does not log prompt, transcript, API key, or response body.
    """

    def __init__(self, *, api_key: str, model: str, timeout_seconds: float) -> None:
        if not api_key.strip():
            raise LLMGraderError("GroqClient: api_key must not be empty")
        if not model.strip():
            raise LLMGraderError("GroqClient: model must not be empty")
        if timeout_seconds <= 0:
            raise LLMGraderError(
                f"GroqClient: timeout_seconds must be positive, got {timeout_seconds}"
            )
        self._api_key = api_key
        self._model = model.strip()
        self._timeout = timeout_seconds

    async def grade(self, prompt: str) -> str:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": "Return JSON only. Do not use markdown fences.",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as http:
                response = await http.post(_GROQ_CHAT_URL, headers=headers, json=body)
        except httpx.TimeoutException as exc:
            raise LLMGraderError(
                f"groq.timeout: request timed out after {self._timeout}s"
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMGraderError(
                f"groq.http_error: {type(exc).__name__}"
            ) from exc

        if response.status_code != 200:
            raise LLMGraderError(f"groq.non_200: HTTP {response.status_code}")

        try:
            data: dict[str, Any] = response.json()
        except Exception as exc:
            raise LLMGraderError(
                "groq.parse_error: response is not valid JSON"
            ) from exc

        try:
            choices: list[Any] = data["choices"]
        except (KeyError, TypeError) as exc:
            raise LLMGraderError(
                "groq.parse_error: missing choices field"
            ) from exc

        if not choices:
            raise LLMGraderError("groq.empty_choices: choices list is empty")

        try:
            content: str = choices[0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMGraderError(
                "groq.parse_error: unexpected response structure"
            ) from exc

        content = content.strip()
        if not content:
            raise LLMGraderError("groq.empty_content: response content is empty")

        return content
