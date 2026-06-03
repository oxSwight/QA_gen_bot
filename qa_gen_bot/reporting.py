"""ZIP and text reports (shared by Telegram bot and local CLI)."""
from __future__ import annotations

import zipfile
from pathlib import Path

from qa_gen_bot.pipeline import PipelineResult


def build_generation_report(
    result: PipelineResult,
    *,
    analysis_title: str,
    ops_count: int,
) -> str:
    lines = [
        f"Spec: {analysis_title}",
        f"Operations: {ops_count}",
        f"Files: {len(result.files)}",
        f"Elapsed: {result.elapsed_sec}s",
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
    result: PipelineResult,
    *,
    package_hint: str,
    analysis_title: str,
    ops_count: int,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"{package_hint}-qa-framework.zip"
    report_name = (
        "GENERATION_REPORT.txt"
        if result.delivery_ready or result.partial_success
        else "GENERATION_FAILED.txt"
    )
    report_body = build_generation_report(
        result, analysis_title=analysis_title, ops_count=ops_count
    )

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        if result.zip_shippable:
            for path, content in result.files.items():
                zf.writestr(path, content)
        zf.writestr(report_name, report_body)
        if result.maven and not result.maven.passed and not result.maven.skipped:
            zf.writestr("MAVEN_BUILD_REPORT.txt", result.maven.feedback_for_llm(20_000))

    (out_dir / report_name).write_text(report_body, encoding="utf-8")
    if result.maven and not result.maven.passed and not result.maven.skipped:
        (out_dir / "MAVEN_BUILD_REPORT.txt").write_text(
            result.maven.feedback_for_llm(20_000), encoding="utf-8"
        )
    return zip_path
