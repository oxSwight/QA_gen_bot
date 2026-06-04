"""Save/load generated file maps for local iteration without API calls."""
from __future__ import annotations

import json
from pathlib import Path


def save_gen_cache(
    path: Path,
    *,
    spec_path: str,
    package_hint: str,
    files: dict[str, str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "spec_path": spec_path,
        "package_hint": package_hint,
        "files": files,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_gen_cache(
    path: Path,
    *,
    expected_package_hint: str | None = None,
) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    files = data.get("files")
    if not isinstance(files, dict):
        raise ValueError(f"Invalid cache {path}: missing 'files' dict")
    hint = data.get("package_hint")
    if expected_package_hint and hint != expected_package_hint:
        raise ValueError(
            f"Cache package_hint={hint!r} does not match spec {expected_package_hint!r}. "
            f"Use --cache fixtures/{expected_package_hint}-gen-cache.json"
        )
    pkg_path = f"com/{expected_package_hint}/" if expected_package_hint else None
    out: dict[str, str] = {}
    for k, v in files.items():
        key = str(k).replace("\\", "/")
        if pkg_path:
            if pkg_path in key:
                out[key] = str(v)
            elif key.startswith("src/test/resources/"):
                out[key] = str(v)
            continue
        out[key] = str(v)
    if expected_package_hint and not out:
        raise ValueError(f"Cache {path} has no files for com.{expected_package_hint}")
    return out
