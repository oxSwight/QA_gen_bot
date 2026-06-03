from qa_gen_bot.quality_gate import validate_generated_project


def _minimal_with_crud_client():
    return {
        "pom.xml": "<project/>",
        "src/test/java/com/x/base/BaseTest.java": "class BaseTest {}",
        "src/test/java/com/x/base/WireMockBaseTest.java": "class WireMockBaseTest {}",
        "src/test/resources/schemas/a.json": "{}",
        "src/main/java/com/x/dto/request/ItemInputDto.java": "package com.x.dto.request; public class ItemInputDto {}",
        "src/test/java/com/x/client/ItemsApiClient.java": """
            package com.x.client;
            import io.restassured.response.Response;
            public class ItemsApiClient {
                public Response getById(long id) { return null; }
                public Response create(com.x.dto.request.ItemInputDto b) { return null; }
            }
        """,
        "src/test/java/com/x/tests/WireMock405Test.java": "@Test void t405() { assert 405 == 405; }",
        "src/test/java/com/x/tests/ItemWireMockTest.java": """
            import org.junit.jupiter.api.Test;
            import static com.github.tomakehurst.wiremock.client.WireMock.stubFor;
            import static io.restassured.RestAssured.given;
            import static io.restassured.module.jsv.JsonSchemaValidator.matchesJsonSchemaInClasspath;
            class ItemWireMockTest {
                ItemsApiClient client;
                @Test void ok() {
                    stubFor(com.github.tomakehurst.wiremock.client.WireMock.get("/x"));
                    client.getById(1L);
                    given().when().get("/").then().body(matchesJsonSchemaInClasspath("schemas/a.json"));
                }
            }
        """,
        "src/test/java/com/x/tests/ItemIntegrationTest.java": "@Test void live() {}",
        "src/test/java/com/x/tests/ItemNegativeTest.java": "@Test void neg() {}",
        "src/main/java/com/x/config/ConfigManager.java": "class ConfigManager { static ConfigManager getInstance() { return null; } }",
    }


def test_gate_fails_getbyid_string_with_long_client():
    files = _minimal_with_crud_client()
    files["src/test/java/com/x/tests/ItemNegativeTest.java"] = """
        import org.junit.jupiter.api.Test;
        class ItemNegativeTest {
            ItemsApiClient client;
            @Test void missing() { client.getById("nonexistent"); }
        }
    """
    result = validate_generated_project(files)
    assert not result.passed
    assert any("getById(String)" in e for e in result.errors)
