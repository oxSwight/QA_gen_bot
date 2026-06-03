"""Generation API client retry/timeout helpers."""
import asyncio
from unittest import mock

import pytest

from qa_gen_bot.generation_api import GenerationApiError, call_generation_messages


def test_fail_fast_invalid_timeout() -> None:
    async def _run() -> None:
        client = mock.AsyncMock()
        with pytest.raises(GenerationApiError, match="ANTHROPIC_TIMEOUT_SEC"):
            await call_generation_messages(
                client,
                model="m",
                max_tokens=100,
                system="s",
                user_content="u",
                timeout_sec=0,
                max_api_retries=1,
            )

    asyncio.run(_run())


def test_retries_on_transient_error() -> None:
    async def _run() -> None:
        client = mock.AsyncMock()
        client.messages.create = mock.AsyncMock(
            side_effect=[
                ConnectionError("reset"),
                mock.Mock(content=[mock.Mock(text="ok")]),
            ]
        )

        text = await call_generation_messages(
            client,
            model="claude-test",
            max_tokens=100,
            system="sys",
            user_content="go",
            timeout_sec=30.0,
            max_api_retries=2,
        )
        assert text == "ok"
        assert client.messages.create.await_count == 2

    asyncio.run(_run())
