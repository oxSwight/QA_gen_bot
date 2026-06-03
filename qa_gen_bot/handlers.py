"""Telegram bot handlers."""
from __future__ import annotations

import asyncio
import io
import logging
import zipfile
from collections import defaultdict

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest
from anthropic import AsyncAnthropic

from qa_gen_bot.base_url import is_skip_base_url, normalize_base_url
from qa_gen_bot.config import Settings
from qa_gen_bot.pending_jobs import PendingSpecJob, clear_pending, get_pending, set_pending
from qa_gen_bot.pipeline import PipelineResult, run_pipeline
from qa_gen_bot.spec_parser import SpecType, parse_spec_content
from qa_gen_bot.status_reporter import StatusReporter
from qa_gen_bot.usage_limits import get_quota_status, reserve_generation

logger = logging.getLogger(__name__)

_pipeline_sem = asyncio.Semaphore(2)
_user_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


def _build_project_zip_bytes(
    files: dict[str, str],
    *,
    report_name: str,
    report_body: str,
    maven_report: str | None = None,
) -> bytes:
    """CPU-bound ZIP assembly — run via asyncio.to_thread from handlers."""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, content in files.items():
            zf.writestr(path, content)
        zf.writestr(report_name, report_body)
        if maven_report:
            zf.writestr("MAVEN_BUILD_REPORT.txt", maven_report)
    return zip_buffer.getvalue()


def _build_report(result: PipelineResult, analysis_title: str, ops_count: int) -> str:
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


def _caption(result: PipelineResult, analysis, *, base_url_used: str) -> str:
    if result.delivery_ready:
        status = "Готово: mvn test прошёл"
    elif result.partial_success:
        if result.maven and result.maven.skipped:
            status = "Частично: нет Docker, Maven не проверялся"
        elif not result.zip_shippable:
            status = "Ошибка: в ZIP только отчёты"
        else:
            status = "Частично: mvn test не прошёл — см. отчёт в ZIP"
    else:
        status = "Ошибка: см. GENERATION_FAILED.txt"

    return (
        f"<b>{analysis.title}</b>\n"
        f"URL: <code>{base_url_used}</code>\n"
        f"{status}"
    )


async def _run_and_deliver_zip(
    message: types.Message,
    bot: Bot,
    client: AsyncAnthropic,
    settings: Settings,
    *,
    spec_content: str,
    analysis,
    base_url_override: str | None,
    base_url_label: str,
) -> None:
    if not message.from_user:
        return

    user_id = message.from_user.id
    user_lock = _user_locks[user_id]
    if user_lock.locked():
        await message.answer("Уже идёт генерация. Дождись ZIP в этом чате.")
        return

    async with user_lock:
        if settings.limits_enabled_for(user_id):
            reserve = await reserve_generation(
                settings.usage_store_path,
                user_id,
                settings.tester_max_runs,
            )
            if not reserve.allowed:
                await message.answer(reserve.message or "Лимит генераций исчерпан.")
                return

        async with _pipeline_sem:
            await _run_and_deliver_zip_locked(
                message,
                bot,
                client,
                settings,
                spec_content=spec_content,
                analysis=analysis,
                base_url_override=base_url_override,
                base_url_label=base_url_label,
            )


async def _run_and_deliver_zip_locked(
    message: types.Message,
    bot: Bot,
    client: AsyncAnthropic,
    settings: Settings,
    *,
    spec_content: str,
    analysis,
    base_url_override: str | None,
    base_url_label: str,
) -> None:
    status_msg = await message.answer(
        "<b>Генерация</b>\nОбычно 3–6 мин.",
        parse_mode="HTML",
    )

    async def edit_status(html: str) -> None:
        try:
            await status_msg.edit_text(html, parse_mode="HTML")
        except TelegramBadRequest as exc:
            if "message is not modified" not in str(exc).lower():
                logger.debug("Status edit skipped: %s", exc)

    reporter = StatusReporter(edit_status, heartbeat_sec=20.0)

    try:
        result = await run_pipeline(
            client,
            analysis,
            spec_content,
            settings,
            reporter=reporter,
            base_url_override=base_url_override,
        )

        if settings.maven_validation_strict and not result.delivery_ready:
            zip_note = (
                "В ZIP только отчёты (исходники не включены)."
                if not result.zip_shippable
                else "ZIP отправлен, но не production-ready."
            )
            await message.answer(
                f"Не готово к продакшену. {zip_note} Подробности в ZIP.",
            )

        report_name = (
            "GENERATION_REPORT.txt"
            if result.delivery_ready or result.partial_success
            else "GENERATION_FAILED.txt"
        )
        report_body = _build_report(result, analysis.title, len(analysis.operations))

        if not result.files:
            await message.answer("Не удалось сгенерировать файлы. Попробуй снова.")
            return

        maven_report = None
        if result.maven and not result.maven.passed and not result.maven.skipped:
            maven_report = result.maven.feedback_for_llm(20_000)

        zip_payload = result.files if result.zip_shippable else {}
        zip_bytes = await asyncio.to_thread(
            _build_project_zip_bytes,
            zip_payload,
            report_name=report_name,
            report_body=report_body,
            maven_report=maven_report,
        )

        await message.answer_document(
            document=types.BufferedInputFile(
                zip_bytes,
                filename=f"{analysis.package_hint}-qa-framework.zip",
            ),
            caption=_caption(result, analysis, base_url_used=base_url_label),
            parse_mode="HTML",
        )

        await edit_status("Готово")

    except Exception as exc:
        logger.exception("Pipeline failed")
        await message.answer(f"Ошибка: {exc}")
        await edit_status("Ошибка")

    finally:
        try:
            await status_msg.delete()
        except Exception:
            pass


def register_handlers(dp: Dispatcher, bot: Bot, client: AsyncAnthropic, settings: Settings) -> None:
    @dp.message(Command("start"))
    async def cmd_start(message: types.Message) -> None:
        lines = [
            "<b>QA Gen Bot</b>",
            "OpenAPI (.json) → Java Maven проект с тестами.",
            "",
            "1. Отправь .json",
            "2. Укажи base URL или <code>/skip</code>",
            "",
            "Обычно 3–6 мин. /cancel — отмена",
        ]
        if message.from_user and settings.limits_enabled_for(message.from_user.id):
            status = get_quota_status(
                settings.usage_store_path,
                message.from_user.id,
                settings.tester_max_runs,
            )
            lines.append(
                f"\nТестовый доступ: осталось {status.remaining}/{status.max_runs} генераций."
            )
        await message.answer("\n".join(lines), parse_mode="HTML")

    @dp.message(Command("help"))
    async def cmd_help(message: types.Message) -> None:
        await cmd_start(message)

    @dp.message(Command("cancel"))
    async def cmd_cancel(message: types.Message) -> None:
        if get_pending(message.from_user.id):
            clear_pending(message.from_user.id)
            await message.answer("Отменено. Можешь отправить новый .json")
        else:
            await message.answer("Нечего отменять — сначала отправь .json")

    @dp.message(F.document)
    async def handle_document(message: types.Message) -> None:
        doc = message.document
        if not doc.file_name or not doc.file_name.lower().endswith(".json"):
            await message.answer("Нужен файл .json")
            return

        try:
            file_in_memory = io.BytesIO()
            await bot.download(doc, destination=file_in_memory)
            raw_bytes = file_in_memory.read()

            if len(raw_bytes) > settings.max_spec_chars:
                await message.answer(
                    f"Файл слишком большой. Лимит: {settings.max_spec_chars} байт."
                )
                return

            spec_content = raw_bytes.decode("utf-8-sig")
            analysis = parse_spec_content(spec_content)

            if analysis.error:
                hint = ""
                if analysis.spec_type == SpecType.POSTMAN:
                    hint = "\nЭкспортируй OpenAPI из Postman."
                await message.answer(f"{analysis.error}{hint}")
                return

            from_spec = analysis.base_url or "https://api.example.com/v1"
            set_pending(
                message.from_user.id,
                PendingSpecJob(
                    spec_content=spec_content,
                    analysis=analysis,
                    file_name=doc.file_name,
                ),
            )

            quota_line = ""
            if message.from_user and settings.limits_enabled_for(message.from_user.id):
                status = get_quota_status(
                    settings.usage_store_path,
                    message.from_user.id,
                    settings.tester_max_runs,
                )
                quota_line = (
                    f"\nГенераций осталось: {status.remaining}/{status.max_runs}."
                )

            await message.answer(
                f"Принято: <b>{analysis.title}</b> ({len(analysis.operations)} ops)\n\n"
                f"Пришли base URL или <code>/skip</code>\n"
                f"В спецификации: <code>{from_spec}</code>{quota_line}",
                parse_mode="HTML",
            )

        except Exception as exc:
            logger.exception("Spec intake failed")
            await message.answer(f"Ошибка: {exc}")

    @dp.message(F.text)
    async def handle_base_url_reply(message: types.Message) -> None:
        if not message.from_user or not message.text:
            return

        job = get_pending(message.from_user.id)
        if not job:
            return

        text = message.text.strip()
        base_url_override: str | None = None
        base_url_label: str

        if is_skip_base_url(text):
            base_url_label = job.analysis.base_url or "https://api.example.com/v1"
            await message.answer(
                f"Использую URL из JSON: <code>{base_url_label}</code>",
                parse_mode="HTML",
            )
        else:
            normalized, err = normalize_base_url(text)
            if err:
                await message.answer(
                    f"{err}\nПример: https://api.example.com/v1 или /skip",
                )
                return
            base_url_override = normalized
            base_url_label = normalized
            await message.answer(f"URL: {base_url_label}")

        clear_pending(message.from_user.id)

        await _run_and_deliver_zip(
            message,
            bot,
            client,
            settings,
            spec_content=job.spec_content,
            analysis=job.analysis,
            base_url_override=base_url_override,
            base_url_label=base_url_label,
        )
