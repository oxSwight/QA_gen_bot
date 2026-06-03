"""End-to-end: scaffold + LLM → fixes → gate → Docker Maven → retry."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from anthropic import AsyncAnthropic

from qa_gen_bot.config import Settings
from qa_gen_bot.generator import (
    _llm_batch_ok,
    generate_framework,
    regenerate_with_feedback,
)
from qa_gen_bot.maven_validator import MavenValidationResult, validate_maven_project
from qa_gen_bot.quality_gate import GateResult, validate_generated_project
from qa_gen_bot.scaffold import build_scaffold, merge_with_scaffold, strip_llm_protected
from qa_gen_bot.spec_parser import SpecAnalysis
from qa_gen_bot.status_reporter import StatusReporter
from qa_gen_bot.structure_fixer import (
    apply_all_structure_fixes,
    autofix_from_maven_log,
)

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    files: dict[str, str]
    static_gate: GateResult
    maven: MavenValidationResult | None
    log: list[str] = field(default_factory=list)
    elapsed_sec: int = 0
    llm_files_raw: dict[str, str] | None = None

    @property
    def delivery_ready(self) -> bool:
        if not self.static_gate.passed:
            return False
        if self.maven is None:
            return True
        if self.maven.skipped:
            return False
        return self.maven.passed

    @property
    def zip_shippable(self) -> bool:
        """Deliverable ZIP only when static gate and Maven both pass."""
        return self.delivery_ready

    @property
    def partial_success(self) -> bool:
        return self.static_gate.passed and not self.delivery_ready


def _finalize_files(
    llm_files: dict[str, str],
    scaffold: dict[str, str],
    use_scaffold: bool,
    base_package: str,
    log: list[str],
) -> tuple[dict[str, str], GateResult]:
    files = llm_files
    if use_scaffold:
        llm_stripped = strip_llm_protected(llm_files)
        files = merge_with_scaffold(llm_stripped, scaffold)
        log.append(f"Scaffold merge: {len(scaffold)} protected + {len(llm_stripped)} от LLM")

    fix = apply_all_structure_fixes(
        files, base_package, scaffold if use_scaffold else None
    )
    if fix.applied:
        log.extend(f"Auto-fix: {a}" for a in fix.applied)
    files = fix.files

    gate = validate_generated_project(files)
    return files, gate


async def run_pipeline(
    client: AsyncAnthropic,
    analysis: SpecAnalysis,
    spec_content: str,
    settings: Settings,
    *,
    reporter: StatusReporter | None = None,
    llm_files_preloaded: dict[str, str] | None = None,
    llm_cache_path: str | None = None,
    base_url_override: str | None = None,
) -> PipelineResult:
    log: list[str] = []
    base_package = f"com.{analysis.package_hint}"
    scaffold = (
        build_scaffold(analysis, base_url_override=base_url_override)
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
            on_progress=progress if reporter else None,
        )

    gen_status: GateResult | None = None

    if llm_files_preloaded is not None:
        llm_files = llm_files_preloaded
        gen_log = [
            f"LLM: загружен из кэша ({len(llm_files)} файлов)"
            + (f" — {llm_cache_path}" if llm_cache_path else "")
        ]
        log.extend(gen_log)
        if reporter:
            await progress("Генерация", "из кэша")
    else:
        if reporter:
            llm_files, gen_status, gen_log = await reporter.run_with_heartbeat(
                "Генерация",
                "",
                _generate(),
            )
        else:
            llm_files, gen_status, gen_log = await _generate()
        log.extend(gen_log)

    batch_ok = _llm_batch_ok(llm_files)
    if not batch_ok and (gen_status is None or not gen_status.passed):
        fail_gate = gen_status or GateResult(
            passed=False,
            errors=["Недостаточно файлов от модели — нет минимального набора Java-тестов."],
        )
        log.append("Стоп: генерация не дала минимальный batch (LLM batch check).")
        await progress("Ошибка", "генерация")
        return PipelineResult(
            files=llm_files,
            static_gate=fail_gate,
            maven=None,
            log=log,
            elapsed_sec=reporter.elapsed_sec if reporter else 0,
            llm_files_raw=dict(llm_files),
        )

    llm_files_raw = dict(llm_files)

    await progress("Сборка", "")
    files, gate = _finalize_files(
        llm_files, scaffold, settings.use_scaffold, base_package, log
    )

    if not gate.passed:
        await progress("Ошибка", "проверка кода")
        return PipelineResult(
            files=files,
            static_gate=gate,
            maven=None,
            log=log,
            elapsed_sec=reporter.elapsed_sec if reporter else 0,
            llm_files_raw=llm_files_raw,
        )

    if not settings.maven_validation_enabled:
        await progress("Готово", "Maven отключён")
        return PipelineResult(
            files=files,
            static_gate=gate,
            maven=None,
            log=log,
            elapsed_sec=reporter.elapsed_sec if reporter else 0,
            llm_files_raw=llm_files_raw,
        )

    async def _maven(files_map: dict[str, str]) -> MavenValidationResult:
        async def maven_detail(msg: str) -> None:
            if reporter:
                await reporter.set_detail(msg)

        coro = validate_maven_project(
            files_map,
            docker_image=settings.maven_docker_image,
            timeout_sec=settings.maven_timeout_sec,
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
            llm_files_raw=llm_files_raw,
        )

    if maven.skipped:
        await progress("Готово", "Maven пропущен")
        return PipelineResult(
            files=files,
            static_gate=gate,
            maven=maven,
            log=log,
            elapsed_sec=reporter.elapsed_sec if reporter else 0,
            llm_files_raw=llm_files_raw,
        )

    # Local autofix pass before paid LLM regen
    autofix = autofix_from_maven_log(files, maven.log_tail, base_package)
    if autofix.applied:
        log.extend(f"Maven auto-fix: {a}" for a in autofix.applied)
        await progress("Maven", "повтор")
        files, gate = _finalize_files(
            autofix.files,
            scaffold,
            settings.use_scaffold,
            base_package,
            log,
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
                llm_files_raw=llm_files_raw,
            )

    from qa_gen_bot.prompts import MAVEN_RETRY_HINT

    for attempt in range(1, settings.maven_max_retries + 1):
        await progress("Исправление", f"попытка {attempt}")

        async def _regen():
            return await regenerate_with_feedback(
                client,
                analysis,
                spec_content,
                existing_files=files,
                feedback=MAVEN_RETRY_HINT + "\n\n" + maven.feedback_for_llm(),
                model=settings.model,
                max_tokens=settings.max_tokens,
                on_progress=progress if reporter else None,
            )

        if reporter:
            llm_files, _, gen_log = await reporter.run_with_heartbeat(
                "Исправление",
                "",
                _regen(),
            )
        else:
            llm_files, _, gen_log = await _regen()
        log.extend(gen_log)

        files, gate = _finalize_files(
            llm_files, scaffold, settings.use_scaffold, base_package, log
        )
        if not gate.passed:
            break

        maven = await _maven(files)
        log.append(f"Maven retry: {maven.summary()}")
        if maven.passed:
            await progress("Готово", "")
            break

    return PipelineResult(
        files=files,
        static_gate=gate,
        maven=maven,
        log=log,
        elapsed_sec=reporter.elapsed_sec if reporter else 0,
        llm_files_raw=llm_files_raw,
    )
