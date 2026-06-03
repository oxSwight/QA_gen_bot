"""Unit tests for quality_gate."""
from qa_gen_bot.quality_gate import validate_generated_project


_JUNIT = "import org.junit.jupiter.api.Test;\n"

def _minimal_passing_blob() -> dict[str, str]:
    return {
        "pom.xml": "<project><modelVersion>4.0.0</modelVersion></project>",
        "src/main/java/com/x/config/ConfigManager.java": "class ConfigManager {}",
        "src/test/java/com/x/base/BaseTest.java": "RequestSpecBuilder",
        "src/test/java/com/x/base/WireMockBaseTest.java": "WireMockServer",
        "src/test/java/com/x/client/ItemsApiClient.java": """
            import com.x.dto.request.ItemInputDto;
            public class ItemsApiClient {
                public void create(ItemInputDto body) {}
            }
        """,
        "src/main/java/com/x/dto/request/ItemInputDto.java": "public class ItemInputDto {}",
        "src/test/java/com/x/tests/PositiveTest.java": _JUNIT + """
            import static io.restassured.module.jsv.JsonSchemaValidator.matchesJsonSchemaInClasspath;
            class PositiveTest {
                @Test
                void ok() { matchesJsonSchemaInClasspath("schemas/a.json"); }
            }
        """,
        "src/test/java/com/x/tests/NegativeTest.java": _JUNIT + """
            class NegativeTest { @Test void n() {} }
        """,
        "src/test/java/com/x/tests/IntegrationTest.java": _JUNIT + """
            class IntegrationTest { @Test void i() {} }
        """,
        "src/test/java/com/x/tests/WireMock405Test.java": _JUNIT + """
            import static com.github.tomakehurst.wiremock.client.WireMock.get;
            import static com.github.tomakehurst.wiremock.client.WireMock.stubFor;
            import static com.github.tomakehurst.wiremock.client.WireMock.urlPathEqualTo;
            import static com.github.tomakehurst.wiremock.client.WireMock.aResponse;
            import static org.hamcrest.Matchers.equalTo;
            class WireMock405Test {
                @Test
                void methodNotAllowed() {
                    stubFor(get(urlPathEqualTo("/x")).willReturn(aResponse().withStatus(405)));
                    body("m", equalTo("x"));
                }
            }
        """,
        "src/test/resources/schemas/a.json": "{}",
    }


def test_gate_passes_complete_skeleton():
    result = validate_generated_project(_minimal_passing_blob())
    assert result.passed, result.errors


def test_gate_fails_without_tests():
    files = {"pom.xml": "<project/>"}
    result = validate_generated_project(files)
    assert not result.passed
    assert any("@Test" in e for e in result.errors)


def test_gate_forbids_allure():
    files = _minimal_passing_blob()
    files["pom.xml"] += "<dependency>allure</dependency>"
    result = validate_generated_project(files)
    assert not result.passed


def test_gate_fails_missing_nested_request_dto():
    files = _minimal_passing_blob()
    files["src/main/java/com/x/dto/request/ItemInputDto.java"] = """
        package com.x.dto.request;
        public class ItemInputDto {
            private MetricDetailsDto metrics;
        }
    """
    result = validate_generated_project(files)
    assert not result.passed
    assert any("MetricDetailsDto" in e for e in result.errors)


def test_gate_fails_positive_test_on_base_test():
    files = _minimal_passing_blob()
    files["src/test/java/com/x/tests/OrdersPositiveTest.java"] = (
        _JUNIT
        + """
        import com.x.base.BaseTest;
        class OrdersPositiveTest extends BaseTest {
            @Test void live() {}
        }
    """
    )
    result = validate_generated_project(files)
    assert not result.passed
    assert any("IntegrationTest" in e for e in result.errors)
