"""Run mvn test inside Docker to verify generated projects compile and pass."""
from __future__ import annotations

import asyncio
import logging
import re
import tempfile
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from qa_gen_bot.safe_paths import filter_safe_file_map, require_safe_file_map

logger = logging.getLogger(__name__)

TESTS_RUN_RE = re.compile(
    r"Tests run:\s*(\d+),\s*Failures:\s*(\d+)(?:,\s*Errors:\s*(\d+))?",
    re.IGNORECASE,
)
BUILD_SUCCESS_RE = re.compile(r"BUILD SUCCESS", re.IGNORECASE)
BUILD_FAILURE_RE = re.compile(r"BUILD FAILURE", re.IGNORECASE)
COMPILATION_ERROR_RE = re.compile(r"\[ERROR\].*\.java:\[", re.IGNORECASE)


@dataclass
class MavenValidationResult:
    passed: bool
    skipped: bool = False
    skip_reason: str | None = None
    exit_code: int | None = None
    tests_run: int | None = None
    failures: int | None = None
    test_errors: int | None = None
    duration_sec: float | None = None
    log_tail: str = ""
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if self.skipped:
            return f"Maven: пропущено ({self.skip_reason})"
        if self.passed:
            extra = ""
            if self.tests_run is not None:
                err = self.test_errors or 0
                extra = (
                    f", tests={self.tests_run}, failures={self.failures or 0}, "
                    f"errors={err}"
                )
            return f"Maven: BUILD SUCCESS{extra}"
        return "Maven: BUILD FAILURE\n" + "\n".join(f"  • {e}" for e in self.errors)

    def feedback_for_regen(self, max_chars: int = 6_000) -> str:
        """Compact log excerpt for API retry."""
        tail = self.log_tail[-max_chars:] if self.log_tail else ""
        return (
            f"exit_code={self.exit_code}\n"
            f"tests_run={self.tests_run} failures={self.failures} "
            f"errors={self.test_errors}\n\n"
            f"--- maven log (tail) ---\n{tail}"
        )


async def is_docker_available() -> bool:
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "version",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=15)
        return proc.returncode == 0
    except (OSError, asyncio.TimeoutError):
        return False


def _write_project_to_disk(files: dict[str, str], root: Path) -> None:
    safe_files = require_safe_file_map(files, context="maven_disk")
    root_resolved = root.resolve()
    for rel_path, content in safe_files.items():
        target = (root / rel_path).resolve()
        if not str(target).startswith(str(root_resolved)):
            logger.error("Path escapes maven temp root: %s", rel_path)
            raise ValueError(f"Unsafe path for Maven workspace: {rel_path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")


async def _docker_force_stop(container_name: str) -> None:
    """Stop orphaned Maven container after CLI timeout (proc.kill is not enough)."""
    for cmd in (
        ["docker", "kill", container_name],
        ["docker", "rm", "-f", container_name],
    ):
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.wait(), timeout=30)
            logger.info("Docker cleanup: %s (exit %s)", " ".join(cmd), proc.returncode)
        except (OSError, asyncio.TimeoutError) as exc:
            logger.warning("Docker cleanup failed %s: %s", cmd, exc)


def _docker_volume_arg(host_path: Path) -> str:
    """Docker bind mount path (Windows-friendly)."""
    resolved = host_path.resolve()
    return f"{resolved}:/project"


def _surefire_results_tail(output: str) -> str:
    """Extract the final Surefire summary block from Maven output."""
    marker = "[INFO] Results:"
    if marker in output:
        return output.split(marker, 1)[-1]
    return output[-4000:]


def _parse_maven_output(output: str, exit_code: int) -> MavenValidationResult:
    tests_run = failures = test_errors = None
    summary = _surefire_results_tail(output)
    matches = list(TESTS_RUN_RE.finditer(summary))
    if not matches:
        matches = list(TESTS_RUN_RE.finditer(output))
    if matches:
        final = matches[-1]
        tests_run = int(final.group(1))
        failures = int(final.group(2))
        if final.group(3) is not None:
            test_errors = int(final.group(3))

    errors: list[str] = []
    tail = output[-8000:]
    build_failed = BUILD_FAILURE_RE.search(tail) is not None

    if build_failed or exit_code != 0:
        for line in output.splitlines():
            if "[ERROR]" in line and len(errors) < 12:
                stripped = line.strip()
                if stripped not in errors:
                    errors.append(stripped)

    compile_failed = (
        COMPILATION_ERROR_RE.search(output) is not None
        or "Compilation failure" in output
        or "COMPILATION ERROR" in output
    )

    passed = exit_code == 0 and not build_failed and not compile_failed
    if BUILD_SUCCESS_RE.search(tail) and not build_failed and not compile_failed:
        passed = True
    if (
        tests_run is not None
        and tests_run > 0
        and not (failures or 0)
        and not (test_errors or 0)
        and BUILD_SUCCESS_RE.search(tail)
        and not build_failed
    ):
        passed = True

    if tests_run is not None and failures and failures > 0:
        passed = False
        errors.append(f"Упавших тестов: {failures} из {tests_run}")
    if test_errors and test_errors > 0:
        passed = False
        errors.append(
            f"Ошибок выполнения тестов (Errors): {test_errors} "
            f"(часто UnknownHost — интеграционные тесты на base.url без стенда)"
        )

    if compile_failed and tests_run is None:
        errors.append(
            "Ошибка компиляции (main/test) — Surefire не запускался (tests_run отсутствует)."
        )

    if not passed and not errors:
        errors.append("Сборка не прошла — см. log_tail в отчёте.")

    if tests_run == 0 and passed:
        errors.append("Maven не запустил ни одного теста (tests run: 0).")
        passed = False

    if passed and tests_run is None:
        passed = False
        errors.append(
            "Сборка успешна, но Surefire не нашел тестов для запуска "
            "(Tests run: N отсутствует)"
        )

    return MavenValidationResult(
        passed=passed,
        exit_code=exit_code,
        tests_run=tests_run,
        failures=failures,
        test_errors=test_errors,
        log_tail=output[-12_000:],
        errors=errors,
    )


async def validate_maven_project(
    files: dict[str, str],
    *,
    docker_image: str,
    timeout_sec: int,
    maven_extra_args: list[str] | None = None,
    on_progress: Callable[[str], Awaitable[None]] | None = None,
) -> MavenValidationResult:
    if not _has_pom(files):
        return MavenValidationResult(
            passed=False,
            errors=["Нет pom.xml для Maven-сборки."],
        )

    if not await is_docker_available():
        return MavenValidationResult(
            passed=False,
            skipped=True,
            skip_reason="Docker недоступен (установи Docker Desktop и запусти daemon).",
        )

    safe_files, rejected = filter_safe_file_map(files, context="maven_validate")
    if rejected:
        return MavenValidationResult(
            passed=False,
            errors=[
                f"Небезопасные пути в проекте ({len(rejected)}): "
                + ", ".join(rejected[:3])
            ],
        )

    container_name = f"qa_gen_maven_{uuid.uuid4().hex[:12]}"

    with tempfile.TemporaryDirectory(prefix="qa_gen_maven_") as tmp:
        root = Path(tmp)
        await asyncio.to_thread(_write_project_to_disk, safe_files, root)

        goals = maven_extra_args if maven_extra_args else ["test"]
        mvn_args = ["mvn", "-B", *goals]
        cmd = [
            "docker",
            "run",
            "--rm",
            "--name",
            container_name,
            "-v",
            _docker_volume_arg(root),
            "-w",
            "/project",
            docker_image,
            *mvn_args,
        ]
        logger.info("Maven validation: %s", " ".join(cmd[:8]))
        if on_progress:
            await on_progress("mvn test…")

        started = time.monotonic()
        proc: asyncio.subprocess.Process | None = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
        except asyncio.TimeoutError:
            if proc:
                proc.kill()
            await _docker_force_stop(container_name)
            logger.error(
                "Maven Docker timeout after %ss; container %s force-stopped",
                timeout_sec,
                container_name,
            )
            return MavenValidationResult(
                passed=False,
                exit_code=-1,
                duration_sec=float(timeout_sec),
                errors=[f"Таймаут Maven ({timeout_sec}s). Упрости проект или увеличь MAVEN_TIMEOUT_SEC."],
                log_tail="Timeout (Docker container stopped)",
            )

        duration = time.monotonic() - started
        output = stdout.decode("utf-8", errors="replace")
        result = _parse_maven_output(output, proc.returncode or 1)
        result.duration_sec = duration
        return result


def _has_pom(files: dict[str, str]) -> bool:
    return any(p.replace("\\", "/").endswith("pom.xml") for p in files)
