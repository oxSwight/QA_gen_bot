"""Unit tests for spec JSON trimming in generator prompts."""
import json

from qa_gen_bot.generator import _SPEC_JSON_MAX_CHARS, _spec_json_for_prompt


def test_spec_json_unchanged_when_small():
    raw = {"openapi": "3.0.0", "info": {"title": "T", "version": "1"}, "paths": {}}
    assert _spec_json_for_prompt(raw) == json.dumps(raw, ensure_ascii=False, indent=2)


def test_spec_json_trims_schemas_when_huge():
    schemas = {f"Schema{i}": {"type": "object", "properties": {f"f{j}": {"type": "string"} for j in range(50)}} for i in range(100)}
    raw = {
        "openapi": "3.0.0",
        "info": {"title": "Big", "version": "1"},
        "paths": {f"/r{i}": {"get": {"responses": {"200": {"description": "ok"}}}} for i in range(500)},
        "components": {"schemas": schemas},
    }
    assert len(json.dumps(raw, ensure_ascii=False, indent=2)) > _SPEC_JSON_MAX_CHARS
    trimmed = _spec_json_for_prompt(raw)
    parsed = json.loads(trimmed)
    assert len(parsed["components"]["schemas"]) == 30
    assert "_note" in parsed["components"]
