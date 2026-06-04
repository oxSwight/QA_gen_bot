"""Entry point: QA Gen Telegram Bot."""
from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from anthropic import AsyncAnthropic

from qa_gen_bot.config import load_settings
from qa_gen_bot.handlers import register_handlers
from qa_gen_bot.maven_validator import is_docker_available

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def main() -> None:
    settings = load_settings()
    bot = Bot(token=settings.tg_token)
    dp = Dispatcher()
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    register_handlers(dp, bot, client, settings)

    docker_ok = await is_docker_available()
    if settings.maven_validation_enabled and not docker_ok:
        logger.warning(
            "Docker unavailable — Maven validation will be skipped. "
            "Start Docker Desktop for Maven validation in Docker."
        )

    logger.info(
        "QA Gen Bot started | model=%s | profile=%s | segment=%s | maven=%s | docker=%s",
        settings.model,
        settings.generation_profile,
        settings.segment or "-",
        "on" if settings.maven_validation_enabled else "off",
        "ok" if docker_ok else "missing",
    )
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
