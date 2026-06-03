"""CLI: verify schema refs in a cached LLM run resolve to files on disk."""
from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from qa_gen_bot.llm_cache import load_llm_cache
from qa_gen_bot.pipeline import _finalize_files
from qa_gen_bot.scaffold import build_scaffold
from qa_gen_bot.spec_parser import parse_spec_content

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--spec",
        type=Path,
        default=_ROOT / "fixtures" / "httpbin-live-testing-api.json",
        help="OpenAPI fixture used to build scaffold",
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=_ROOT / "out_local" / "llm_cache.json",
        help="LLM cache JSON from run_local.py --save-cache",
    )
    args = parser.parse_args()

    spec_content = args.spec.read_text(encoding="utf-8-sig")
    analysis = parse_spec_content(spec_content)
    if analysis.error:
        raise SystemExit(f"Invalid spec: {analysis.error}")

    scaffold = build_scaffold(analysis)
    pkg = f"com.{analysis.package_hint}"
    llm = load_llm_cache(args.cache, expected_package_hint=analysis.package_hint)
    files, gate = _finalize_files(llm, scaffold, True, pkg, [])

    logger.info("static gate passed=%s", gate.passed)
    schema_paths = [p for p in files if "/schemas/" in p.replace("\\", "/")]
    logger.info("schema files: %s", schema_paths)

    refs: set[str] = set()
    for content in files.values():
        refs.update(re.findall(r"schemas/[A-Za-z0-9_.-]+", content))

    missing = [
        r
        for r in sorted(refs)
        if not any(
            p.replace("\\", "/").endswith(r.split("/", 1)[1]) for p in files
        )
    ]
    if missing:
        logger.error("unresolved schema refs: %s", missing)
        raise SystemExit(1)
    logger.info("all %s schema refs resolved", len(refs))


if __name__ == "__main__":
    main()
