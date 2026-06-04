"""Mode B repo scaffold."""
from qa_gen_bot.codegen.repo_scaffold import build_repo_scaffold
from qa_gen_bot.quality_gate import validate_repo_project
from qa_gen_bot.spec_parser import parse_spec_content

SPEC = """
{
  "openapi": "3.0.0",
  "info": {"title": "Demo", "version": "1"},
  "paths": {"/items": {"get": {"responses": {"200": {"description": "ok"}}}}}
}
"""


def test_repo_scaffold_has_codegen_pom() -> None:
    analysis = parse_spec_content(SPEC)
    files = build_repo_scaffold(analysis, SPEC, uses_wiremock=True)
    pom = files["pom.xml"]
    assert "openapi-generator-maven-plugin" in pom
    assert "library>rest-assured</library>" in pom
    for dep in (
        "com.google.code.gson",
        "io.gsonfire",
        "com.squareup.okio",
        "javax.annotation-api",
        "io.rest-assured",
        "org.slf4j",
    ):
        assert dep in pom, f"missing dependency marker: {dep}"
    assert any("WireMockBaseTest" in p for p in files)
    assert files["src/main/resources/openapi/openapi.json"].strip().startswith("{")


def test_repo_gate_minimal() -> None:
    analysis = parse_spec_content(SPEC)
    files = build_repo_scaffold(analysis, SPEC, uses_wiremock=False)
    pkg = f"com.{analysis.package_hint}".replace(".", "/")
    java_pkg = f"com.{analysis.package_hint}"
    files[f"src/test/java/{pkg}/tests/DemoIntegrationTest.java"] = f"""
import org.junit.jupiter.api.Test;
import {java_pkg}.base.BaseTest;
class DemoIntegrationTest extends BaseTest {{
    @Test void ok() {{}}
}}
"""
    result = validate_repo_project(files, uses_wiremock=False)
    assert result.passed, result.errors
