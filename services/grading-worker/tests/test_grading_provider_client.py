from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.grading_provider_client import GroqClient
from src.llm_grader import LLMGraderError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_JSON_TEXT = (
    '{"fluency_score": 8.0, "grammar_score": 7.5, "vocab_score": 7.0,'
    ' "summary": "Good effort.", "corrections": []}'
)

_VALID_RESPONSE_BODY: dict[str, Any] = {
    "choices": [{"message": {"content": _VALID_JSON_TEXT}}]
}


def _mock_response(status_code: int = 200, json_data: Any = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else _VALID_RESPONSE_BODY
    return resp


def _patch_http(resp: MagicMock):
    """Patch httpx.AsyncClient so .post() returns the given mock response."""
    mock_http = AsyncMock()
    mock_http.post = AsyncMock(return_value=resp)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_http)
    cm.__aexit__ = AsyncMock(return_value=False)
    return patch("src.grading_provider_client.httpx.AsyncClient", return_value=cm)


def _patch_http_raise(exc: Exception):
    """Patch httpx.AsyncClient so .post() raises the given exception."""
    mock_http = AsyncMock()
    mock_http.post = AsyncMock(side_effect=exc)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_http)
    cm.__aexit__ = AsyncMock(return_value=False)
    return patch("src.grading_provider_client.httpx.AsyncClient", return_value=cm)


def _valid_client() -> GroqClient:
    return GroqClient(api_key="test-key", model="llama-3.1-8b-instant", timeout_seconds=20.0)


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------


def test_init_blank_api_key_raises() -> None:
    with pytest.raises(LLMGraderError, match="api_key"):
        GroqClient(api_key="", model="llama-3.1-8b-instant", timeout_seconds=20.0)


def test_init_whitespace_api_key_raises() -> None:
    with pytest.raises(LLMGraderError, match="api_key"):
        GroqClient(api_key="   ", model="llama-3.1-8b-instant", timeout_seconds=20.0)


def test_init_blank_model_raises() -> None:
    with pytest.raises(LLMGraderError, match="model"):
        GroqClient(api_key="test-key", model="", timeout_seconds=20.0)


def test_init_zero_timeout_raises() -> None:
    with pytest.raises(LLMGraderError, match="timeout_seconds"):
        GroqClient(api_key="test-key", model="llama-3.1-8b-instant", timeout_seconds=0.0)


def test_init_negative_timeout_raises() -> None:
    with pytest.raises(LLMGraderError, match="timeout_seconds"):
        GroqClient(api_key="test-key", model="llama-3.1-8b-instant", timeout_seconds=-1.0)


# ---------------------------------------------------------------------------
# grade() — success paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_grade_success_returns_content() -> None:
    resp = _mock_response(200, {"choices": [{"message": {"content": _VALID_JSON_TEXT}}]})
    with _patch_http(resp):
        result = await _valid_client().grade("rate this session")
    assert result == _VALID_JSON_TEXT


@pytest.mark.asyncio
async def test_grade_strips_surrounding_whitespace() -> None:
    resp = _mock_response(200, {"choices": [{"message": {"content": "  {}\n  "}}]})
    with _patch_http(resp):
        result = await _valid_client().grade("prompt")
    assert result == "{}"


# ---------------------------------------------------------------------------
# grade() — timeout and transport errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_grade_timeout_raises_llm_grader_error() -> None:
    with _patch_http_raise(httpx.TimeoutException("timed out")):
        with pytest.raises(LLMGraderError, match="timeout"):
            await _valid_client().grade("prompt")


@pytest.mark.asyncio
async def test_grade_http_error_raises_llm_grader_error() -> None:
    with _patch_http_raise(httpx.HTTPError("network failure")):
        with pytest.raises(LLMGraderError, match="http_error"):
            await _valid_client().grade("prompt")


# ---------------------------------------------------------------------------
# grade() — non-2xx HTTP status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_grade_500_raises_llm_grader_error() -> None:
    with _patch_http(_mock_response(500)):
        with pytest.raises(LLMGraderError, match="500"):
            await _valid_client().grade("prompt")


@pytest.mark.asyncio
async def test_grade_429_raises_llm_grader_error() -> None:
    with _patch_http(_mock_response(429)):
        with pytest.raises(LLMGraderError, match="429"):
            await _valid_client().grade("prompt")


# ---------------------------------------------------------------------------
# grade() — malformed response structure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_grade_missing_choices_key_raises() -> None:
    resp = _mock_response(200, {"error": "unexpected"})
    with _patch_http(resp):
        with pytest.raises(LLMGraderError, match="choices"):
            await _valid_client().grade("prompt")


@pytest.mark.asyncio
async def test_grade_empty_choices_list_raises() -> None:
    resp = _mock_response(200, {"choices": []})
    with _patch_http(resp):
        with pytest.raises(LLMGraderError, match="empty_choices"):
            await _valid_client().grade("prompt")


@pytest.mark.asyncio
async def test_grade_missing_message_raises() -> None:
    resp = _mock_response(200, {"choices": [{}]})
    with _patch_http(resp):
        with pytest.raises(LLMGraderError, match="parse_error"):
            await _valid_client().grade("prompt")


@pytest.mark.asyncio
async def test_grade_empty_content_raises() -> None:
    resp = _mock_response(200, {"choices": [{"message": {"content": "   "}}]})
    with _patch_http(resp):
        with pytest.raises(LLMGraderError, match="empty_content"):
            await _valid_client().grade("prompt")


# ---------------------------------------------------------------------------
# Security: no sensitive data in exceptions or logs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exception_does_not_contain_api_key() -> None:
    secret = "MY_SECRET_GROQ_KEY_ABCDEF123"
    client = GroqClient(api_key=secret, model="llama-3.1-8b-instant", timeout_seconds=20.0)
    with _patch_http(_mock_response(500)):
        with pytest.raises(LLMGraderError) as exc_info:
            await client.grade("some prompt")
    assert secret not in str(exc_info.value)


@pytest.mark.asyncio
async def test_logs_do_not_contain_prompt_or_api_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_key = "MY_SECRET_GROQ_KEY_ABCDEF456"
    secret_prompt = "Confidential student transcript xyz987"
    client = GroqClient(api_key=secret_key, model="llama-3.1-8b-instant", timeout_seconds=20.0)
    with _patch_http(_mock_response(500)):
        with caplog.at_level(logging.DEBUG):
            with pytest.raises(LLMGraderError):
                await client.grade(secret_prompt)
    for record in caplog.records:
        assert secret_key not in record.message
        assert secret_prompt not in record.message
