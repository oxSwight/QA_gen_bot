"""Telegram bot handlers."""
from __future__ import annotations

import asyncio
import io
import logging
from collections import defaultdict
from dataclasses import replace

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest
from anthropic import AsyncAnthropic

from qa_gen_bot.base_url import is_skip_base_url, normalize_base_url
from qa_gen_bot.config import Settings
from qa_gen_bot.core.models import GenerationRequest, GenerationResult
from qa_gen_bot.core.runner import run_generation
from qa_gen_bot.delivery.zip_bundle import build_project_zip_bytes
from qa_gen_bot.generation_mode_ui import (
    mode_keyboard,
    mode_label,
    parse_mode_from_callback,
    parse_mode_from_text,
)
from qa_gen_bot.generation_profile_ui import (
    parse_profile_from_callback,
    parse_profile_from_text,
    profile_keyboard,
    profile_label,
)
from qa_gen_bot.generation_api import GenerationApiError
from qa_gen_bot.pending_jobs import (
    PendingSpecJob,
    clear_pending,
    get_pending,
    set_pending,
    update_pending_mode,
    update_pending_profile,
)
from qa_gen_bot.reporting import human_pipeline_summary
from qa_gen_bot.spec_parser import SpecType, parse_spec_content
from qa_gen_bot.status_reporter import StatusReporter
from qa_gen_bot.metrics import log_run_summary
from qa_gen_bot.usage_limits import get_quota_status_async, reserve_generation

logger = logging.getLogger(__name__)

_pipeline_sem = asyncio.Semaphore(2)
_user_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


def _caption(
    result: GenerationResult,
    analysis,
    *,
    base_url_used: str,
    profile_label: str,
    mode_label_text: str,
) -> str:
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

    summary = human_pipeline_summary(
        result,
        profile_label=profile_label,
        mode_label=mode_label_text,
    )
    return (
        f"<b>{analysis.title}</b>\n"
        f"Профиль: {profile_label}\n"
        f"Режим: {mode_label_text}\n"
        f"URL: <code>{base_url_used}</code>\n"
        f"{status}\n"
        f"<i>{summary.splitlines()[-1]}</i>"
    )


async def _run_and_deliver_zip(
    message: types.Message,
    bot: Bot,
    client: AsyncAnthropic,
    settings: Settings,
    job: PendingSpecJob,
    *,
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

    if not job.ready_for_url:
        await message.answer("Сначала выбери профиль и режим (кнопки выше).")
        return

    run_settings = replace(settings, generation_profile=job.generation_profile)

    async with user_lock:
        if run_settings.limits_enabled_for(user_id):
            reserve = await reserve_generation(
                run_settings.usage_store_path,
                user_id,
                run_settings.tester_max_runs,
            )
            if not reserve.allowed:
                await message.answer(reserve.message or "Лимит генераций исчерпан.")
                return

        async with _pipeline_sem:
            await _run_and_deliver_zip_locked(
                message,
                client,
                run_settings,
                job=job,
                base_url_override=base_url_override,
                base_url_label=base_url_label,
            )


async def _run_and_deliver_zip_locked(
    message: types.Message,
    client: AsyncAnthropic,
    settings: Settings,
    *,
    job: PendingSpecJob,
    base_url_override: str | None,
    base_url_label: str,
) -> None:
    assert job.generation_profile is not None
    assert job.generation_mode is not None

    status_msg = await message.answer(
        "<b>Сборка проекта</b>\nОбычно 3–6 мин.",
        parse_mode="HTML",
    )

    async def edit_status(html: str) -> None:
        try:
            await status_msg.edit_text(html, parse_mode="HTML")
        except TelegramBadRequest as exc:
            if "message is not modified" not in str(exc).lower():
                logger.debug("Status edit skipped: %s", exc)

    reporter = StatusReporter(edit_status, heartbeat_sec=20.0)
    profile_lbl = profile_label(job.generation_profile)
    mode_lbl = mode_label(job.generation_mode)

    try:
        request = GenerationRequest(
            analysis=job.analysis,
            spec_content=job.spec_content,
            generation_profile=job.generation_profile,
            base_url_override=base_url_override,
            mode=job.generation_mode,
        )
        logger.info(
            "Pipeline start user=%s mode=%s profile=%s ops=%s",
            message.from_user.id if message.from_user else "?",
            job.generation_mode,
            job.generation_profile,
            len(job.analysis.operations),
        )
        result = await run_generation(
            client,
            request,
            settings,
            reporter=reporter,
        )
        logger.info(
            "Pipeline done mode=%s delivery_ready=%s files=%s",
            result.mode,
            result.delivery_ready,
            len(result.files),
        )

        if settings.maven_validation_strict and not result.delivery_ready:
            await message.answer(
                "Maven не прошёл — в ZIP проект + отчёты (см. MAVEN_BUILD_REPORT.txt). "
                "Исправь локально или запусти генерацию снова.",
            )

        if not result.files:
            await message.answer("Не удалось сгенерировать файлы. Попробуй снова.")
            log_run_summary(
                mode=job.generation_mode,
                profile=job.generation_profile,
                segment=settings.segment,
                delivery_ready=False,
                elapsed_sec=result.elapsed_sec,
                user_id=message.from_user.id if message.from_user else None,
            )
            return

        suffix = "repo" if job.generation_mode == "repo" else "qa-framework"
        zip_bytes, _report_name = await asyncio.to_thread(
            build_project_zip_bytes,
            result,
            analysis_title=job.analysis.title,
            ops_count=len(job.analysis.operations),
            profile_label=job.generation_profile,
            include_sources=result.static_gate.passed and bool(result.files),
        )

        await message.answer_document(
            document=types.BufferedInputFile(
                zip_bytes,
                filename=f"{job.analysis.package_hint}-{suffix}.zip",
            ),
            caption=_caption(
                result,
                job.analysis,
                base_url_used=base_url_label,
                profile_label=profile_lbl,
                mode_label_text=mode_lbl,
            ),
            parse_mode="HTML",
        )

        await edit_status("Готово")
        log_run_summary(
            mode=job.generation_mode,
            profile=job.generation_profile,
            segment=settings.segment,
            delivery_ready=result.delivery_ready,
            elapsed_sec=result.elapsed_sec,
            user_id=message.from_user.id if message.from_user else None,
        )

    except GenerationApiError as exc:
        logger.error("Generation API failed: %s", exc, exc_info=exc.cause)
        await message.answer(f"Ошибка: {exc}")
        await edit_status("Ошибка сервиса")
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
            "2. Профиль тестов (моки / без моков)",
            "3. Режим (ZIP или Repo/codegen)",
            "4. base URL или <code>/skip</code>",
            "",
            "Обычно 3–6 мин. /cancel — отмена",
        ]
        if message.from_user and settings.limits_enabled_for(message.from_user.id):
            status = await get_quota_status_async(
                settings.usage_store_path,
                message.from_user.id,
                settings.tester_max_runs,
            )
            lines.append(
                f"\nТестовый доступ: осталось {status.remaining}/{status.max_runs} генераций."
            )
        if settings.segment:
            lines.append(f"\nСегмент: <code>{settings.segment}</code>")
        lines.append("\n/status — квота и черновик")
        await message.answer("\n".join(lines), parse_mode="HTML")

    @dp.message(Command("status"))
    async def cmd_status(message: types.Message) -> None:
        if not message.from_user:
            return
        lines: list[str] = ["<b>Статус</b>"]
        if settings.limits_enabled_for(message.from_user.id):
            status = await get_quota_status_async(
                settings.usage_store_path,
                message.from_user.id,
                settings.tester_max_runs,
            )
            lines.append(
                f"Генераций: {status.used}/{status.max_runs} "
                f"(осталось {status.remaining})"
            )
        else:
            lines.append("Лимит генераций к этому аккаунту не применяется.")
        job = get_pending(message.from_user.id)
        if job:
            prof = profile_label(job.generation_profile) if job.generation_profile else "не выбран"
            mod = mode_label(job.generation_mode) if job.generation_mode else "не выбран"
            lines.append(f"Черновик: {job.analysis.title}")
            lines.append(f"Профиль: {prof}")
            lines.append(f"Режим: {mod}")
            if job.ready_for_url:
                lines.append("Жду base URL или /skip")
            elif job.awaiting_mode:
                lines.append("Жду выбор режима (кнопки)")
            else:
                lines.append("Жду выбор профиля (кнопки)")
        else:
            lines.append("Нет активного .json — отправь файл.")
        await message.answer("\n".join(lines), parse_mode="HTML")

    @dp.message(Command("help"))
    async def cmd_help(message: types.Message) -> None:
        await cmd_start(message)

    @dp.message(Command("cancel"))
    async def cmd_cancel(message: types.Message) -> None:
        if message.from_user and get_pending(message.from_user.id):
            clear_pending(message.from_user.id)
            await message.answer("Отменено. Можешь отправить новый .json")
        else:
            await message.answer("Нечего отменять — сначала отправь .json")

    @dp.callback_query(F.data.startswith("genprof:"))
    async def handle_profile_callback(callback: types.CallbackQuery) -> None:
        if not callback.from_user or not callback.data:
            return
        profile = parse_profile_from_callback(callback.data)
        if profile is None:
            await callback.answer("Неизвестный профиль", show_alert=True)
            return

        job = update_pending_profile(callback.from_user.id, profile)
        if job is None:
            await callback.answer("Сначала отправь .json", show_alert=True)
            return

        await callback.answer()
        if callback.message:
            await callback.message.edit_text(
                f"Профиль: <b>{profile_label(profile)}</b>\n\n"
                "<b>Шаг 3.</b> Выбери режим сборки:",
                parse_mode="HTML",
                reply_markup=mode_keyboard(),
            )

    @dp.callback_query(F.data.startswith("genmode:"))
    async def handle_mode_callback(callback: types.CallbackQuery) -> None:
        if not callback.from_user or not callback.data:
            return
        mode = parse_mode_from_callback(callback.data)
        if mode is None:
            await callback.answer("Неизвестный режим", show_alert=True)
            return

        job = update_pending_mode(callback.from_user.id, mode)
        if job is None:
            await callback.answer("Сначала отправь .json", show_alert=True)
            return
        if job.generation_profile is None:
            await callback.answer("Сначала выбери профиль", show_alert=True)
            return

        await callback.answer()
        from_spec = job.analysis.base_url or "https://api.example.com/v1"
        if callback.message:
            await callback.message.edit_text(
                f"Профиль: <b>{profile_label(job.generation_profile)}</b>\n"
                f"Режим: <b>{mode_label(mode)}</b>\n\n"
                f"Пришли base URL или <code>/skip</code>\n"
                f"В спецификации: <code>{from_spec}</code>",
                parse_mode="HTML",
            )

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
                status = await get_quota_status_async(
                    settings.usage_store_path,
                    message.from_user.id,
                    settings.tester_max_runs,
                )
                quota_line = (
                    f"\nГенераций осталось: {status.remaining}/{status.max_runs}."
                )

            await message.answer(
                f"Принято: <b>{analysis.title}</b> ({len(analysis.operations)} ops)\n\n"
                f"<b>Шаг 2.</b> Профиль тестов:{quota_line}",
                parse_mode="HTML",
                reply_markup=profile_keyboard(),
            )

        except Exception as exc:
            logger.exception("Spec intake failed")
            await message.answer(f"Ошибка: {exc}")

    @dp.message(F.text)
    async def handle_text(message: types.Message) -> None:
        if not message.from_user or not message.text:
            return

        job = get_pending(message.from_user.id)
        if not job:
            return

        text = message.text.strip()

        if job.awaiting_profile:
            profile = parse_profile_from_text(text)
            if profile is None:
                await message.answer(
                    "Выбери профиль кнопками или напиши: "
                    "<code>1</code> (без моков) / <code>2</code> (с моками)",
                    parse_mode="HTML",
                )
                return
            update_pending_profile(message.from_user.id, profile)
            await message.answer(
                f"Профиль: {profile_label(profile)}\n\n"
                "Шаг 3 — выбери режим:",
                reply_markup=mode_keyboard(),
            )
            return

        if job.awaiting_mode:
            mode = parse_mode_from_text(text)
            if mode is None:
                await message.answer(
                    "Выбери режим кнопками или напиши: "
                    "<code>zip</code> (быстрый старт) / <code>repo</code> (codegen)",
                    parse_mode="HTML",
                )
                return
            update_pending_mode(message.from_user.id, mode)
            job = get_pending(message.from_user.id)
            assert job and job.generation_mode and job.generation_profile
            from_spec = job.analysis.base_url or "https://api.example.com/v1"
            await message.answer(
                f"Режим: {mode_label(job.generation_mode)}\n\n"
                f"Пришли base URL или /skip\n"
                f"В JSON: {from_spec}",
            )
            return

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
            job,
            base_url_override=base_url_override,
            base_url_label=base_url_label,
        )
