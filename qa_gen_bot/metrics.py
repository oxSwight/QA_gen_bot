"""Structured run summaries for logs / future observability."""
from __future__ import annotations

import json
import logging

from qa_gen_bot.config import GenerationProfile
from qa_gen_bot.core.models import GenerationMode

logger = logging.getLogger(__name__)


def log_run_summary(
    *,
    mode: GenerationMode,
    profile: GenerationProfile,
    segment: str | None,
    delivery_ready: bool,
    elapsed_sec: int,
    user_id: int | None = None,
) -> None:
    payload = {
        "event": "generation_run",
        "mode": mode,
        "profile": profile,
        "segment": segment or "unknown",
        "delivery_ready": delivery_ready,
        "elapsed_sec": elapsed_sec,
    }
    if user_id is not None:
        payload["user_id"] = user_id
    logger.info("run_summary %s", json.dumps(payload, ensure_ascii=False))
