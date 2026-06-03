"""Filter API output to the allowed zone in Mode B (repo / codegen)."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_ALLOWED_PREFIXES = (
    "src/test/",
    "src/main/resources/schemas/",
)

_FORBIDDEN_FRAGMENTS = (
    "/client/",
    "/dto/",
    "ApiClient.java",
    "pom.xml",
    "openapi.json",
)


def filter_repo_generated_files(files: dict[str, str]) -> dict[str, str]:
    """Keep only test-zone paths; drop hand-written clients/DTO/pom from API output."""
    kept: dict[str, str] = {}
    dropped: list[str] = []
    for path, content in files.items():
        norm = path.replace("\\", "/").lstrip("/")
        if any(norm.startswith(prefix) for prefix in _ALLOWED_PREFIXES):
            if any(frag in norm for frag in _FORBIDDEN_FRAGMENTS if frag != "pom.xml"):
                dropped.append(norm)
                continue
            kept[norm] = content
            continue
        dropped.append(norm)
    if dropped:
        logger.info(
            "Repo file filter: kept %s, dropped %s (%s…)",
            len(kept),
            len(dropped),
            ", ".join(dropped[:4]),
        )
    return kept
