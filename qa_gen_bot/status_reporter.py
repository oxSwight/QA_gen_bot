"""Telegram progress updates with elapsed time and heartbeat."""
from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable


StatusCallback = Callable[[str], Awaitable[None]]


class StatusReporter:
    """Edits one status message; sends heartbeat if a step runs too long."""

    def __init__(
        self,
        on_update: StatusCallback,
        *,
        heartbeat_sec: float = 20.0,
        model_label: str = "",
    ) -> None:
        self._on_update = on_update
        self._heartbeat_sec = heartbeat_sec
        self._model_label = model_label
        self._step = "Старт"
        self._detail = ""
        self._started = time.monotonic()
        self._heartbeat_task: asyncio.Task | None = None

    @property
    def elapsed_sec(self) -> int:
        return int(time.monotonic() - self._started)

    async def set_step(self, step: str, detail: str = "") -> None:
        self._step = step
        self._detail = detail
        await self._push()

    async def set_detail(self, detail: str) -> None:
        self._detail = detail
        await self._push()

    async def _push(self) -> None:
        elapsed = self.elapsed_sec
        lines = [
            f"⏳ <b>{self._step}</b>  ({elapsed // 60}:{elapsed % 60:02d})",
        ]
        if self._detail:
            lines.append(self._detail)
        lines.append("<i>Обычно 3–6 мин. Не закрывай чат — пришлю ZIP.</i>")
        if self._model_label:
            lines.append(f"<i>{self._model_label}</i>")
        await self._on_update("\n".join(lines))

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(self._heartbeat_sec)
            await self._push()

    async def start_heartbeat(self) -> None:
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def stop_heartbeat(self) -> None:
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        self._heartbeat_task = None

    async def run_with_heartbeat(self, step: str, detail: str, coro):
        """Run awaitable while refreshing elapsed time every heartbeat_sec."""
        await self.set_step(step, detail)
        await self.start_heartbeat()
        try:
            return await coro
        finally:
            await self.stop_heartbeat()
