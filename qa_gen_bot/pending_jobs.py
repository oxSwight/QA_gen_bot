"""In-memory pending OpenAPI jobs awaiting base URL (per Telegram user)."""
from __future__ import annotations

from dataclasses import dataclass

from qa_gen_bot.spec_parser import SpecAnalysis


@dataclass
class PendingSpecJob:
    spec_content: str
    analysis: SpecAnalysis
    file_name: str


_pending: dict[int, PendingSpecJob] = {}


def set_pending(user_id: int, job: PendingSpecJob) -> None:
    _pending[user_id] = job


def pop_pending(user_id: int) -> PendingSpecJob | None:
    return _pending.pop(user_id, None)


def get_pending(user_id: int) -> PendingSpecJob | None:
    return _pending.get(user_id)


def clear_pending(user_id: int) -> None:
    _pending.pop(user_id, None)
