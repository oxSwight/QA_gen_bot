"""Extract httpbin generated files from out_local ZIP into fixtures cache."""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from qa_gen_bot.gen_cache import save_gen_cache
from qa_gen_bot.scaffold import is_protected_path

ZIP = _ROOT / "out_local" / "httpbinlivetestingapi-qa-framework.zip"
OUT = _ROOT / "fixtures" / "httpbin-gen-cache.json"
SPEC = _ROOT / "fixtures" / "httpbin-live-testing-api.json"
PKG = "com/httpbinlivetestingapi"


def _norm(p: str) -> str:
    return p.replace("\\", "/")


def main() -> None:
    if not ZIP.is_file():
        raise SystemExit(
            f"Missing {ZIP} — run:\n"
            "  python run_local.py --spec fixtures/httpbin-live-testing-api.json "
            "--base-url https://httpbin.org --save-cache"
        )

    files: dict[str, str] = {}
    with zipfile.ZipFile(ZIP) as zf:
        for name in zf.namelist():
            p = _norm(name)
            if "/schemas/" in p and p.endswith(".json"):
                files[p] = zf.read(name).decode("utf-8")
                continue
            if PKG not in p or not p.endswith(".java"):
                continue
            if is_protected_path(p):
                continue
            if "/src/test/java/" in p and "/dto/response/" in p:
                p = p.replace("/src/test/java/", "/src/main/java/", 1)
            if p in files:
                continue
            files[p] = zf.read(name).decode("utf-8")

    save_gen_cache(
        OUT,
        spec_path=str(SPEC),
        package_hint="httpbinlivetestingapi",
        files=files,
    )
    print(f"Wrote {len(files)} files -> {OUT}")


if __name__ == "__main__":
    main()
