"""Unit tests for spec_parser."""
from qa_gen_bot.spec_parser import SpecType, parse_spec_content


def test_rejects_postman_collection():
    content = """\
line before json
{
  "info": {
    "name": "Test",
    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
  },
  "item": []
}
"""
    analysis = parse_spec_content(content)
    assert analysis.spec_type == SpecType.POSTMAN
    assert analysis.error


def test_accepts_minimal_openapi():
    content = """\
{
  "openapi": "3.0.0",
  "info": {"title": "Demo API", "version": "1.0"},
  "paths": {
    "/pets": {
      "get": {"operationId": "listPets", "responses": {"200": {"description": "ok"}}}
    }
  }
}
"""
    analysis = parse_spec_content(content)
    assert analysis.error is None
    assert analysis.spec_type == SpecType.OPENAPI
    assert len(analysis.operations) == 1
    assert analysis.package_hint == "demoapi"
