"""ZIP and text reports (shared by Telegram bot and local CLI)."""
from __future__ import annotations

import zipfile
from pathlib import Path

from qa_gen_bot.core.models import GenerationResult


def human_pipeline_summary(
    result: GenerationResult,
    *,
    profile_label: str,
    mode_label: str | None = None,
) -> str:
    """Short outcome for operators without reading Java."""
    test_count = sum(c.count("@Test") for c in result.files.values())
    lines = [
        f"Профиль: {profile_label}",
    ]
    if mode_label:
        lines.append(f"Режим: {mode_label}")
    lines.extend(
        [
            f"Файлов в проекте: {len(result.files)}",
            f"Методов @Test (оценка): ~{test_count}",
        ]
    )
    if result.delivery_ready:
        lines.append("Итог: готово — static gate и mvn test OK.")
        if result.maven and result.maven.tests_run is not None:
            lines.append(
                f"Maven: {result.maven.tests_run} тестов за "
                f"{result.maven.duration_sec or 0:.0f}s."
            )
    elif result.partial_success:
        if result.maven and result.maven.skipped:
            lines.append("Итог: код прошёл static gate, Maven не запускался (нет Docker).")
        else:
            lines.append("Итог: static gate OK, Maven не прошёл — см. отчёты в ZIP.")
    else:
        lines.append("Итог: не готово — см. GENERATION_FAILED.txt.")
    return "\n".join(lines)


def build_generation_report(
    result: GenerationResult,
    *,
    analysis_title: str,
    ops_count: int,
    profile_label: str = "contract-mocks",
) -> str:
    lines = [
        f"Spec: {analysis_title}",
        f"Operations: {ops_count}",
        f"Profile: {profile_label}",
        f"Files: {len(result.files)}",
        f"Elapsed: {result.elapsed_sec}s",
        "",
        "=== Краткий итог ===",
        human_pipeline_summary(result, profile_label=profile_label),
        "",
        "=== Pipeline log ===",
        *result.log,
        "",
        "=== Static gate ===",
        result.static_gate.summary() or "OK",
    ]
    if result.maven:
        lines.extend(["", "=== Maven (Docker) ===", result.maven.summary()])
        if result.maven.log_tail and not result.maven.passed:
            lines.extend(["", "=== Maven log (tail) ===", result.maven.log_tail])
    return "\n".join(lines)


def write_project_zip(
    out_dir: Path,
    result: GenerationResult,
    *,
    package_hint: str,
    analysis_title: str,
    ops_count: int,
    profile_label: str = "contract-mocks",
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"{package_hint}-qa-framework.zip"
    report_name = (
        "GENERATION_REPORT.txt"
        if result.delivery_ready or result.partial_success
        else "GENERATION_FAILED.txt"
    )
    report_body = build_generation_report(
        result,
        analysis_title=analysis_title,
        ops_count=ops_count,
        profile_label=profile_label,
    )

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        if result.zip_shippable:
            for path, content in result.files.items():
                zf.writestr(path, content)
        zf.writestr(report_name, report_body)
        if result.maven and not result.maven.passed and not result.maven.skipped:
            zf.writestr("MAVEN_BUILD_REPORT.txt", result.maven.feedback_for_regen(20_000))

    (out_dir / report_name).write_text(report_body, encoding="utf-8")
    if result.maven and not result.maven.passed and not result.maven.skipped:
        (out_dir / "MAVEN_BUILD_REPORT.txt").write_text(
            result.maven.feedback_for_regen(20_000), encoding="utf-8"
        )
    return zip_path
