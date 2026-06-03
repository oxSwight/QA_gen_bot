"""Build fixtures/order-management-gen-cache.json for local runs without API calls."""
from __future__ import annotations

import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_PKG = "com.ordermanagementserviceap"
_PP = _PKG.replace(".", "/")


def _p(suffix: str) -> str:
    return suffix.replace("{{PP}}", _PP).replace("{{PKG}}", _PKG)


FILES = {
    _p("src/main/java/{{PP}}/dto/response/OrderResponse.java"): f"""\
package {_PKG}.dto.response;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class OrderResponse {{
    private String orderId;
    private String status;
    private String createdAt;
    private Double totalAmount;
}}
""",
    _p("src/test/java/{{PP}}/tests/OrderCreatePositiveTest.java"): f"""\
package {_PKG}.tests;

import {_PKG}.base.WireMockBaseTest;
import {_PKG}.client.OrdersApiClient;
import {_PKG}.dto.request.OrderInputDto;
import io.restassured.response.Response;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static com.github.tomakehurst.wiremock.client.WireMock.aResponse;
import static com.github.tomakehurst.wiremock.client.WireMock.post;
import static com.github.tomakehurst.wiremock.client.WireMock.stubFor;
import static com.github.tomakehurst.wiremock.client.WireMock.urlPathEqualTo;
import static io.restassured.module.jsv.JsonSchemaValidator.matchesJsonSchemaInClasspath;
import static org.hamcrest.Matchers.equalTo;

class OrderCreatePositiveTest extends WireMockBaseTest {{
    private OrdersApiClient client;

    @BeforeEach
    void init() {{
        client = new OrdersApiClient(wireMockSpec);
    }}

    @Test
    void createOrderMatchesSchema() {{
        stubFor(post(urlPathEqualTo("/orders"))
                .willReturn(aResponse()
                        .withStatus(201)
                        .withHeader("Content-Type", "application/json")
                        .withBody("{{\\"orderId\\":\\"a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d\\","
                                + "\\"status\\":\\"PROCESSING\\",\\"totalAmount\\":150.5}}")));

        OrderInputDto body = OrderInputDto.builder()
                .customerId("d3b07384-d113-4956-d5f7-183059abc123")
                .totalAmount(150.5)
                .build();
        Response r = client.create(body);
        r.then()
                .statusCode(201)
                .body(matchesJsonSchemaInClasspath("schemas/order-response.json"))
                .body("status", equalTo("PROCESSING"));
    }}
}}
""",
    _p("src/test/java/{{PP}}/tests/OrderGetWireMockTest.java"): f"""\
package {_PKG}.tests;

import {_PKG}.base.WireMockBaseTest;
import {_PKG}.client.OrdersApiClient;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static com.github.tomakehurst.wiremock.client.WireMock.aResponse;
import static com.github.tomakehurst.wiremock.client.WireMock.get;
import static com.github.tomakehurst.wiremock.client.WireMock.stubFor;
import static com.github.tomakehurst.wiremock.client.WireMock.urlPathEqualTo;
import static org.hamcrest.Matchers.equalTo;

class OrderGetWireMockTest extends WireMockBaseTest {{
    private OrdersApiClient client;

    @BeforeEach
    void init() {{
        client = new OrdersApiClient(wireMockSpec);
    }}

    @Test
    void getOrderById() {{
        String orderId = "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d";
        stubFor(get(urlPathEqualTo("/orders/" + orderId))
                .willReturn(aResponse()
                        .withStatus(200)
                        .withHeader("Content-Type", "application/json")
                        .withBody("{{\\"orderId\\":\\"" + orderId + "\\",\\"status\\":\\"PENDING\\"}}")));

        client.getById(orderId).then()
                .statusCode(200)
                .body("orderId", equalTo(orderId));
    }}
}}
""",
    _p("src/test/java/{{PP}}/tests/OrderNotFoundTest.java"): f"""\
package {_PKG}.tests;

import {_PKG}.base.WireMockBaseTest;
import {_PKG}.client.OrdersApiClient;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static com.github.tomakehurst.wiremock.client.WireMock.aResponse;
import static com.github.tomakehurst.wiremock.client.WireMock.get;
import static com.github.tomakehurst.wiremock.client.WireMock.stubFor;
import static com.github.tomakehurst.wiremock.client.WireMock.urlPathEqualTo;

class OrderNotFoundTest extends WireMockBaseTest {{
    private OrdersApiClient client;

    @BeforeEach
    void init() {{
        client = new OrdersApiClient(wireMockSpec);
    }}

    @Test
    void missingOrderReturns404() {{
        String orderId = "00000000-0000-0000-0000-000000000099";
        stubFor(get(urlPathEqualTo("/orders/" + orderId))
                .willReturn(aResponse().withStatus(404)));

        client.getById(orderId).then().statusCode(404);
    }}
}}
""",
    "src/test/resources/schemas/order-response.json": """\
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["orderId", "status"],
  "properties": {
    "orderId": { "type": "string" },
    "status": { "type": "string" },
    "createdAt": { "type": "string" },
    "totalAmount": { "type": "number" }
  }
}
""",
}


def main() -> None:
    out = _ROOT / "fixtures" / "order-management-gen-cache.json"
    payload = {
        "version": 1,
        "spec_path": "fixtures/order-management-api.json",
        "package_hint": "ordermanagementserviceap",
        "files": FILES,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(FILES)} files -> {out}")


if __name__ == "__main__":
    main()
