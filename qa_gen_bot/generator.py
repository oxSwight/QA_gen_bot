"""LLM-based framework generation (Anthropic) with retry and Maven feedback regen."""
from __future__ import annotations

import json
import logging

from anthropic import AsyncAnthropic

from qa_gen_bot.prompts import PHASE_TESTS_PROMPT, RETRY_PROMPT_SUFFIX, SYSTEM_PROMPT
from qa_gen_bot.quality_gate import GateResult
from qa_gen_bot.scaffold_hints import build_scaffold_hints
from qa_gen_bot.spec_parser import SpecAnalysis, build_spec_brief
from qa_gen_bot.xml_parser import merge_file_maps, parse_llm_output

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


def _build_user_message(analysis: SpecAnalysis, spec_json: str, extra: str = "") -> str:
    brief = build_spec_brief(analysis)
    parts = [
        "Сгенерируй файлы для тестового фреймворка (DTO, client, tests, schemas).",
        "pom.xml и base-классы уже в scaffold — не дублируй.",
        "",
        "=== Краткий разбор спеки ===",
        brief,
        "",
        f"Используй Java package: com.{analysis.package_hint}",
        "",
        build_scaffold_hints(analysis),
        "",
        "=== OpenAPI / Swagger JSON ===",
        spec_json,
    ]
    if extra:
        parts.extend(["", "=== Дополнительные инструкции ===", extra])
    return "\n".join(parts)


def _llm_batch_ok(files: dict[str, str]) -> bool:
    """Light check only — full gate runs after scaffold merge in pipeline."""
    if len(files) < 2:
        return False
    java_tests = [
        p
        for p in files
        if p.endswith(".java") and "/tests/" in p.replace("\\", "/")
    ]
    return len(java_tests) >= 1 or any("@Test" in c for c in files.values())


async def _call_claude(
    client: AsyncAnthropic,
    *,
    model: str,
    max_tokens: int,
    system: str,
    user_content: str,
) -> str:
    response = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=0,
        system=system,
        messages=[{"role": "user", "content": user_content}],
    )
    return response.content[0].text


async def _phase_tests_topup(
    client: AsyncAnthropic,
    *,
    model: str,
    max_tokens: int,
    analysis: SpecAnalysis,
    spec_json: str,
    existing_files: dict[str, str],
) -> dict[str, str]:
    file_list = "\n".join(f"- {p}" for p in sorted(existing_files))
    user_content = (
        f"{_build_user_message(analysis, spec_json)}\n\n"
        f"Уже сгенерированы файлы:\n{file_list}\n\n"
        "Верни только недостающие/исправленные файлы (tests, schemas, client)."
    )
    text = await _call_claude(
        client,
        model=model,
        max_tokens=max_tokens,
        system=PHASE_TESTS_PROMPT,
        user_content=user_content,
    )
    parsed = parse_llm_output(text)
    return merge_file_maps(existing_files, parsed.files)


async def generate_framework(
    client: AsyncAnthropic,
    analysis: SpecAnalysis,
    spec_content: str,
    *,
    model: str,
    max_tokens: int,
    max_retries: int,
    on_progress=None,
) -> tuple[dict[str, str], GateResult, list[str]]:
    """
    Returns (llm_files, lightweight_status, log).
    Full quality gate runs in pipeline after scaffold merge.
    """
    log: list[str] = []
    spec_json = _spec_json_for_prompt(analysis.raw_json)
    user_message = _build_user_message(analysis, spec_json)

    files: dict[str, str] = {}
    status = GateResult(passed=False, errors=["Генерация не запускалась."])

    total_attempts = max_retries + 1
    for attempt in range(1, max_retries + 2):
        log.append(f"Попытка {attempt}: запрос к модели...")
        if on_progress:
            await on_progress(
                f"Генерация (LLM) {attempt}/{total_attempts}…",
                "DTO, client, tests, schemas",
            )
        extra = RETRY_PROMPT_SUFFIX if attempt > 1 else ""

        text = await _call_claude(
            client,
            model=model,
            max_tokens=max_tokens,
            system=SYSTEM_PROMPT,
            user_content=_build_user_message(analysis, spec_json, extra=extra)
            if extra
            else user_message,
        )
        parsed = parse_llm_output(text)

        if parsed.llm_error:
            raise ValueError(f"Модель отказала: {parsed.llm_error}")

        if not parsed.files:
            status = GateResult(
                passed=False,
                errors=["Не распознан XML (<file path=...>)."],
            )
            log.append("XML не распознан.")
            continue

        files = parsed.files
        log.append(f"Получено файлов: {len(files)}")

        if _llm_batch_ok(files):
            status = GateResult(passed=True)
            log.append("LLM batch: OK (полный gate после scaffold)")
            return files, status, log

        log.append("LLM batch: мало файлов, повтор…")
        status = GateResult(
            passed=False,
            errors=["Мало файлов от модели — нужен повтор."],
        )

        if attempt == max_retries + 1:
            log.append("Доп. фаза: недостающие тесты…")
            if on_progress:
                await on_progress("Доп. фаза: тесты…", "")
            files = await _phase_tests_topup(
                client,
                model=model,
                max_tokens=max_tokens,
                analysis=analysis,
                spec_json=spec_json,
                existing_files=files,
            )
            if _llm_batch_ok(files):
                status = GateResult(passed=True)
                log.append("LLM batch после доп. фазы: OK")
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
    on_progress=None,
) -> tuple[dict[str, str], GateResult, list[str]]:
    log: list[str] = ["Перегенерация по feedback Maven…"]
    if on_progress:
        await on_progress("LLM: исправление по логу Maven", "")

    spec_json = _spec_json_for_prompt(analysis.raw_json)
    extra = (
        f"{RETRY_PROMPT_SUFFIX}\n\n"
        f"=== FEEDBACK ===\n{feedback}\n\n"
        f"Верни исправленные файлы (не трогай base/, pom.xml)."
    )
    text = await _call_claude(
        client,
        model=model,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        user_content=_build_user_message(analysis, spec_json, extra=extra),
    )
    parsed = parse_llm_output(text)
    if parsed.llm_error:
        raise ValueError(f"Модель отказала: {parsed.llm_error}")

    files = merge_file_maps(existing_files, parsed.files) if parsed.files else existing_files
    log.append(f"Файлов после merge: {len(files)}")
    ok = _llm_batch_ok(files)
    status = GateResult(passed=ok, errors=[] if ok else ["Мало файлов после regen"])
    return files, status, log
