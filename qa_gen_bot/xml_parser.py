"""Parse LLM XML output into a file map."""
from __future__ import annotations

import re
from dataclasses import dataclass


FILE_TAG_RE = re.compile(
    r'<file\s+path=["\']([^"\']+)["\']\s*>(.*?)</file>',
    re.DOTALL | re.IGNORECASE,
)
ERROR_TAG_RE = re.compile(r"<error>(.*?)</error>", re.DOTALL | re.IGNORECASE)
MANIFEST_TEST_RE = re.compile(
    r"<test_class>([^<]+)</test_class>", re.IGNORECASE,
)


@dataclass
class ParseResult:
    files: dict[str, str]
    test_classes: list[str]
    llm_error: str | None
    raw_text: str


def _normalize_path(path: str) -> str:
    return path.strip().replace("\\", "/")


def _sanitize_path(path: str) -> str | None:
    """Reject path traversal and absolute paths."""
    p = _normalize_path(path)
    if not p or p.startswith("/") or ".." in p.split("/"):
        return None
    if p.startswith("./"):
        p = p[2:]
    return p


def parse_llm_output(text: str) -> ParseResult:
    files: dict[str, str] = {}
    for path, content in FILE_TAG_RE.findall(text):
        safe = _sanitize_path(path)
        if safe:
            files[safe] = content.strip()

    error_match = ERROR_TAG_RE.search(text)
    llm_error = error_match.group(1).strip() if error_match else None

    test_classes = [c.strip() for c in MANIFEST_TEST_RE.findall(text)]

    return ParseResult(
        files=files,
        test_classes=test_classes,
        llm_error=llm_error,
        raw_text=text,
    )


def merge_file_maps(*maps: dict[str, str]) -> dict[str, str]:
    merged: dict[str, str] = {}
    for file_map in maps:
        merged.update(file_map)
    return merged
