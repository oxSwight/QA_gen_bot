"""Tests for GENERATION_PROFILE (contract-mocks vs integration-only)."""
from __future__ import annotations

from qa_gen_bot.quality_gate import validate_generated_project
from qa_gen_bot.scaffold import build_scaffold, is_protected_path
from qa_gen_bot.spec_parser import parse_spec_content
from tests.test_quality_gate import _JUNIT, _minimal_passing_blob


OPENAPI = """
{
  "openapi": "3.0.0",
  "info": {"title": "Demo", "version": "1"},
  "paths": {"/items": {"get": {"responses": {"200": {"description": "ok"}}}}}
}
"""


def test_scaffold_integration_only_omits_wiremock() -> None:
    spec = parse_spec_content(OPENAPI)
    scaffold = build_scaffold(spec, uses_wiremock=False)
    paths = " ".join(scaffold)
    assert "WireMockBaseTest" not in paths
    assert "WireMock405Test" not in paths
    assert "wiremock-standalone" not in scaffold["pom.xml"]
    assert "IntegrationTest" in scaffold["README.md"] or "integration-only" in scaffold["README.md"]


def test_scaffold_contract_includes_wiremock() -> None:
    spec = parse_spec_content(OPENAPI)
    scaffold = build_scaffold(spec, uses_wiremock=True)
    assert any("WireMockBaseTest" in p for p in scaffold)
    assert "wiremock-standalone" in scaffold["pom.xml"]


def test_protected_path_respects_profile() -> None:
    assert is_protected_path("src/test/java/com/x/base/WireMockBaseTest.java", uses_wiremock=True)
    assert not is_protected_path(
        "src/test/java/com/x/base/WireMockBaseTest.java", uses_wiremock=False
    )


def _integration_passing_blob() -> dict[str, str]:
    pkg = "com.x"
    return {
        "pom.xml": "<project><modelVersion>4.0.0</modelVersion></project>",
        "src/main/java/com/x/config/ConfigManager.java": "class ConfigManager {}",
        "src/test/java/com/x/base/BaseTest.java": "RequestSpecBuilder",
        "src/test/java/com/x/client/ItemsApiClient.java": "public class ItemsApiClient {}",
        "src/main/java/com/x/dto/request/ItemInputDto.java": "public class ItemInputDto {}",
        "src/test/java/com/x/tests/ItemsIntegrationTest.java": _JUNIT + """
            import com.x.base.BaseTest;
            class ItemsIntegrationTest extends BaseTest {
                @Test void live() { given().get("/items"); }
            }
        """,
        "src/test/java/com/x/tests/MoreIntegrationTest.java": _JUNIT + """
            import com.x.base.BaseTest;
            class MoreIntegrationTest extends BaseTest {
                @Test void live2() {}
            }
        """,
    }


def test_gate_integration_only_passes_without_wiremock() -> None:
    result = validate_generated_project(
        _integration_passing_blob(), uses_wiremock=False
    )
    assert result.passed, result.errors


def test_gate_integration_only_rejects_wiremock() -> None:
    files = _integration_passing_blob()
    files["src/test/java/com/x/tests/Bad.java"] = _JUNIT + """
        import static com.github.tomakehurst.wiremock.client.WireMock.stubFor;
        class Bad { @Test void x() { stubFor(null); } }
    """
    result = validate_generated_project(files, uses_wiremock=False)
    assert not result.passed
    assert any("WireMock" in e for e in result.errors)


def test_gate_contract_still_requires_wiremock() -> None:
    result = validate_generated_project(_minimal_passing_blob(), uses_wiremock=True)
    assert result.passed, result.errors
