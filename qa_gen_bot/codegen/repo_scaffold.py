"""Repo-mode skeleton: spec on disk + openapi-generator pom (Mode B)."""
from __future__ import annotations

from pathlib import Path

from qa_gen_bot.codegen.repo_tests import build_repo_tests
from qa_gen_bot.scaffold import _load_template, _primary_resource, _render, _sample_path
from qa_gen_bot.spec_parser import SpecAnalysis

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


def build_repo_scaffold(
    analysis: SpecAnalysis,
    spec_content: str,
    *,
    base_url_override: str | None = None,
    uses_wiremock: bool = True,
) -> dict[str, str]:
    """
    Files for a repo-oriented layout.

    API client/DTO are produced by openapi-generator into target/generated-sources
    during `mvn generate-sources` — not checked into src/main by the bot.
    """
    pkg = f"com.{analysis.package_hint}"
    artifact = analysis.package_hint
    base_url = (
        base_url_override
        or analysis.base_url
        or "https://api.example.com/v1"
    )
    sample = _sample_path(analysis)
    resource = _primary_resource(analysis)
    vars_map = {
        "PACKAGE": pkg,
        "PACKAGE_PATH": pkg.replace(".", "/"),
        "GROUP_ID": pkg,
        "ARTIFACT_ID": artifact,
        "ARTIFACT_TITLE": analysis.title,
        "BASE_URL": base_url,
        "SAMPLE_PATH": sample.lstrip("/"),
        "RESOURCE": resource,
    }

    pkg_path = vars_map["PACKAGE_PATH"]
    pom = _render(_load_template("pom_repo_codegen.xml"), vars_map)

    files: dict[str, str] = {
        "pom.xml": pom,
        f"src/main/java/{pkg_path}/config/ConfigManager.java": _render(
            _load_template("ConfigManager.java"), vars_map
        ),
        f"src/test/java/{pkg_path}/base/BaseTest.java": _render(
            _load_template("BaseTest.java"), vars_map
        ),
        "src/main/resources/openapi/openapi.json": spec_content,
        "src/main/resources/config.properties": (
            f"base.url={base_url}\n"
            f"sample.path={sample.lstrip('/')}\n"
        ),
        "README.md": (
            f"# {analysis.title} — Repo mode (OpenAPI codegen)\n\n"
            "## Встройка в существующий репозиторий\n\n"
            "1. Скопируй `pom.xml` фрагмент (openapi-generator-maven-plugin) в свой pom.\n"
            "2. Положи `src/main/resources/openapi/openapi.json`.\n"
            "3. `mvn generate-sources` — клиент в `target/generated-sources/openapi/`.\n"
            "4. Тесты в `src/test/java` (от бота) используют сгенерированный API.\n\n"
            f"- Package: `{pkg}`\n"
            f"- base.url: `{base_url}`\n"
        ),
        "REPO_MODE.txt": (
            "Mode B: openapi-generator → target/generated-sources\n"
            "Доп. файлы: только src/test/java\n"
        ),
    }
    if uses_wiremock:
        files[f"src/test/java/{pkg_path}/base/WireMockBaseTest.java"] = _render(
            _load_template("WireMockBaseTest.java"), vars_map
        )
        files[f"src/test/java/{pkg_path}/base/RepoWireMockBaseTest.java"] = _render(
            _load_template("RepoWireMockBaseTest.java"), vars_map
        )
        files[f"src/test/java/{pkg_path}/tests/WireMock405Test.java"] = _render(
            _load_template("WireMock405Test.java"), vars_map
        )
    files[f"src/test/java/{pkg_path}/base/RepoBaseTest.java"] = _render(
        _load_template("RepoBaseTest.java"), vars_map
    )
    files.update(build_repo_tests(analysis, uses_wiremock=uses_wiremock))
    return files
