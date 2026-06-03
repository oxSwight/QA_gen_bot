"""Remote API framework generation with retry and Maven feedback regen."""
from __future__ import annotations

import json
import logging

from anthropic import AsyncAnthropic

from qa_gen_bot.prompts import (
    get_phase_tests_prompt,
    get_retry_prompt_suffix,
    get_system_prompt,
)
from qa_gen_bot.quality_gate import GateResult
from qa_gen_bot.scaffold_hints import build_repo_codegen_hints, build_scaffold_hints
from qa_gen_bot.spec_parser import SpecAnalysis, build_spec_brief
from qa_gen_bot.generation_api import call_generation_messages
from qa_gen_bot.xml_parser import merge_file_maps, parse_generation_output

logger = logging.getLogger(__name__)

_SPEC_JSON_MAX_CHARS = 50_000
_SCHEMA_KEEP = 30


def _spec_json_for_prompt(raw_json: dict) -> str:
    """Trim components.schemas when full spec JSON exceeds token budget."""
    dumped = json.dumps(raw_json, ensure_ascii=False, indent=2)
    if len(dumped) <= _SPEC_JSON_MAX_CHARS:
        return dumped

    slim: dict = dict(raw_json)
    components = slim.get("components")
    if isinstance(components, dict):
        components = dict(components)
        schemas = components.get("schemas")
        if isinstance(schemas, dict) and len(schemas) > _SCHEMA_KEEP:
            keys = list(schemas.keys())[:_SCHEMA_KEEP]
            omitted = len(schemas) - _SCHEMA_KEEP
            components["schemas"] = {k: schemas[k] for k in keys}
            components["_note"] = (
                f"Truncated for prompt: showing {_SCHEMA_KEEP} of "
                f"{len(schemas)} schemas ({omitted} omitted)."
            )
        slim["components"] = components

    result = json.dumps(slim, ensure_ascii=False, indent=2)
    if len(result) > _SPEC_JSON_MAX_CHARS:
        logger.warning(
            "Spec JSON still %s chars after schema trim (limit %s)",
            len(result),
            _SPEC_JSON_MAX_CHARS,
        )
    else:
        logger.info(
            "Spec JSON trimmed: %s -> %s chars (schemas capped at %s)",
            len(dumped),
            len(result),
            _SCHEMA_KEEP,
        )
    return result


def _build_user_message(
    analysis: SpecAnalysis,
    spec_json: str,
    extra: str = "",
    *,
    uses_wiremock: bool = True,
    repo_mode: bool = False,
) -> str:
    brief = build_spec_brief(analysis)
    if repo_mode:
        intro = (
            "Сгенерируй только тесты (src/test/java) и опционально schemas. "
            "API/DTO даст openapi-generator — не создавай client/dto/pom."
        )
        hints = build_repo_codegen_hints(analysis, uses_wiremock=uses_wiremock)
    else:
        intro = (
            "Сгенерируй файлы для тестового фреймворка (DTO, client, tests, schemas). "
            "pom.xml и base-классы уже в scaffold — не дублируй."
        )
        hints = build_scaffold_hints(analysis, uses_wiremock=uses_wiremock)
    parts = [
        intro,
        "",
        "=== Краткий разбор спеки ===",
        brief,
        "",
        f"Используй Java package: com.{analysis.package_hint}",
        "",
        hints,
        "",
        "=== OpenAPI / Swagger JSON ===",
        spec_json,
    ]
    if extra:
        parts.extend(["", "=== Дополнительные инструкции ===", extra])
    return "\n".join(parts)


def _output_batch_ok(
    files: dict[str, str],
    *,
    uses_wiremock: bool = True,
    repo_mode: bool = False,
) -> bool:
    """Light check only — full gate runs after scaffold merge in pipeline."""
    if repo_mode:
        from qa_gen_bot.codegen.repo_output_filter import filter_repo_generated_files

        files = filter_repo_generated_files(files)
    if len(files) < 1:
        return False
    java_tests = [
        p
        for p, content in files.items()
        if p.endswith(".java") and "/tests/" in p.replace("\\", "/")
    ]
    if not java_tests and not any("@Test" in c for c in files.values()):
        return False
    if uses_wiremock:
        return len(java_tests) >= 1
    return any(
        p.replace("\\", "/").endswith("IntegrationTest.java") for p in java_tests
    ) or any("@Test" in files.get(p, "") for p in java_tests)


async def _call_claude(
    client: AsyncAnthropic,
    *,
    model: str,
    max_tokens: int,
    system: str,
    user_content: str,
    timeout_sec: float,
    api_max_retries: int,
) -> str:
    return await call_generation_messages(
        client,
        model=model,
        max_tokens=max_tokens,
        system=system,
        user_content=user_content,
        timeout_sec=timeout_sec,
        max_api_retries=api_max_retries,
    )


async def _phase_tests_topup(
    client: AsyncAnthropic,
    *,
    model: str,
    max_tokens: int,
    analysis: SpecAnalysis,
    spec_json: str,
    existing_files: dict[str, str],
    uses_wiremock: bool,
    repo_mode: bool,
    anthropic_timeout_sec: float,
    anthropic_api_max_retries: int,
) -> dict[str, str]:
    file_list = "\n".join(f"- {p}" for p in sorted(existing_files))
    user_content = (
        f"{_build_user_message(analysis, spec_json, uses_wiremock=uses_wiremock, repo_mode=repo_mode)}\n\n"
        f"Уже сгенерированы файлы:\n{file_list}\n\n"
        "Верни только недостающие/исправленные файлы (tests, schemas)."
    )
    text = await _call_claude(
        client,
        model=model,
        max_tokens=max_tokens,
        system=get_phase_tests_prompt(uses_wiremock=uses_wiremock, repo_mode=repo_mode),
        user_content=user_content,
        timeout_sec=anthropic_timeout_sec,
        api_max_retries=anthropic_api_max_retries,
    )
    parsed = parse_generation_output(text)
    return merge_file_maps(existing_files, parsed.files)


async def generate_framework(
    client: AsyncAnthropic,
    analysis: SpecAnalysis,
    spec_content: str,
    *,
    model: str,
    max_tokens: int,
    max_retries: int,
    uses_wiremock: bool = True,
    repo_mode: bool = False,
    anthropic_timeout_sec: float = 600.0,
    anthropic_api_max_retries: int = 2,
    on_progress=None,
) -> tuple[dict[str, str], GateResult, list[str]]:
    """
    Returns (generated_files, lightweight_status, log).
    Full quality gate runs in pipeline after scaffold merge.
    """
    log: list[str] = []
    spec_json = _spec_json_for_prompt(analysis.raw_json)
    user_message = _build_user_message(
        analysis, spec_json, uses_wiremock=uses_wiremock, repo_mode=repo_mode
    )
    system_prompt = get_system_prompt(uses_wiremock=uses_wiremock, repo_mode=repo_mode)

    files: dict[str, str] = {}
    status = GateResult(passed=False, errors=["Запрос к сервису не выполнялся."])

    total_attempts = max_retries + 1
    for attempt in range(1, max_retries + 2):
        log.append(f"Попытка {attempt}: запрос к API…")
        if on_progress:
            await on_progress("Сборка", f"{attempt}/{total_attempts}")
        extra = (
            get_retry_prompt_suffix(uses_wiremock=uses_wiremock, repo_mode=repo_mode)
            if attempt > 1
            else ""
        )

        text = await _call_claude(
            client,
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            user_content=_build_user_message(
                analysis,
                spec_json,
                extra=extra,
                uses_wiremock=uses_wiremock,
                repo_mode=repo_mode,
            )
            if extra
            else user_message,
            timeout_sec=anthropic_timeout_sec,
            api_max_retries=anthropic_api_max_retries,
        )
        parsed = parse_generation_output(text)

        if parsed.refusal_text:
            raise ValueError(f"Сервис отклонил запрос: {parsed.refusal_text}")

        if not parsed.files:
            status = GateResult(
                passed=False,
                errors=["Не распознан XML (<file path=...>)."],
            )
            log.append("XML не распознан.")
            continue

        files = parsed.files
        log.append(f"Получено файлов: {len(files)}")

        if _output_batch_ok(files, uses_wiremock=uses_wiremock, repo_mode=repo_mode):
            status = GateResult(passed=True)
            log.append("Пакет файлов: OK (полный gate после scaffold)")
            if repo_mode:
                from qa_gen_bot.codegen.repo_output_filter import filter_repo_generated_files

                files = filter_repo_generated_files(files)
            return files, status, log

        log.append("Пакет файлов: мало файлов, повтор…")
        status = GateResult(
            passed=False,
            errors=["Недостаточно файлов в ответе — нужен повтор."],
        )

        if attempt == max_retries + 1:
            log.append("Доп. фаза: недостающие тесты…")
            if on_progress:
                await on_progress("Сборка", "доп. тесты")
            files = await _phase_tests_topup(
                client,
                model=model,
                max_tokens=max_tokens,
                analysis=analysis,
                spec_json=spec_json,
                existing_files=files,
                uses_wiremock=uses_wiremock,
                repo_mode=repo_mode,
                anthropic_timeout_sec=anthropic_timeout_sec,
                anthropic_api_max_retries=anthropic_api_max_retries,
            )
            if _output_batch_ok(files, uses_wiremock=uses_wiremock, repo_mode=repo_mode):
                status = GateResult(passed=True)
                log.append("Пакет файлов после доп. фазы: OK")
                if repo_mode:
                    from qa_gen_bot.codegen.repo_output_filter import filter_repo_generated_files

                    files = filter_repo_generated_files(files)
                return files, status, log

    return files, status, log


async def regenerate_with_feedback(
    client: AsyncAnthropic,
    analysis: SpecAnalysis,
    spec_content: str,
    *,
    existing_files: dict[str, str],
    feedback: str,
    model: str,
    max_tokens: int,
    uses_wiremock: bool = True,
    repo_mode: bool = False,
    anthropic_timeout_sec: float = 600.0,
    anthropic_api_max_retries: int = 2,
    on_progress=None,
) -> tuple[dict[str, str], GateResult, list[str]]:
    log: list[str] = ["Перегенерация по feedback Maven…"]
    if on_progress:
        await on_progress("Исправление", "")

    spec_json = _spec_json_for_prompt(analysis.raw_json)
    extra = (
        f"{get_retry_prompt_suffix(uses_wiremock=uses_wiremock, repo_mode=repo_mode)}\n\n"
        f"=== FEEDBACK ===\n{feedback}\n\n"
        f"Верни исправленные файлы (не трогай base/, pom.xml)."
    )
    text = await _call_claude(
        client,
        model=model,
        max_tokens=max_tokens,
        system=get_system_prompt(uses_wiremock=uses_wiremock, repo_mode=repo_mode),
        user_content=_build_user_message(
            analysis,
            spec_json,
            extra=extra,
            uses_wiremock=uses_wiremock,
            repo_mode=repo_mode,
        ),
        timeout_sec=anthropic_timeout_sec,
        api_max_retries=anthropic_api_max_retries,
    )
    parsed = parse_generation_output(text)
    if parsed.refusal_text:
        raise ValueError(f"Сервис отклонил запрос: {parsed.refusal_text}")

    if repo_mode and parsed.files:
        from qa_gen_bot.codegen.repo_output_filter import filter_repo_generated_files

        patch = filter_repo_generated_files(parsed.files)
        files = merge_file_maps(existing_files, patch)
    else:
        files = merge_file_maps(existing_files, parsed.files) if parsed.files else existing_files
    log.append(f"Файлов после merge: {len(files)}")
    ok = _output_batch_ok(files, uses_wiremock=uses_wiremock, repo_mode=repo_mode)
    status = GateResult(passed=ok, errors=[] if ok else ["Мало файлов после regen"])
    return files, status, log
