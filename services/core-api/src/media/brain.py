from __future__ import annotations

import asyncio
import inspect
import json
import logging
import urllib.error
import urllib.request
from collections.abc import Awaitable, Callable
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.ai_logic import STTAnalysis


logger = logging.getLogger(__name__)

TokenCallback = Callable[[str], Awaitable[None]]


class PedagogicalReply(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    response_text: str = Field(min_length=1)
    pedagogical_feedback: str = Field(default="")
    source: str = Field(default="gemini")


class LLMProcessor:
    GROQ_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"

    SYSTEM_PROMPT = (
        "You are Lucy, a warm, encouraging English speaking coach in a live spoken "
        "practice session. Keep replies natural and short — usually 1 to 3 short "
        "sentences so the learner gets to talk.\n"
        "Conversation policy:\n"
        "- If the learner asks a direct question (for example 'what should I try', "
        "'what should I do', 'what do you recommend'), answer it first with concrete, "
        "specific suggestions or examples. Do not reply with only another question.\n"
        "- Use the recent conversation to infer the current topic and build on it. "
        "Never ask the learner to repeat information they already gave (for example, "
        "do not ask 'where did you go?' if they already told you).\n"
        "- Guide the conversation forward. After a helpful answer, ask at most one "
        "short follow-up question.\n"
        "- Prefer concrete examples over vague questions.\n"
        "- Match the learner's level: if their input is short or simple, reply with "
        "short, easy English; if their input is richer, you may use slightly richer "
        "English.\n"
        "- Always keep the conversation in English.\n"
        "When you detect a grammar or pronunciation issue, add a gentle coaching note. "
        "Never sound robotic, never shame the learner, and never output markdown.\n"
        "Output format (exactly 2 lines):\n"
        "RESPONSE_TEXT: <short conversational response in English>\n"
        "PEDAGOGICAL_FEEDBACK: <brief coaching note, or None if no issue>"
    )

    def __init__(
        self,
        *,
        api_key: str,
        model_name: str = "gemini-2.0-flash",
        provider: str = "gemini",
        timeout_seconds: float = 20.0,
    ) -> None:
        if not api_key.strip():
            raise ValueError("LLM API key must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")

        self._api_key = api_key
        self._model_name = model_name
        self._provider = provider.strip().lower()
        self._timeout_seconds = timeout_seconds

    @property
    def source(self) -> str:
        return self._provider

    async def stream_response(
        self,
        *,
        session_id: UUID,
        stt: STTAnalysis,
        on_token: TokenCallback,
        stt_metadata: Mapping[str, Any] | None = None,
        history: list[Mapping[str, str]] | None = None,
    ) -> PedagogicalReply:
        transcript = stt.raw_text.strip()
        if not transcript:
            return PedagogicalReply(
                response_text="Could you say that one more time?",
                pedagogical_feedback="",
                source="local_fallback",
            )

        prompt = self._build_user_prompt(
            stt, stt_metadata=stt_metadata, history=history
        )
        try:
            if self._provider == "groq":
                raw_output = await self._complete_from_groq(
                    prompt=prompt,
                    on_token=on_token,
                    session_id=session_id,
                )
            elif self._provider == "gemini":
                raw_output = await self._stream_from_gemini(
                    prompt=prompt,
                    on_token=on_token,
                    session_id=session_id,
                )
            else:
                raise ValueError(f"Unsupported LLM provider: {self._provider}")
            return self._parse_output(raw_output, source=self._provider)
        except asyncio.TimeoutError:
            logger.warning(
                "llm.timeout session_id=%s timeout_seconds=%.2f",
                session_id,
                self._timeout_seconds,
            )
        except Exception:
            logger.warning("llm.failure session_id=%s", session_id, exc_info=True)

        fallback = self.build_fallback_reply(stt)
        await on_token(fallback.response_text)
        return fallback

    async def _complete_from_groq(
        self,
        *,
        prompt: str,
        on_token: TokenCallback,
        session_id: UUID,
    ) -> str:
        raw_output = await asyncio.wait_for(
            asyncio.to_thread(self._request_groq_completion, prompt),
            timeout=self._timeout_seconds,
        )
        raw_output = raw_output.strip()
        if raw_output:
            await on_token(raw_output)
        return raw_output

    def _request_groq_completion(self, prompt: str) -> str:
        payload = {
            "model": self._model_name,
            "messages": [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.35,
            "max_tokens": 220,
            "stream": False,
        }
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.GROQ_CHAT_COMPLETIONS_URL,
            data=body,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "luve-core-api/0.1",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self._timeout_seconds
            ) as response:
                response_body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"Groq API error HTTP {exc.code}: {error_body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Groq API request failed: {exc.reason}") from exc

        data = json.loads(response_body)
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("Groq returned no choices")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Groq returned empty content")
        return content

    async def _stream_from_gemini(
        self,
        *,
        prompt: str,
        on_token: TokenCallback,
        session_id: UUID,
    ) -> str:
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError(
                "google-genai package is required for LLMProcessor"
            ) from exc

        client = genai.Client(api_key=self._api_key)
        config = types.GenerateContentConfig(
            system_instruction=self.SYSTEM_PROMPT,
            temperature=0.35,
            max_output_tokens=220,
        )

        pieces: list[str] = []
        try:
            await asyncio.wait_for(
                self._collect_gemini_stream(
                    client=client,
                    prompt=prompt,
                    config=config,
                    pieces=pieces,
                    on_token=on_token,
                ),
                timeout=self._timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "llm.timeout session_id=%s timeout_seconds=%.2f",
                session_id,
                self._timeout_seconds,
            )
            raise  # Re-raise to be handled by the outer exception handler in stream_response
        finally:
            await self._close_client(client)

        return "".join(pieces).strip()

    async def _collect_gemini_stream(
        self,
        *,
        client: object,
        prompt: str,
        config: object,
        pieces: list[str],
        on_token: TokenCallback,
    ) -> None:
        stream_candidate = client.aio.models.generate_content_stream(
            model=self._model_name,
            contents=prompt,
            config=config,
        )
        stream = (
            stream_candidate
            if not inspect.isawaitable(stream_candidate)
            else await stream_candidate
        )

        async for chunk in stream:
            delta = self._extract_chunk_text(chunk)
            if not delta:
                continue
            pieces.append(delta)
            await on_token(delta)

    @staticmethod
    def _extract_chunk_text(chunk: object) -> str:
        text = getattr(chunk, "text", None)
        if isinstance(text, str):
            return text
        return ""

    @staticmethod
    async def _close_client(client: object) -> None:
        aio_client = getattr(client, "aio", None)
        for candidate in (aio_client, client):
            if candidate is None:
                continue
            for closer_name in ("aclose", "close"):
                closer = getattr(candidate, closer_name, None)
                if closer is None:
                    continue
                result = closer()
                if inspect.isawaitable(result):
                    await result
                return

    @staticmethod
    def _format_history(history: list[Mapping[str, str]] | None) -> str:
        """Render a bounded sliding window of prior turns as plain text.

        Provider-agnostic: the recent learner/tutor turns are prepended to the
        user prompt so both the Groq and Gemini paths receive them without
        changing their message/contents structure. Empty history yields "".
        """
        if not history:
            return ""
        lines: list[str] = []
        for turn in history:
            text = str(turn.get("text", "")).strip()
            if not text:
                continue
            label = "Lucy" if str(turn.get("speaker", "")).strip().lower() == "tutor" else "Learner"
            lines.append(f"{label}: {text}")
        if not lines:
            return ""
        return "Recent conversation (most recent last):\n" + "\n".join(lines) + "\n\n"

    def _build_user_prompt(
        self,
        stt: STTAnalysis,
        *,
        stt_metadata: Mapping[str, Any] | None = None,
        history: list[Mapping[str, str]] | None = None,
    ) -> str:
        low_confidence_words = [
            item.word for item in stt.all_words if item.confidence < 0.6
        ]
        low_confidence_text = (
            ", ".join(low_confidence_words) if low_confidence_words else "None"
        )
        stt_note = self._build_stt_note(stt_metadata)

        return (
            f"{self._format_history(history)}"
            "Learner transcript:\n"
            f"{stt.raw_text.strip()}\n\n"
            f"{stt_note}"
            "Low-confidence tokens (likely pronunciation uncertainty):\n"
            f"{low_confidence_text}\n\n"
            f"Suspicious count: {stt.suspicious_count}\n"
            "Do not quote or mention transcription reliability notes directly unless asking for clarification.\n"
            "Provide the 2-line output format exactly."
        )

    @staticmethod
    def _build_stt_note(stt_metadata: Mapping[str, Any] | None) -> str:
        if not isinstance(stt_metadata, Mapping):
            return ""
        quality = str(stt_metadata.get("stt_quality") or "").strip().lower()
        if quality != "uncertain":
            return ""

        reasons = stt_metadata.get("uncertainty_reasons")
        reason_list: list[str] = []
        if isinstance(reasons, list):
            for item in reasons:
                if isinstance(item, str) and item.strip():
                    reason_list.append(item.strip())
        reason_text = ", ".join(reason_list) if reason_list else "uncertain_transcript"
        return (
            f"Transcription reliability: uncertain ({reason_text}). "
            "Use caution; do not mention this note to the learner.\n\n"
        )

    @staticmethod
    def _parse_output(raw_output: str, *, source: str = "gemini") -> PedagogicalReply:
        response_text = ""
        pedagogical_feedback = ""

        for raw_line in raw_output.splitlines():
            line = raw_line.strip()
            upper = line.upper()
            if upper.startswith("RESPONSE_TEXT:"):
                response_text = line.split(":", 1)[1].strip()
                continue
            if upper.startswith("PEDAGOGICAL_FEEDBACK:"):
                pedagogical_feedback = line.split(":", 1)[1].strip()

        if pedagogical_feedback.lower() in {"none", "n/a", "na"}:
            pedagogical_feedback = ""

        if response_text:
            return PedagogicalReply(
                response_text=response_text,
                pedagogical_feedback=pedagogical_feedback,
                source=source,
            )

        cleaned = raw_output.strip()
        if not cleaned:
            raise ValueError("Gemini returned empty output")

        return PedagogicalReply(
            response_text=cleaned.splitlines()[0][:220],
            pedagogical_feedback="",
            source=source,
        )

    @staticmethod
    def build_fallback_reply(stt: STTAnalysis) -> PedagogicalReply:
        if stt.suspicious_count > 0:
            return PedagogicalReply(
                response_text="Nice try! Can you repeat that once more a bit more clearly?",
                pedagogical_feedback=(
                    "I detected a few unclear words. Slow down slightly and stress keyword endings."
                ),
                source="local_fallback",
            )
        return PedagogicalReply(
            response_text="Great! Tell me a little more about that.",
            pedagogical_feedback="",
            source="local_fallback",
        )
