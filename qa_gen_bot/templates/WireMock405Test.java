package {{PACKAGE}}.tests;

import {{PACKAGE}}.base.WireMockBaseTest;
import io.restassured.http.ContentType;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static com.github.tomakehurst.wiremock.client.WireMock.aResponse;
import static com.github.tomakehurst.wiremock.client.WireMock.post;
import static com.github.tomakehurst.wiremock.client.WireMock.stubFor;
import static com.github.tomakehurst.wiremock.client.WireMock.urlPathEqualTo;
import static io.restassured.RestAssured.given;
import static org.hamcrest.Matchers.equalTo;

@DisplayName("WireMock — HTTP 405")
class WireMock405Test extends WireMockBaseTest {

    @Test
    void shouldReturn405WithErrorBody() {
        stubFor(post(urlPathEqualTo("/{{RESOURCE}}"))
                .willReturn(aResponse()
                        .withStatus(405)
                        .withHeader("Content-Type", "application/json")
                        .withBody("{\"type\":\"error\",\"message\":\"Method Not Allowed\"}")));

        given()
                .spec(wireMockSpec)
                .contentType(ContentType.JSON)
                .body("{}")
                .when()
                .post("/{{RESOURCE}}")
                .then()
                .statusCode(405)
                .body("type", equalTo("error"))
                .body("message", equalTo("Method Not Allowed"));
    }
}
