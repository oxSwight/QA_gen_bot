"""Parse and normalize API base URL from user input."""
from __future__ import annotations

import re
from urllib.parse import urlparse

_SKIP_RE = re.compile(r"^/(?:skip|пропустить)$", re.IGNORECASE)


def is_skip_base_url(text: str) -> bool:
    return bool(_SKIP_RE.match(text.strip()))


def normalize_base_url(raw: str) -> tuple[str | None, str | None]:
    """
    Returns (normalized_url, error_message).
  Accepts https://host/v1 or host/v1 (adds https://).
    """
    text = raw.strip()
    if not text:
        return None, "URL не может быть пустым."
    if is_skip_base_url(text):
        return None, None

    candidate = text if "://" in text else f"https://{text}"
    parsed = urlparse(candidate)
    if parsed.scheme not in ("http", "https"):
        return None, "Нужен URL с http:// или https://"
    if not parsed.netloc or " " in parsed.netloc:
        return None, "Некорректный URL — укажите хост, например https://dev.company.com/v1"
    if not parsed.hostname:
        return None, "Некорректный URL — укажите хост, например https://dev.company.com/v1"

    path = parsed.path or ""
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    normalized = f"{parsed.scheme}://{parsed.netloc}{path}"
    if parsed.query:
        normalized += f"?{parsed.query}"
    return normalized, None
