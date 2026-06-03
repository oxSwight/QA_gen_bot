"""Telegram UI helpers for generation mode (Quick Start vs Repo)."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from qa_gen_bot.core.models import GenerationMode

CALLBACK_PREFIX = "genmode:"

MODE_QUICK_START: GenerationMode = "quick_start"
MODE_REPO: GenerationMode = "repo"


def mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="ZIP — быстрый старт (Mode A)",
                    callback_data=f"{CALLBACK_PREFIX}{MODE_QUICK_START}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Repo — openapi-generator (Mode B)",
                    callback_data=f"{CALLBACK_PREFIX}{MODE_REPO}",
                ),
            ],
        ]
    )


def mode_label(mode: GenerationMode) -> str:
    if mode == MODE_REPO:
        return "repo — client в target/generated-sources"
    return "quick_start — готовый ZIP-проект"


def parse_mode_from_callback(data: str) -> GenerationMode | None:
    if not data.startswith(CALLBACK_PREFIX):
        return None
    value = data[len(CALLBACK_PREFIX) :]
    if value in (MODE_QUICK_START, MODE_REPO):
        return value  # type: ignore[return-value]
    return None


def parse_mode_from_text(text: str) -> GenerationMode | None:
    normalized = text.strip().lower()
    if normalized in {"zip", "a", "1", "quick", "quick_start", "старт"}:
        return MODE_QUICK_START
    if normalized in {"repo", "b", "2", "codegen", "generator", "target"}:
        return MODE_REPO
    return None
