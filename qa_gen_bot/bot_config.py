"""Optional config/bot.json overrides (env wins on conflict)."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, replace
from pathlib import Path

from qa_gen_bot.config import (
    GenerationProfile,
    Settings,
    _parse_generation_profile,
)
from qa_gen_bot.core.models import GenerationMode

logger = logging.getLogger(__name__)

_ALLOWED_MODES: frozenset[str] = frozenset({"quick_start", "repo"})
_ALLOWED_SEGMENTS: frozenset[str] = frozenset({"startup", "team", "enterprise-preview"})


@dataclass(frozen=True)
class BotFileConfig:
    default_generation_profile: GenerationProfile | None = None
    default_generation_mode: GenerationMode | None = None
    segment: str | None = None
    tester_max_runs: int | None = None


def _parse_mode(raw: object) -> GenerationMode | None:
    if not isinstance(raw, str):
        return None
    value = raw.strip().lower()
    if value in _ALLOWED_MODES:
        return value  # type: ignore[return-value]
    logger.error("Invalid generation_mode in bot.json: %r", raw)
    return None


def _parse_segment(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    value = raw.strip().lower()
    if value in _ALLOWED_SEGMENTS:
        return value
    logger.error("Invalid segment in bot.json: %r", raw)
    return None


def load_bot_file_config(path: Path) -> BotFileConfig:
    if not path.is_file():
        logger.info("Bot config file not found: %s (using env only)", path)
        return BotFileConfig()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Failed to read bot config {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise RuntimeError(f"bot.json root must be object, got {type(data).__name__}")

    profile_raw = data.get("default_generation_profile")
    profile: GenerationProfile | None = None
    if isinstance(profile_raw, str) and profile_raw.strip():
        profile = _parse_generation_profile(profile_raw)

    mode = _parse_mode(data.get("default_generation_mode"))
    segment = _parse_segment(data.get("segment"))

    tester_max_runs: int | None = None
    raw_runs = data.get("tester_max_runs")
    if raw_runs is not None:
        if not isinstance(raw_runs, int) or raw_runs < 1:
            raise RuntimeError(f"tester_max_runs must be positive int, got {raw_runs!r}")
        tester_max_runs = raw_runs

    cfg = BotFileConfig(
        default_generation_profile=profile,
        default_generation_mode=mode,
        segment=segment,
        tester_max_runs=tester_max_runs,
    )
    logger.info(
        "Loaded bot.json: profile=%s mode=%s segment=%s",
        cfg.default_generation_profile,
        cfg.default_generation_mode,
        cfg.segment,
    )
    return cfg


def apply_bot_file_config(
    settings: Settings,
    file_cfg: BotFileConfig,
    *,
    env_profile_set: bool,
) -> Settings:
    """Apply bot.json defaults where env did not set a value (env still wins for secrets)."""
    updates: dict = {}
    if file_cfg.default_generation_profile is not None and not env_profile_set:
        updates["generation_profile"] = file_cfg.default_generation_profile
    if file_cfg.tester_max_runs is not None and settings.tester_telegram_id is not None:
        import os

        if not os.getenv("TESTER_MAX_RUNS", "").strip():
            updates["tester_max_runs"] = file_cfg.tester_max_runs
    if file_cfg.segment is not None:
        updates["segment"] = file_cfg.segment
    if not updates:
        return settings
    merged = replace(settings, **updates)
    logger.info("Settings merged with bot.json: %s", list(updates.keys()))
    return merged


def resolve_bot_config_path() -> Path:
    import os

    return Path(os.getenv("BOT_CONFIG_PATH", "config/bot.json").strip())
