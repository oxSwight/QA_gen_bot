"""Remote generation API client (timeout and retries)."""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from anthropic import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncAnthropic,
    RateLimitError,
)

if TYPE_CHECKING:
    from anthropic.types import Message

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 529})


class GenerationApiError(RuntimeError):
    """Failure after retries; safe to show in Telegram."""

    def __init__(self, message: str, *, cause: BaseException | None = None) -> None:
        super().__init__(message)
        self.cause = cause


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, (APITimeoutError, APIConnectionError, RateLimitError, ConnectionError)):
        return True
    if isinstance(exc, APIStatusError) and exc.status_code in _RETRYABLE_STATUS_CODES:
        return True
    if isinstance(exc, asyncio.TimeoutError):
        return True
    return False


def _backoff_seconds(attempt: int) -> float:
    return min(60.0, 2.0 ** attempt)


async def call_generation_messages(
    client: AsyncAnthropic,
    *,
    model: str,
    max_tokens: int,
    system: str,
    user_content: str,
    timeout_sec: float,
    max_api_retries: int,
) -> str:
    """
    Call Messages API with bounded wait and retries on transient failures.

    Raises GenerationApiError with a safe message for end users.
    """
    if not model.strip():
        raise GenerationApiError("Не задан ANTHROPIC_MODEL.")
    if max_tokens < 1:
        raise GenerationApiError(f"Некорректный ANTHROPIC_MAX_TOKENS={max_tokens}.")
    if timeout_sec <= 0:
        raise GenerationApiError(f"Некорректный ANTHROPIC_TIMEOUT_SEC={timeout_sec}.")
    if max_api_retries < 0:
        raise GenerationApiError(f"Некорректный ANTHROPIC_API_MAX_RETRIES={max_api_retries}.")

    last_exc: BaseException | None = None
    attempts = max_api_retries + 1

    for attempt in range(1, attempts + 1):
        try:
            logger.info(
                "Generation API request model=%s attempt=%s/%s timeout=%ss",
                model,
                attempt,
                attempts,
                timeout_sec,
            )
            coro = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=0,
                system=system,
                messages=[{"role": "user", "content": user_content}],
            )
            response: Message = await asyncio.wait_for(coro, timeout=timeout_sec)
            if not response.content:
                raise GenerationApiError("Пустой ответ сервиса генерации.")
            block = response.content[0]
            text = getattr(block, "text", None)
            if not text:
                raise GenerationApiError("Ответ без текстового блока.")
            return text

        except asyncio.TimeoutError as exc:
            last_exc = exc
            logger.error(
                "Generation API timeout after %ss (attempt %s/%s)",
                timeout_sec,
                attempt,
                attempts,
            )
        except Exception as exc:
            last_exc = exc
            if _is_retryable(exc):
                logger.warning(
                    "Generation API transient error (attempt %s/%s): %s",
                    attempt,
                    attempts,
                    exc,
                )
            else:
                logger.error("Generation API non-retryable error: %s", exc, exc_info=True)
                raise GenerationApiError(
                    f"Ошибка сервиса генерации: {exc}",
                    cause=exc,
                ) from exc

        if attempt < attempts:
            delay = _backoff_seconds(attempt)
            logger.info("Generation API retry in %.1fs", delay)
            await asyncio.sleep(delay)

    raise GenerationApiError(
        "Сервис генерации недоступен (таймаут или лимит). Попробуйте позже.",
        cause=last_exc,
    )
