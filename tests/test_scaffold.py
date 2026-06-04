"""Tests for scaffold merge."""
from pathlib import Path

from qa_gen_bot.scaffold import (
    build_scaffold,
    is_protected_path,
    merge_with_scaffold,
    put_update_on_collection_body_only,
    uses_operation_centric_client,
)
from qa_gen_bot.spec_parser import parse_spec_content


def test_protected_paths():
    assert is_protected_path("pom.xml")
    assert is_protected_path("src/test/java/com/x/base/BaseTest.java")


def test_scaffold_overrides_bad_pom():
    spec = parse_spec_content(
        '{"openapi":"3.0.0","info":{"title":"Demo","version":"1"},"paths":{"/a":{"get":{}}}}'
    )
    scaffold = build_scaffold(spec)
    llm = {
        "pom.xml": "<project><dependency>allure</dependency></project>",
        "src/test/java/com/demo/tests/T.java": "@Test void t() {}",
    }
    merged = merge_with_scaffold(llm, scaffold)
    assert "allure" not in merged["pom.xml"].lower()
    assert "wiremock-standalone" in merged["pom.xml"]


def test_scaffold_fills_missing_request_dto():
    spec = parse_spec_content(
        '{"openapi":"3.0.0","info":{"title":"Demo","version":"1"},'
        '"paths":{"/products":{"post":{}}}}'
    )
    scaffold = build_scaffold(spec)
    dto_key = next(k for k in scaffold if "/dto/request/" in k)
    merged = merge_with_scaffold({"src/test/java/com/x/tests/T.java": "class T {}"}, scaffold)
    assert dto_key in merged
    assert "class ItemInputDto" in merged[dto_key] or "InputDto" in merged[dto_key]


def test_scaffold_keeps_generated_response_dto():
    spec = parse_spec_content(
        '{"openapi":"3.0.0","info":{"title":"Demo","version":"1"},'
        '"paths":{"/products":{"post":{}}}}'
    )
    scaffold = build_scaffold(spec)
    response_path = "src/main/java/com/demo/dto/response/ProductResponse.java"
    custom = "package com.demo.dto.response; public class ProductResponse {}"
    merged = merge_with_scaffold({response_path: custom}, scaffold)
    assert merged[response_path] == custom


def test_httpbin_nested_object_ref_generates_metric_details_dto():
    spec = parse_spec_content(
        """
{
  "openapi": "3.0.0",
  "info": {"title": "Httpbin Live Testing API", "version": "1"},
  "paths": {
    "/post": {
      "post": {
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {"$ref": "#/components/schemas/PostRequest"}
            }
          }
        },
        "responses": {"200": {"description": "ok"}}
      }
    }
  },
  "components": {
    "schemas": {
      "PostRequest": {
        "type": "object",
        "properties": {
          "slug": {"type": "string"},
          "metrics": {"$ref": "#/components/schemas/MetricDetails"}
        }
      },
      "MetricDetails": {
        "type": "object",
        "properties": {
          "latencyMs": {"type": "integer"}
        }
      }
    }
  }
}
"""
    )
    scaffold = build_scaffold(spec)
    post_dto = next(v for k, v in scaffold.items() if k.endswith("PostInputDto.java"))
    assert "MetricDetailsDto" in post_dto
    assert any(k.endswith("MetricDetailsDto.java") for k in scaffold)


def test_httpbin_fixture_file_generates_nested_dto():
    from pathlib import Path

    raw = Path("fixtures/httpbin-nested-object-ref.json").read_text(encoding="utf-8")
    spec = parse_spec_content(raw)
    scaffold = build_scaffold(spec)
    assert any(k.endswith("MetricDetailsDto.java") for k in scaffold)


def test_order_spec_scaffold_dto_matches_openapi():
    from pathlib import Path

    raw = Path("fixtures/order-management-api.json").read_text(encoding="utf-8")
    spec = parse_spec_content(raw)
    scaffold = build_scaffold(spec)
    dto = next(v for k, v in scaffold.items() if k.endswith("OrderInputDto.java"))
    assert "customerId" in dto
    assert "totalAmount" in dto
    assert "List<OrderItemDto>" in dto
    assert any(k.endswith("OrderItemDto.java") for k in scaffold)
    client = next(v for k, v in scaffold.items() if k.endswith("OrdersApiClient.java"))
    assert "getById(String orderId)" in client


def test_petstore_swagger2_scaffold_nested_definition_dtos():
    from pathlib import Path

    raw = Path("fixtures/petstore-swagger-api.json").read_text(encoding="utf-8")
    spec = parse_spec_content(raw)
    scaffold = build_scaffold(spec)
    assert any(k.endswith("CategoryDto.java") for k in scaffold)
    assert any(k.endswith("TagDto.java") for k in scaffold)
    assert any(k.endswith("OrderInputDto.java") for k in scaffold)
    assert any(k.endswith("UserInputDto.java") for k in scaffold)
    pet_dto = next(v for k, v in scaffold.items() if k.endswith("PetInputDto.java"))
    assert "private Long id;" in pet_dto
    assert "CategoryDto" in pet_dto
    assert "TagDto" in pet_dto
    order_dto = next(v for k, v in scaffold.items() if k.endswith("OrderInputDto.java"))
    assert "petId" in order_dto
    client = next(v for k, v in scaffold.items() if k.endswith("PetApiClient.java"))
    assert "getById(long petId)" in client


def test_scaffold_pom_has_wiremock_and_live_profiles():
    spec = parse_spec_content(
        '{"openapi":"3.0.0","info":{"title":"Demo","version":"1"},'
        '"paths":{"/a":{"get":{}}}}'
    )
    scaffold = build_scaffold(spec)
    pom = scaffold["pom.xml"]
    assert '<profile>' in pom and '<id>wiremock</id>' in pom
    assert '<id>live</id>' in pom
    assert "**/*IntegrationTest.java" in pom


def test_httpbin_live_spec_operation_centric_client():
    raw = Path("fixtures/httpbin-live-testing-api.json").read_text(encoding="utf-8")
    spec = parse_spec_content(raw)
    assert uses_operation_centric_client(spec)
    scaffold = build_scaffold(spec)
    client = next(v for k, v in scaffold.items() if k.endswith("PostApiClient.java"))
    assert "submitTestData" in client
    assert "fetchTestData" in client
    assert 'header("X-Test-Header"' in client
    assert 'get("/get")' in client
    assert "getAll()" not in client
    assert any(k.endswith("MetricDetailsDto.java") for k in scaffold)
    assert any("TestPayloadInputDto" in v for k, v in scaffold.items() if "/dto/request/" in k)


def test_scaffold_protects_request_dto_from_generated_overwrite():
    spec = parse_spec_content(
        '{"openapi":"3.0.0","info":{"title":"Demo","version":"1"},'
        '"paths":{"/products":{"post":{}}}}'
    )
    scaffold = build_scaffold(spec)
    dto_key = next(k for k in scaffold if "/dto/request/" in k)
    custom = "public class CustomDto { private String x; }"
    merged = merge_with_scaffold({dto_key: custom}, scaffold)
    assert merged[dto_key] == scaffold[dto_key]
    assert "CustomDto" not in merged[dto_key]


def test_petstore_update_put_on_collection_not_path_id():
    raw = Path("fixtures/petstore-swagger-api.json").read_text(encoding="utf-8")
    spec = parse_spec_content(raw)
    assert put_update_on_collection_body_only(spec)
    client = next(
        v for k, v in build_scaffold(spec).items() if k.endswith("PetApiClient.java")
    )
    assert "public Response update(PetInputDto body)" in client
    assert '.put(BASE + "/{id}"' not in client
    assert ".put(BASE)" in client
