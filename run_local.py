"""
Local pipeline runner (no Telegram). Requires .env with ANTHROPIC_KEY.

Examples (from repo root, venv active):

  python run_local.py --spec fixtures/httpbin-live-testing-api.json --base-url https://httpbin.org
  python run_local.py --spec fixtures/jsonplaceholder-api.json --base-url https://jsonplaceholder.typicode.com
  python run_local.py --spec fixtures/httpbin-live-testing-api.json --use-cache --cache fixtures/httpbin-gen-cache.json --cheap
  python run_local.py --spec fixtures/httpbin-nested-object-ref.json --scaffold-only
  python run_local.py --maven-only --project-dir path/to/unpacked-zip
  python -m pytest tests/ -q
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from dataclasses import replace
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent
load_dotenv(_ROOT / ".env")

from anthropic import AsyncAnthropic

from qa_gen_bot.base_url import normalize_base_url
from qa_gen_bot.config import (
    PROFILE_CONTRACT_MOCKS,
    PROFILE_INTEGRATION_ONLY,
    Settings,
    load_settings,
)
from qa_gen_bot.gen_cache import load_gen_cache, save_gen_cache
from qa_gen_bot.maven_validator import validate_maven_project
from qa_gen_bot.core.models import GenerationRequest, GenerationResult
from qa_gen_bot.core.runner import run_generation
from qa_gen_bot.pipeline import _finalize_files
from qa_gen_bot.reporting import write_project_zip
from qa_gen_bot.scaffold import build_scaffold
from qa_gen_bot.spec_parser import parse_spec_content

logger = logging.getLogger(__name__)
DEFAULT_SPEC = _ROOT / "fixtures" / "jsonplaceholder-api.json"
DEFAULT_OUT = _ROOT / "out_local"
DEFAULT_CACHE = DEFAULT_OUT / "gen_cache.json"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Локальный QA Gen pipeline (без Telegram).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--spec",
        type=Path,
        default=DEFAULT_SPEC,
        help=f"OpenAPI JSON (default: {DEFAULT_SPEC.name})",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="Каталог для ZIP и отчётов",
    )
    p.add_argument(
        "--cache",
        type=Path,
        default=DEFAULT_CACHE,
        help="Путь к файлу кэша генерации",
    )
    p.add_argument(
        "--save-cache",
        action="store_true",
        help="После прогона сохранить сырой ответ API в --cache",
    )
    p.add_argument(
        "--use-cache",
        action="store_true",
        help="Не вызывать API — взять файлы из --cache",
    )
    p.add_argument(
        "--scaffold-only",
        action="store_true",
        help="Без API: только scaffold + finalize + gate (+ Maven)",
    )
    p.add_argument(
        "--base-url",
        type=str,
        default=None,
        help="Переопределить base.url в config.properties (как в Telegram после JSON)",
    )
    p.add_argument(
        "--cheap",
        action="store_true",
        help="GENERATION_MAX_RETRIES=0, MAVEN_MAX_RETRIES=0 (минимум вызовов API)",
    )
    p.add_argument(
        "--no-maven",
        action="store_true",
        help="Пропустить Docker mvn test",
    )
    p.add_argument(
        "--maven-only",
        action="store_true",
        help="Только mvn test по --project-dir (распакованный проект)",
    )
    p.add_argument(
        "--project-dir",
        type=Path,
        help="Папка с pom.xml (для --maven-only)",
    )
    p.add_argument(
        "--generation-profile",
        choices=[PROFILE_CONTRACT_MOCKS, PROFILE_INTEGRATION_ONLY],
        default=None,
        help="contract-mocks (WireMock) или integration-only (live API tests)",
    )
    p.add_argument(
        "--mode",
        choices=["quick_start", "repo"],
        default="quick_start",
        help="quick_start (ZIP Mode A) или repo (openapi-generator Mode B)",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args()


def _settings_for_run(args: argparse.Namespace) -> Settings:
    require_api = not (args.use_cache or args.scaffold_only or args.maven_only)
    base = load_settings(require_telegram=False, require_anthropic=require_api)
    if args.generation_profile:
        base = replace(base, generation_profile=args.generation_profile)
    if args.cheap:
        base = replace(base, max_retries=0, maven_max_retries=0)
    if args.no_maven:
        base = replace(base, maven_validation_enabled=False)
    return base


def _read_spec(path: Path) -> tuple[str, object]:
    raw = path.read_text(encoding="utf-8-sig")
    analysis = parse_spec_content(raw)
    if analysis.error:
        raise SystemExit(f"Spec error: {analysis.error}")
    return raw, analysis


def _files_from_dir(project_dir: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for fp in project_dir.rglob("*"):
        if fp.is_file():
            rel = fp.relative_to(project_dir).as_posix()
            if rel.endswith((".java", ".xml", ".json", ".properties", ".md")):
                files[rel] = fp.read_text(encoding="utf-8")
    if "pom.xml" not in files:
        raise SystemExit(f"Нет pom.xml в {project_dir}")
    return files


def _print_result(
    result: GenerationResult,
    zip_path: Path | None,
    *,
    scaffold_only: bool = False,
) -> int:
    print()
    print("=" * 60)
    if scaffold_only:
        print("OK  scaffold-only — только шаблоны (API не вызывался)")
        print(
            "    Static gate сейчас падает — это нормально: нет DTO, тестов и schemas из API."
        )
    elif result.delivery_ready:
        print("OK  Production-ready (static + mvn test)")
    elif result.partial_success:
        print("WARN  Static OK, Maven failed or skipped")
    else:
        print("FAIL  Static gate or generation")
    print(f"Files: {len(result.files)}  Elapsed: {result.elapsed_sec}s")
    if zip_path:
        print(f"ZIP: {zip_path}")
    print()
    if result.static_gate.errors:
        label = (
            "Ожидаемые ошибки gate (нет доп. файлов):"
            if scaffold_only
            else "Static errors:"
        )
        print(label)
        seen: set[str] = set()
        for e in result.static_gate.errors:
            if e in seen:
                continue
            seen.add(e)
            print(f"  - {e}")
    if scaffold_only:
        print()
        print("Дальше:")
        print("  python -m pytest tests/ -q          # fixers/gate, $0")
        print("  python run_local.py --save-cache     # 1× API + кэш")
        print("  python run_local.py --use-cache      # fixers+Maven, $0")
    if result.maven and not result.maven.passed:
        print(result.maven.summary())
        if result.maven.log_tail:
            print("\n--- maven tail ---")
            print(result.maven.log_tail[-3000:])
    print("=" * 60)
    if scaffold_only:
        return 0
    return 0 if result.delivery_ready else 1


async def _run_maven_only(args: argparse.Namespace) -> int:
    if not args.project_dir:
        raise SystemExit("--maven-only требует --project-dir")
    from qa_gen_bot.quality_gate import GateResult

    settings = _settings_for_run(args)
    files = _files_from_dir(args.project_dir)
    t0 = time.monotonic()
    maven = await validate_maven_project(
        files,
        docker_image=settings.maven_docker_image,
        timeout_sec=settings.maven_timeout_sec,
    )
    result = GenerationResult(
        files=files,
        static_gate=GateResult(passed=True),
        maven=maven,
        log=[maven.summary()],
        elapsed_sec=int(time.monotonic() - t0),
    )
    return _print_result(result, None)


async def _run_scaffold_only(
    spec_content: str, analysis, settings: Settings, out_dir: Path
) -> int:
    scaffold = (
        build_scaffold(analysis, uses_wiremock=settings.uses_wiremock)
        if settings.use_scaffold
        else {}
    )
    base_package = f"com.{analysis.package_hint}"
    log: list[str] = ["scaffold-only: API пропущен"]
    t0 = time.monotonic()
    files, gate = _finalize_files(
        {},
        scaffold,
        settings.use_scaffold,
        base_package,
        log,
        uses_wiremock=settings.uses_wiremock,
    )
    maven = None
    if settings.maven_validation_enabled:
        maven = await validate_maven_project(
            files,
            docker_image=settings.maven_docker_image,
            timeout_sec=settings.maven_timeout_sec,
        )
        log.append(maven.summary())
    result = GenerationResult(
        files=files,
        static_gate=gate,
        maven=maven,
        log=log,
        elapsed_sec=int(time.monotonic() - t0),
    )
    zip_path = write_project_zip(
        out_dir,
        result,
        package_hint=analysis.package_hint,
        analysis_title=analysis.title,
        ops_count=len(analysis.operations),
        profile_label=settings.generation_profile,
    )
    return _print_result(result, zip_path, scaffold_only=True)


async def _run_full(args: argparse.Namespace) -> int:
    spec_content, analysis = _read_spec(args.spec)
    settings = _settings_for_run(args)
    out_dir = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    files_preloaded = None
    if args.use_cache:
        if not args.cache.is_file():
            raise SystemExit(
                f"Нет кэша {args.cache}. Сначала: python run_local.py --save-cache"
            )
        files_preloaded = load_gen_cache(
            args.cache,
            expected_package_hint=analysis.package_hint,
        )
        print(
            f"Cache: {len(files_preloaded)} files from {args.cache} "
            f"(package com.{analysis.package_hint})"
        )

    if args.scaffold_only:
        return await _run_scaffold_only(spec_content, analysis, settings, out_dir)

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    t0 = time.monotonic()

    base_url_override = None
    if args.base_url:
        base_url_override, err = normalize_base_url(args.base_url)
        if err:
            raise SystemExit(f"base-url: {err}")
        print(f"base.url override: {base_url_override}")

    request = GenerationRequest(
        analysis=analysis,
        spec_content=spec_content,
        generation_profile=settings.generation_profile,
        base_url_override=base_url_override,
        mode=args.mode,
        files_preloaded=files_preloaded,
        cache_path=str(args.cache) if files_preloaded else None,
    )
    result = await run_generation(client, request, settings)
    result = GenerationResult(
        files=result.files,
        static_gate=result.static_gate,
        maven=result.maven,
        log=result.log,
        elapsed_sec=int(time.monotonic() - t0),
        generated_files_raw=result.generated_files_raw,
        mode=result.mode,
    )

    zip_path = write_project_zip(
        out_dir,
        result,
        package_hint=analysis.package_hint,
        analysis_title=analysis.title,
        ops_count=len(analysis.operations),
        profile_label=settings.generation_profile,
    )

    if args.save_cache and not args.use_cache:
        raw = result.generated_files_raw
        if raw:
            save_gen_cache(
                args.cache,
                spec_path=str(args.spec),
                package_hint=analysis.package_hint,
                files=raw,
            )
            print(f"Saved generation cache ({len(raw)} files): {args.cache}")
        else:
            print("WARN: --save-cache: нет generated_files_raw")

    return _print_result(result, zip_path)


async def _amain() -> int:
    args = _parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    if args.maven_only:
        return await _run_maven_only(args)
    if not args.spec.is_file():
        raise SystemExit(f"Spec not found: {args.spec}")
    return await _run_full(args)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    try:
        code = asyncio.run(_amain())
    except KeyboardInterrupt:
        code = 130
    sys.exit(code)


if __name__ == "__main__":
    main()
