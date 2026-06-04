"""End-to-end: scaffold + API output → fixes → gate → Docker Maven → retry."""
from __future__ import annotations

import logging

from anthropic import AsyncAnthropic

from qa_gen_bot.config import Settings
from qa_gen_bot.core.models import GenerationResult
from qa_gen_bot.generator import (
    _output_batch_ok,
    generate_framework,
    regenerate_with_feedback,
)
from qa_gen_bot.maven_validator import MavenValidationResult, validate_maven_project
from qa_gen_bot.quality_gate import GateResult, validate_generated_project
from qa_gen_bot.scaffold import build_scaffold, merge_with_scaffold, strip_generated_protected
from qa_gen_bot.spec_parser import SpecAnalysis
from qa_gen_bot.metrics import log_run_summary
from qa_gen_bot.status_reporter import StatusReporter
from qa_gen_bot.structure_fixer import (
    apply_all_structure_fixes,
    autofix_from_maven_log,
)

logger = logging.getLogger(__name__)

# Backward-compatible alias for handlers, CLI, tests
PipelineResult = GenerationResult


def _finalize_files(
    generated_files: dict[str, str],
    scaffold: dict[str, str],
    use_scaffold: bool,
    base_package: str,
    log: list[str],
    *,
    uses_wiremock: bool,
) -> tuple[dict[str, str], GateResult]:
    files = generated_files
    if use_scaffold:
        stripped = strip_generated_protected(
            generated_files, uses_wiremock=uses_wiremock
        )
        files = merge_with_scaffold(
            stripped, scaffold, uses_wiremock=uses_wiremock
        )
        log.append(f"Scaffold merge: {len(scaffold)} protected + {len(stripped)} доп.")

    fix = apply_all_structure_fixes(
        files,
        base_package,
        scaffold if use_scaffold else None,
        uses_wiremock=uses_wiremock,
    )
    if fix.applied:
        log.extend(f"Auto-fix: {a}" for a in fix.applied)
    files = fix.files

    gate = validate_generated_project(files, uses_wiremock=uses_wiremock)
    return files, gate


async def run_pipeline(
    client: AsyncAnthropic,
    analysis: SpecAnalysis,
    spec_content: str,
    settings: Settings,
    *,
    reporter: StatusReporter | None = None,
    files_preloaded: dict[str, str] | None = None,
    cache_path: str | None = None,
    base_url_override: str | None = None,
) -> PipelineResult:
    log: list[str] = []
    base_package = f"com.{analysis.package_hint}"
    uses_wiremock = settings.uses_wiremock
    log.append(f"generation_profile={settings.generation_profile}")

    scaffold = (
        build_scaffold(
            analysis,
            base_url_override=base_url_override,
            uses_wiremock=uses_wiremock,
        )
        if settings.use_scaffold
        else {}
    )
    if base_url_override:
        log.append(f"base.url override: {base_url_override}")
    elif analysis.base_url:
        log.append(f"base.url из OpenAPI: {analysis.base_url}")

    async def progress(step: str, detail: str = "") -> None:
        log.append(f"{step} {detail}".strip())
        if reporter:
            await reporter.set_step(step, detail)

    if reporter:
        await progress("Спека", analysis.title)

    async def _generate():
        return await generate_framework(
            client,
            analysis,
            spec_content,
            model=settings.model,
            max_tokens=settings.max_tokens,
            max_retries=settings.max_retries,
            uses_wiremock=uses_wiremock,
            anthropic_timeout_sec=settings.anthropic_timeout_sec,
            anthropic_api_max_retries=settings.anthropic_api_max_retries,
            on_progress=progress if reporter else None,
        )

    gen_status: GateResult | None = None

    if files_preloaded is not None:
        generated_files = files_preloaded
        gen_log = [
            f"Кэш: загружено {len(generated_files)} файлов"
            + (f" — {cache_path}" if cache_path else "")
        ]
        log.extend(gen_log)
        if reporter:
            await progress("Сборка", "из кэша")
    else:
        if reporter:
            generated_files, gen_status, gen_log = await reporter.run_with_heartbeat(
                "Сборка",
                "",
                _generate(),
            )
        else:
            generated_files, gen_status, gen_log = await _generate()
        log.extend(gen_log)

    batch_ok = _output_batch_ok(generated_files, uses_wiremock=uses_wiremock)
    if not batch_ok and (gen_status is None or not gen_status.passed):
        fail_gate = gen_status or GateResult(
            passed=False,
            errors=["Недостаточно файлов — нет минимального набора Java-тестов."],
        )
        log.append("Стоп: недостаточно тестовых файлов в ответе.")
        await progress("Ошибка", "сборка")
        return PipelineResult(
            files=generated_files,
            static_gate=fail_gate,
            maven=None,
            log=log,
            elapsed_sec=reporter.elapsed_sec if reporter else 0,
            generated_files_raw=dict(generated_files),
        )

    generated_files_raw = dict(generated_files)

    await progress("Сборка", "")
    files, gate = _finalize_files(
        generated_files,
        scaffold,
        settings.use_scaffold,
        base_package,
        log,
        uses_wiremock=uses_wiremock,
    )

    if not gate.passed:
        await progress("Ошибка", "проверка кода")
        return PipelineResult(
            files=files,
            static_gate=gate,
            maven=None,
            log=log,
            elapsed_sec=reporter.elapsed_sec if reporter else 0,
            generated_files_raw=generated_files_raw,
        )

    if not settings.maven_validation_enabled:
        await progress("Готово", "Maven отключён")
        return PipelineResult(
            files=files,
            static_gate=gate,
            maven=None,
            log=log,
            elapsed_sec=reporter.elapsed_sec if reporter else 0,
            generated_files_raw=generated_files_raw,
        )

    async def _maven(files_map: dict[str, str]) -> MavenValidationResult:
        async def maven_detail(msg: str) -> None:
            if reporter:
                await reporter.set_detail(msg)

        coro = validate_maven_project(
            files_map,
            docker_image=settings.maven_docker_image,
            timeout_sec=settings.maven_timeout_sec,
            maven_extra_args=[],
            on_progress=maven_detail if reporter else None,
        )
        if reporter:
            return await reporter.run_with_heartbeat(
                "Maven",
                "mvn test",
                coro,
            )
        return await coro

    maven = await _maven(files)
    log.append(maven.summary())

    if maven.passed:
        await progress("Готово", "")
        return PipelineResult(
            files=files,
            static_gate=gate,
            maven=maven,
            log=log,
            elapsed_sec=reporter.elapsed_sec if reporter else 0,
            generated_files_raw=generated_files_raw,
        )

    if maven.skipped:
        await progress("Готово", "Maven пропущен")
        return PipelineResult(
            files=files,
            static_gate=gate,
            maven=maven,
            log=log,
            elapsed_sec=reporter.elapsed_sec if reporter else 0,
            generated_files_raw=generated_files_raw,
        )

    # Local autofix before API regen
    autofix = autofix_from_maven_log(
        files, maven.log_tail, base_package, uses_wiremock=uses_wiremock
    )
    if autofix.applied:
        log.extend(f"Maven auto-fix: {a}" for a in autofix.applied)
        await progress("Maven", "повтор")
        files, gate = _finalize_files(
            autofix.files,
            scaffold,
            settings.use_scaffold,
            base_package,
            log,
            uses_wiremock=uses_wiremock,
        )
        maven = await _maven(files)
        log.append(f"После auto-fix: {maven.summary()}")
        if maven.passed:
            await progress("Готово", "")
            return PipelineResult(
                files=files,
                static_gate=gate,
                maven=maven,
                log=log,
                elapsed_sec=reporter.elapsed_sec if reporter else 0,
                generated_files_raw=generated_files_raw,
            )

    from qa_gen_bot.prompts import get_maven_retry_hint

    maven_hint = get_maven_retry_hint(uses_wiremock=uses_wiremock)

    for attempt in range(1, settings.maven_max_retries + 1):
        await progress("Исправление", f"попытка {attempt}")

        async def _regen():
            return await regenerate_with_feedback(
                client,
                analysis,
                spec_content,
                existing_files=files,
                feedback=maven_hint + "\n\n" + maven.feedback_for_regen(),
                model=settings.model,
                max_tokens=settings.max_tokens,
                uses_wiremock=uses_wiremock,
                anthropic_timeout_sec=settings.anthropic_timeout_sec,
                anthropic_api_max_retries=settings.anthropic_api_max_retries,
                on_progress=progress if reporter else None,
            )

        if reporter:
            generated_files, _, gen_log = await reporter.run_with_heartbeat(
                "Исправление",
                "",
                _regen(),
            )
        else:
            generated_files, _, gen_log = await _regen()
        log.extend(gen_log)

        files, gate = _finalize_files(
            generated_files,
            scaffold,
            settings.use_scaffold,
            base_package,
            log,
            uses_wiremock=uses_wiremock,
        )
        if not gate.passed:
            break

        maven = await _maven(files)
        log.append(f"Maven retry: {maven.summary()}")
        if maven.passed:
            await progress("Готово", "")
            break

    result = PipelineResult(
        files=files,
        static_gate=gate,
        maven=maven,
        log=log,
        elapsed_sec=reporter.elapsed_sec if reporter else 0,
        generated_files_raw=generated_files_raw,
    )
    log_run_summary(
        mode="quick_start",
        profile=settings.generation_profile,
        segment=settings.segment,
        delivery_ready=result.delivery_ready,
        elapsed_sec=result.elapsed_sec,
    )
    return result
