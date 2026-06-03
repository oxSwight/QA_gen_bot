"""Dispatch generation by mode (Quick Start vs Repo)."""
from __future__ import annotations

import logging
from dataclasses import replace

from anthropic import AsyncAnthropic

from qa_gen_bot.config import Settings
from qa_gen_bot.core.models import GenerationRequest, GenerationResult
from qa_gen_bot.status_reporter import StatusReporter

logger = logging.getLogger(__name__)


def _settings_for_request(base: Settings, request: GenerationRequest) -> Settings:
    return replace(base, generation_profile=request.generation_profile)


async def run_quick_start(
    client: AsyncAnthropic,
    request: GenerationRequest,
    settings: Settings,
    *,
    reporter: StatusReporter | None = None,
) -> GenerationResult:
    from qa_gen_bot.pipeline import run_pipeline

    effective = _settings_for_request(settings, request)
    pipeline_result = await run_pipeline(
        client,
        request.analysis,
        request.spec_content,
        effective,
        reporter=reporter,
        files_preloaded=request.files_preloaded,
        cache_path=request.cache_path,
        base_url_override=request.base_url_override,
    )
    return GenerationResult(
        files=pipeline_result.files,
        static_gate=pipeline_result.static_gate,
        maven=pipeline_result.maven,
        log=pipeline_result.log,
        elapsed_sec=pipeline_result.elapsed_sec,
        generated_files_raw=pipeline_result.generated_files_raw,
        mode="quick_start",
    )


async def run_generation(
    client: AsyncAnthropic,
    request: GenerationRequest,
    settings: Settings,
    *,
    reporter: StatusReporter | None = None,
) -> GenerationResult:
    effective = _settings_for_request(settings, request)

    if request.mode == "repo":
        from qa_gen_bot.pipeline_mode_b import run_repo_mode

        logger.info(
            "Generation mode=repo profile=%s segment=%s",
            request.generation_profile,
            effective.segment,
        )
        return await run_repo_mode(
            client, request, effective, reporter=reporter
        )

    return await run_quick_start(client, request, effective, reporter=reporter)
