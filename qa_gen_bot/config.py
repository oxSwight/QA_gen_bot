import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError as exc:
        raise RuntimeError(f"Invalid integer for {name}={raw!r}") from exc


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
    return Settings(
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
    )
