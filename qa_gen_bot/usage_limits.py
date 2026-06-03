"""Per-user generation quotas (JSON store; extensible to many users)."""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_STORE_VERSION = 1
_store_lock = asyncio.Lock()


@dataclass(frozen=True)
class QuotaStatus:
    used: int
    max_runs: int

    @property
    def remaining(self) -> int:
        return max(0, self.max_runs - self.used)


@dataclass(frozen=True)
class ReserveResult:
    allowed: bool
    status: QuotaStatus | None = None
    message: str | None = None


def limits_apply_to_user(user_id: int, tester_telegram_id: int | None) -> bool:
    return tester_telegram_id is not None and user_id == tester_telegram_id


def _load_store(path: Path) -> dict:
    if not path.is_file():
        return {"version": _STORE_VERSION, "users": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to read usage store %s: %s", path, exc)
        raise RuntimeError(f"Не удалось прочитать учёт использования: {path}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid usage store format: {path}")
    users = data.get("users")
    if not isinstance(users, dict):
        data["users"] = {}
    return data


def _save_store(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)


def _user_key(user_id: int) -> str:
    return str(user_id)


def _read_status_unlocked(
    data: dict,
    user_id: int,
    max_runs: int,
) -> QuotaStatus:
    users = data["users"]
    key = _user_key(user_id)
    entry = users.get(key)
    if not isinstance(entry, dict):
        return QuotaStatus(used=0, max_runs=max_runs)
    used = int(entry.get("used", 0))
    stored_max = int(entry.get("max_runs", max_runs))
    return QuotaStatus(used=used, max_runs=max(stored_max, max_runs))


def get_quota_status(
    store_path: Path,
    user_id: int,
    max_runs: int,
) -> QuotaStatus:
    data = _load_store(store_path)
    return _read_status_unlocked(data, user_id, max_runs)


async def get_quota_status_async(
    store_path: Path,
    user_id: int,
    max_runs: int,
) -> QuotaStatus:
    return await asyncio.to_thread(get_quota_status, store_path, user_id, max_runs)


def _reserve_sync(
    store_path: Path,
    user_id: int,
    max_runs: int,
) -> ReserveResult:
    data = _load_store(store_path)
    status = _read_status_unlocked(data, user_id, max_runs)

    if status.used >= status.max_runs:
        logger.info(
            "Quota denied user_id=%s used=%s max=%s",
            user_id,
            status.used,
            status.max_runs,
        )
        return ReserveResult(
            allowed=False,
            status=status,
            message=(
                f"Лимит исчерпан: {status.used}/{status.max_runs} генераций.\n"
                "Напиши автору бота, если нужно продление."
            ),
        )

    key = _user_key(user_id)
    data["users"][key] = {
        "used": status.used + 1,
        "max_runs": status.max_runs,
    }
    _save_store(store_path, data)
    new_status = QuotaStatus(used=status.used + 1, max_runs=status.max_runs)
    logger.info(
        "Quota reserved user_id=%s %s/%s",
        user_id,
        new_status.used,
        new_status.max_runs,
    )
    return ReserveResult(allowed=True, status=new_status)


async def reserve_generation(
    store_path: Path,
    user_id: int,
    max_runs: int,
) -> ReserveResult:
    async with _store_lock:
        return await asyncio.to_thread(_reserve_sync, store_path, user_id, max_runs)
