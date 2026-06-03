"""Mode B: repo layout + openapi-generator + tests in src/test/java."""
from __future__ import annotations

import logging

from anthropic import AsyncAnthropic

from qa_gen_bot.codegen.repo_output_filter import filter_repo_generated_files
from qa_gen_bot.codegen.repo_scaffold import build_repo_scaffold
from qa_gen_bot.config import Settings
from qa_gen_bot.core.models import GenerationRequest, GenerationResult
from qa_gen_bot.generator import (
    _output_batch_ok,
    generate_framework,
    regenerate_with_feedback,
)
from qa_gen_bot.maven_validator import MavenValidationResult, validate_maven_project
from qa_gen_bot.metrics import log_run_summary
from qa_gen_bot.prompts import get_maven_retry_hint
from qa_gen_bot.quality_gate import GateResult, validate_repo_project
from qa_gen_bot.status_reporter import StatusReporter
from qa_gen_bot.structure_fixer import apply_all_structure_fixes, autofix_from_maven_log

logger = logging.getLogger(__name__)


def _merge_repo_files(
    scaffold: dict[str, str],
    generated_files: dict[str, str],
) -> dict[str, str]:
    merged = dict(scaffold)
    for path, content in filter_repo_generated_files(generated_files).items():
        merged[path] = content
    return merged


def _finalize_repo(
    files: dict[str, str],
    base_package: str,
    scaffold: dict[str, str],
    log: list[str],
    *,
    uses_wiremock: bool,
) -> tuple[dict[str, str], GateResult]:
    fix = apply_all_structure_fixes(
        files,
        base_package,
        scaffold,
        uses_wiremock=uses_wiremock,
    )
    if fix.applied:
        log.extend(f"Auto-fix: {a}" for a in fix.applied)
    files = fix.files
    gate = validate_repo_project(files, uses_wiremock=uses_wiremock)
    return files, gate


async def run_repo_mode(
    client: AsyncAnthropic,
    request: GenerationRequest,
    settings: Settings,
    *,
    reporter: StatusReporter | None = None,
) -> GenerationResult:
    """
    Repo mode: deterministic codegen scaffold + generated tests.

    Maven runs `generate-sources test` so generated API exists under target/.
    """
    log: list[str] = ["Mode B: repo / openapi-generator"]
    analysis = request.analysis
    uses_wiremock = request.uses_wiremock
    base_package = f"com.{analysis.package_hint}"

    async def progress(step: str, detail: str = "") -> None:
        log.append(f"{step} {detail}".strip())
        if reporter:
            await reporter.set_step(step, detail)

    await progress("Repo scaffold", "openapi.json + pom plugin")

    scaffold = build_repo_scaffold(
        analysis,
        request.spec_content,
        base_url_override=request.base_url_override,
        uses_wiremock=uses_wiremock,
    )

    async def _generate():
        return await generate_framework(
            client,
            analysis,
            request.spec_content,
            model=settings.model,
            max_tokens=settings.max_tokens,
            max_retries=settings.max_retries,
            uses_wiremock=uses_wiremock,
            repo_mode=True,
            anthropic_timeout_sec=settings.anthropic_timeout_sec,
            anthropic_api_max_retries=settings.anthropic_api_max_retries,
            on_progress=progress if reporter else None,
        )

    if reporter:
        generated_files, gen_status, gen_log = await reporter.run_with_heartbeat(
            "Сборка",
            "repo / tests only",
            _generate(),
        )
    else:
        generated_files, gen_status, gen_log = await _generate()
    log.extend(gen_log)

    if not _output_batch_ok(generated_files, uses_wiremock=uses_wiremock, repo_mode=True):
        fail_gate = gen_status or GateResult(
            passed=False,
            errors=["Недостаточно тестовых файлов (Mode B)."],
        )
        await progress("Ошибка", "сборка")
        return GenerationResult(
            files=filter_repo_generated_files(generated_files),
            static_gate=fail_gate,
            maven=None,
            log=log,
            mode="repo",
        )

    generated_files_raw = filter_repo_generated_files(dict(generated_files))
    files = _merge_repo_files(scaffold, generated_files_raw)
    files, gate = _finalize_repo(
        files, base_package, scaffold, log, uses_wiremock=uses_wiremock
    )

    if not gate.passed:
        await progress("Ошибка", "static gate")
        return GenerationResult(
            files=files,
            static_gate=gate,
            maven=None,
            log=log,
            mode="repo",
            generated_files_raw=generated_files_raw,
        )

    if not settings.maven_validation_enabled:
        await progress("Готово", "Maven отключён")
        result = GenerationResult(
            files=files,
            static_gate=gate,
            maven=None,
            log=log,
            elapsed_sec=reporter.elapsed_sec if reporter else 0,
            generated_files_raw=generated_files_raw,
            mode="repo",
        )
        log_run_summary(
            mode="repo",
            profile=request.generation_profile,
            segment=settings.segment,
            delivery_ready=result.delivery_ready,
            elapsed_sec=result.elapsed_sec,
        )
        return result

    async def _maven(files_map: dict[str, str]) -> MavenValidationResult:
        async def maven_detail(msg: str) -> None:
            if reporter:
                await reporter.set_detail(msg)

        coro = validate_maven_project(
            files_map,
            docker_image=settings.maven_docker_image,
            timeout_sec=settings.maven_timeout_sec,
            maven_extra_args=["generate-sources", "test"],
            on_progress=maven_detail if reporter else None,
        )
        if reporter:
            return await reporter.run_with_heartbeat(
                "Maven",
                "generate-sources test",
                coro,
            )
        return await coro

    maven = await _maven(files)
    log.append(maven.summary())

    if maven.passed or maven.skipped:
        await progress("Готово", "")
        result = GenerationResult(
            files=files,
            static_gate=gate,
            maven=maven,
            log=log,
            elapsed_sec=reporter.elapsed_sec if reporter else 0,
            generated_files_raw=generated_files_raw,
            mode="repo",
        )
        log_run_summary(
            mode="repo",
            profile=request.generation_profile,
            segment=settings.segment,
            delivery_ready=result.delivery_ready,
            elapsed_sec=result.elapsed_sec,
        )
        return result

    autofix = autofix_from_maven_log(
        files, maven.log_tail, base_package, uses_wiremock=uses_wiremock
    )
    if autofix.applied:
        log.extend(f"Maven auto-fix: {a}" for a in autofix.applied)
        files = _merge_repo_files(scaffold, filter_repo_generated_files(autofix.files))
        files, gate = _finalize_repo(
            files, base_package, scaffold, log, uses_wiremock=uses_wiremock
        )
        maven = await _maven(files)
        log.append(f"После auto-fix: {maven.summary()}")
        if maven.passed:
            await progress("Готово", "")
            result = GenerationResult(
                files=files,
                static_gate=gate,
                maven=maven,
                log=log,
                elapsed_sec=reporter.elapsed_sec if reporter else 0,
                generated_files_raw=generated_files_raw,
                mode="repo",
            )
            log_run_summary(
                mode="repo",
                profile=request.generation_profile,
                segment=settings.segment,
                delivery_ready=result.delivery_ready,
                elapsed_sec=result.elapsed_sec,
            )
            return result

    maven_hint = get_maven_retry_hint(uses_wiremock=uses_wiremock, repo_mode=True)

    for attempt in range(1, settings.maven_max_retries + 1):
        await progress("Исправление", f"попытка {attempt}")

        async def _regen():
            return await regenerate_with_feedback(
                client,
                analysis,
                request.spec_content,
                existing_files=files,
                feedback=maven_hint + "\n\n" + maven.feedback_for_regen(),
                model=settings.model,
                max_tokens=settings.max_tokens,
                uses_wiremock=uses_wiremock,
                repo_mode=True,
                anthropic_timeout_sec=settings.anthropic_timeout_sec,
                anthropic_api_max_retries=settings.anthropic_api_max_retries,
                on_progress=progress if reporter else None,
            )

        if reporter:
            api_patch, _, gen_log = await reporter.run_with_heartbeat(
                "Исправление",
                "",
                _regen(),
            )
        else:
            api_patch, _, gen_log = await _regen()
        log.extend(gen_log)

        files = _merge_repo_files(scaffold, api_patch)
        files, gate = _finalize_repo(
            files, base_package, scaffold, log, uses_wiremock=uses_wiremock
        )
        if not gate.passed:
            break

        maven = await _maven(files)
        log.append(f"Maven retry: {maven.summary()}")
        if maven.passed:
            await progress("Готово", "")
            break

    result = GenerationResult(
        files=files,
        static_gate=gate,
        maven=maven,
        log=log,
        elapsed_sec=reporter.elapsed_sec if reporter else 0,
        generated_files_raw=generated_files_raw,
        mode="repo",
    )
    log_run_summary(
        mode="repo",
        profile=request.generation_profile,
        segment=settings.segment,
        delivery_ready=result.delivery_ready,
        elapsed_sec=result.elapsed_sec,
    )
    return result
