"""Application settings loaded from environment variables."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

logger = logging.getLogger(__name__)

GenerationProfile = Literal["integration-only", "contract-mocks"]

PROFILE_INTEGRATION_ONLY: Final[GenerationProfile] = "integration-only"
PROFILE_CONTRACT_MOCKS: Final[GenerationProfile] = "contract-mocks"

DEFAULT_GENERATION_PROFILE: Final[GenerationProfile] = PROFILE_CONTRACT_MOCKS

_ALLOWED_PROFILES: Final[frozenset[str]] = frozenset(
    {PROFILE_INTEGRATION_ONLY, PROFILE_CONTRACT_MOCKS}
)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw.strip())
    except ValueError as exc:
        raise RuntimeError(f"Invalid float for {name}={raw!r}") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be positive, got {value!r}")
    return value


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError as exc:
        raise RuntimeError(f"Invalid integer for {name}={raw!r}") from exc


def _parse_generation_profile(raw: str | None) -> GenerationProfile:
    """
    Resolve GENERATION_PROFILE from env.

    Missing or blank -> DEFAULT_GENERATION_PROFILE (contract-mocks, backward compatible).
    Unknown value -> fail-fast RuntimeError.
    """
    if raw is None or not raw.strip():
        profile: GenerationProfile = DEFAULT_GENERATION_PROFILE
        logger.info(
            "GENERATION_PROFILE unset; using default %r",
            profile,
        )
        return profile

    normalized = raw.strip().lower()
    if normalized not in _ALLOWED_PROFILES:
        allowed = ", ".join(sorted(_ALLOWED_PROFILES))
        logger.error(
            "Invalid GENERATION_PROFILE=%r; allowed: %s",
            raw,
            allowed,
        )
        raise RuntimeError(
            f"Invalid GENERATION_PROFILE={raw!r}. "
            f"Allowed values: {allowed}."
        )

    if normalized == PROFILE_INTEGRATION_ONLY:
        profile = PROFILE_INTEGRATION_ONLY
    else:
        profile = PROFILE_CONTRACT_MOCKS
    logger.info("GENERATION_PROFILE=%r", profile)
    return profile


@dataclass(frozen=True)
class Settings:
    tg_token: str
    anthropic_api_key: str
    model: str = "claude-sonnet-4-6"
    max_tokens: int = 16_384
    max_retries: int = 1
    max_spec_chars: int = 120_000
    maven_validation_enabled: bool = True
    maven_validation_strict: bool = True
    maven_docker_image: str = "maven:3.9-eclipse-temurin-17"
    maven_timeout_sec: int = 300
    maven_max_retries: int = 1
    use_scaffold: bool = True
    generation_profile: GenerationProfile = DEFAULT_GENERATION_PROFILE
    tester_telegram_id: int | None = None
    tester_max_runs: int = 5
    usage_store_path: Path = Path("data/usage.json")
    anthropic_timeout_sec: float = 600.0
    anthropic_api_max_retries: int = 2
    segment: str | None = None

    def limits_enabled_for(self, user_id: int) -> bool:
        return (
            self.tester_telegram_id is not None
            and user_id == self.tester_telegram_id
        )

    @property
    def uses_wiremock(self) -> bool:
        """True when scaffold/prompts should include WireMock (contract-mocks)."""
        return self.generation_profile == PROFILE_CONTRACT_MOCKS

    @property
    def is_integration_only(self) -> bool:
        """True when tests target live base.url only (no WireMock scaffold)."""
        return self.generation_profile == PROFILE_INTEGRATION_ONLY


def _env_optional_int(name: str) -> int | None:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return None
    try:
        return int(str(raw).strip())
    except ValueError as exc:
        raise RuntimeError(f"Invalid integer for {name}={raw!r}") from exc


def load_settings(
    *,
    require_telegram: bool = True,
    require_anthropic: bool = True,
) -> Settings:
    tg_token = os.getenv("TG_TOKEN", "").strip()
    anthropic_api_key = os.getenv("ANTHROPIC_KEY", "").strip()
    if require_telegram and not tg_token:
        raise RuntimeError("Set TG_TOKEN in .env (see .env.example).")
    if require_anthropic and not anthropic_api_key:
        raise RuntimeError("Set ANTHROPIC_KEY in .env (see .env.example).")
    if not tg_token:
        tg_token = "local-cli"
    if not anthropic_api_key:
        anthropic_api_key = "local-cli"

    env_profile_raw = os.getenv("GENERATION_PROFILE")
    generation_profile = _parse_generation_profile(env_profile_raw)

    settings = Settings(
        tg_token=tg_token,
        anthropic_api_key=anthropic_api_key,
        model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6").strip(),
        max_tokens=_env_int("ANTHROPIC_MAX_TOKENS", 16384),
        max_retries=_env_int("GENERATION_MAX_RETRIES", 1),
        max_spec_chars=_env_int("MAX_SPEC_CHARS", 120000),
        maven_validation_enabled=_env_bool("MAVEN_VALIDATION_ENABLED", True),
        maven_validation_strict=_env_bool("MAVEN_VALIDATION_STRICT", True),
        maven_docker_image=os.getenv(
            "MAVEN_DOCKER_IMAGE", "maven:3.9-eclipse-temurin-17"
        ).strip(),
        maven_timeout_sec=_env_int("MAVEN_TIMEOUT_SEC", 300),
        maven_max_retries=_env_int("MAVEN_MAX_RETRIES", 1),
        use_scaffold=_env_bool("USE_SCAFFOLD", True),
        generation_profile=generation_profile,
        tester_telegram_id=_env_optional_int("TESTER_TELEGRAM_ID"),
        tester_max_runs=_env_int("TESTER_MAX_RUNS", 5),
        usage_store_path=Path(
            os.getenv("USAGE_STORE_PATH", "data/usage.json").strip()
        ),
        anthropic_timeout_sec=_env_float("ANTHROPIC_TIMEOUT_SEC", 600.0),
        anthropic_api_max_retries=_env_int("ANTHROPIC_API_MAX_RETRIES", 2),
    )
    from qa_gen_bot.bot_config import (
        apply_bot_file_config,
        load_bot_file_config,
        resolve_bot_config_path,
    )

    file_cfg = load_bot_file_config(resolve_bot_config_path())
    settings = apply_bot_file_config(settings, file_cfg, env_profile_set=bool(env_profile_raw and env_profile_raw.strip()))

    logger.info(
        "Settings loaded: profile=%s uses_wiremock=%s segment=%s",
        settings.generation_profile,
        settings.uses_wiremock,
        file_cfg.segment,
    )
    return settings
