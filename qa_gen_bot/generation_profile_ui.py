"""Telegram UI helpers for GENERATION_PROFILE selection."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from qa_gen_bot.config import (
    GenerationProfile,
    PROFILE_CONTRACT_MOCKS,
    PROFILE_INTEGRATION_ONLY,
)

CALLBACK_PREFIX = "genprof:"


def profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Только API (без WireMock)",
                    callback_data=f"{CALLBACK_PREFIX}{PROFILE_INTEGRATION_ONLY}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="С моками (WireMock + schema)",
                    callback_data=f"{CALLBACK_PREFIX}{PROFILE_CONTRACT_MOCKS}",
                ),
            ],
        ]
    )


def profile_label(profile: GenerationProfile) -> str:
    if profile == PROFILE_INTEGRATION_ONLY:
        return "integration-only — живой API, без моков"
    return "contract-mocks — WireMock + JSON Schema"


def parse_profile_from_text(text: str) -> GenerationProfile | None:
    """Optional text aliases (buttons are primary)."""
    normalized = text.strip().lower()
    integration_aliases = {
        "1",
        "live",
        "/live",
        "integration",
        "integration-only",
        "интеграция",
        "без моков",
        "без моков",
        "api",
    }
    contract_aliases = {
        "2",
        "mocks",
        "/mocks",
        "mock",
        "wiremock",
        "contract",
        "contract-mocks",
        "моки",
        "с моками",
    }
    if normalized in integration_aliases:
        return PROFILE_INTEGRATION_ONLY
    if normalized in contract_aliases:
        return PROFILE_CONTRACT_MOCKS
    return None


def parse_profile_from_callback(data: str) -> GenerationProfile | None:
    if not data.startswith(CALLBACK_PREFIX):
        return None
    value = data[len(CALLBACK_PREFIX) :]
    if value in (PROFILE_INTEGRATION_ONLY, PROFILE_CONTRACT_MOCKS):
        return value  # type: ignore[return-value]
    return None
