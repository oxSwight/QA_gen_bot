"""In-memory pending OpenAPI jobs (per Telegram user)."""
from __future__ import annotations

from dataclasses import dataclass

from qa_gen_bot.config import GenerationProfile
from qa_gen_bot.core.models import GenerationMode
from qa_gen_bot.spec_parser import SpecAnalysis


@dataclass
class PendingSpecJob:
    spec_content: str
    analysis: SpecAnalysis
    file_name: str
    generation_profile: GenerationProfile | None = None
    generation_mode: GenerationMode | None = None

    @property
    def awaiting_profile(self) -> bool:
        return self.generation_profile is None

    @property
    def awaiting_mode(self) -> bool:
        return self.generation_profile is not None and self.generation_mode is None

    @property
    def ready_for_url(self) -> bool:
        return (
            self.generation_profile is not None
            and self.generation_mode is not None
        )


_pending: dict[int, PendingSpecJob] = {}


def set_pending(user_id: int, job: PendingSpecJob) -> None:
    _pending[user_id] = job


def update_pending_profile(user_id: int, profile: GenerationProfile) -> PendingSpecJob | None:
    job = _pending.get(user_id)
    if job is None:
        return None
    job.generation_profile = profile
    return job


def update_pending_mode(user_id: int, mode: GenerationMode) -> PendingSpecJob | None:
    job = _pending.get(user_id)
    if job is None:
        return None
    job.generation_mode = mode
    return job


def pop_pending(user_id: int) -> PendingSpecJob | None:
    return _pending.pop(user_id, None)


def get_pending(user_id: int) -> PendingSpecJob | None:
    return _pending.get(user_id)


def clear_pending(user_id: int) -> None:
    _pending.pop(user_id, None)
