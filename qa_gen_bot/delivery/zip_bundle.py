"""Build ZIP archives from generation results."""
from __future__ import annotations

import io
import zipfile

from qa_gen_bot.core.models import GenerationResult
from qa_gen_bot.reporting import build_generation_report
from qa_gen_bot.safe_paths import filter_safe_file_map


def build_project_zip_bytes(
    result: GenerationResult,
    *,
    analysis_title: str,
    ops_count: int,
    profile_label: str,
    include_sources: bool = True,
) -> tuple[bytes, str]:
    """
    Returns (zip_bytes, report_filename).

    include_sources=False when only reports should ship (failed gate/Maven).
    """
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

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        if include_sources:
            payload, rejected = filter_safe_file_map(
                result.files, context="telegram_zip"
            )
            if rejected:
                zf.writestr(
                    "UNSAFE_PATHS_REJECTED.txt",
                    "Rejected paths (Zip Slip protection):\n"
                    + "\n".join(rejected),
                )
        else:
            payload = {}
        for path, content in payload.items():
            zf.writestr(path, content)
        zf.writestr(report_name, report_body)
        if result.maven and not result.maven.passed and not result.maven.skipped:
            zf.writestr(
                "MAVEN_BUILD_REPORT.txt",
                result.maven.feedback_for_regen(20_000),
            )

    return zip_buffer.getvalue(), report_name
