"""Tests for generation quota store."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from qa_gen_bot.usage_limits import (
    get_quota_status,
    limits_apply_to_user,
    reserve_generation,
)


def test_reserve_until_exhausted(tmp_path: Path) -> None:
    store = tmp_path / "usage.json"
    user_id = 42

    async def _run() -> None:
        for i in range(3):
            result = await reserve_generation(store, user_id, max_runs=3)
            assert result.allowed
            assert result.status is not None
            assert result.status.used == i + 1

        blocked = await reserve_generation(store, user_id, max_runs=3)
        assert not blocked.allowed
        assert "Лимит исчерпан" in (blocked.message or "")

        status = get_quota_status(store, user_id, max_runs=3)
        assert status.used == 3
        assert status.remaining == 0

    asyncio.run(_run())


def test_limits_apply_only_to_tester() -> None:
    assert limits_apply_to_user(1, 1)
    assert not limits_apply_to_user(2, 1)
    assert not limits_apply_to_user(1, None)


def test_store_persists(tmp_path: Path) -> None:
    store = tmp_path / "usage.json"
    asyncio.run(reserve_generation(store, 99, max_runs=5))
    data = json.loads(store.read_text(encoding="utf-8"))
    assert data["users"]["99"]["used"] == 1
