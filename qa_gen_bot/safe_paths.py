"""Validate relative archive paths (Zip Slip / path traversal protection)."""
from __future__ import annotations

import logging
import re
from pathlib import PurePosixPath

logger = logging.getLogger(__name__)

_INVALID_CHARS_RE = re.compile(r"[\x00-\x1f<>|\"?*]")
_RESERVED_WINDOWS_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


class UnsafePathError(ValueError):
    """Raised when a path cannot be used for disk or ZIP output."""


def normalize_relative_path(path: str) -> str:
    return path.strip().replace("\\", "/")


def is_safe_relative_path(path: str) -> bool:
    """
    Return True if path is safe to write under a project root or ZIP archive.

    Rejects: absolute paths, .. segments, drive letters (C:), NUL/control chars.
    """
    if not path or not path.strip():
        return False

    raw = normalize_relative_path(path)
    if raw.startswith("/"):
        return False
    if _INVALID_CHARS_RE.search(raw):
        return False
    if len(raw) > 512:
        return False

    if re.match(r"^[a-zA-Z]:", raw):
        return False

    parts = PurePosixPath(raw).parts
    if not parts:
        return False
    if ".." in parts:
        return False
    if parts[0] == "..":
        return False

    for part in parts:
        if part in (".", ""):
            continue
        stem = part.split(".")[0].upper()
        if stem in _RESERVED_WINDOWS_NAMES:
            return False

    resolved = PurePosixPath(raw)
    if str(resolved).startswith(".."):
        return False

    return True


def sanitize_relative_path(path: str) -> str | None:
    if not is_safe_relative_path(path):
        return None
    return normalize_relative_path(path)


def filter_safe_file_map(
    files: dict[str, str],
    *,
    context: str = "archive",
) -> tuple[dict[str, str], list[str]]:
    """
    Drop unsafe paths; log each rejection.

    Returns (safe_files, rejected_paths).
    """
    safe: dict[str, str] = {}
    rejected: list[str] = []
    for path, content in files.items():
        clean = sanitize_relative_path(path)
        if clean is None:
            rejected.append(path)
            logger.error(
                "Rejected unsafe path (%s): %r",
                context,
                path,
            )
            continue
        if clean in safe and safe[clean] != content:
            logger.warning(
                "Duplicate safe path %r (%s); keeping last entry",
                clean,
                context,
            )
        safe[clean] = content
    if rejected:
        logger.error(
            "Path filter (%s): rejected %d of %d paths",
            context,
            len(rejected),
            len(files),
        )
    return safe, rejected


def require_safe_file_map(
    files: dict[str, str],
    *,
    context: str = "archive",
) -> dict[str, str]:
    """Fail-fast if any path is unsafe."""
    safe, rejected = filter_safe_file_map(files, context=context)
    if rejected:
        sample = ", ".join(rejected[:5])
        extra = f" (+{len(rejected) - 5} more)" if len(rejected) > 5 else ""
        raise UnsafePathError(
            f"Unsafe paths in {context}: {sample}{extra}"
        )
    return safe
