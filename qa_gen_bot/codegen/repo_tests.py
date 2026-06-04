"""Deterministic Mode B tests for openapi-generator fluent DefaultApi."""
from __future__ import annotations

import json
import re
from typing import Any

from qa_gen_bot.spec_parser import OperationSummary, SpecAnalysis

_HTTP = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})


def _pascal(s: str) -> str:
    parts = re.split(r"[^a-zA-Z0-9]+", s)
    return "".join(p[:1].upper() + p[1:] for p in parts if p)


def _path_only(path: str) -> str:
    return path.split("?", 1)[0]


def _operation_def(raw: dict[str, Any], op: OperationSummary) -> dict[str, Any]:
    paths = raw.get("paths") or {}
    item = paths.get(_path_only(op.path)) or {}
    return item.get(op.method.lower()) or {}


def _schema_name(ref: str | None) -> str | None:
    if not ref or not ref.startswith("#/components/schemas/"):
        return None
    return ref.rsplit("/", 1)[-1]


def _schemas(raw: dict[str, Any]) -> dict[str, Any]:
    comp = raw.get("components") or {}
    schemas = comp.get("schemas") or {}
    return schemas if isinstance(schemas, dict) else {}


def _model_imports_and_builder(
    schema_name: str | None, schemas: dict[str, Any], pkg: str
) -> tuple[list[str], str]:
    """Return extra model imports and Java statements to build request body."""
    if not schema_name or schema_name not in schemas:
        return [], "        // no request body\n"

    schema = schemas[schema_name]
    if not isinstance(schema, dict):
        return [], ""

    imports: list[str] = [f"import {pkg}.model.{schema_name};"]
    lines: list[str] = [f"        {schema_name} body = new {schema_name}();"]
    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])

    for prop, spec in props.items():
        if not isinstance(spec, dict):
            continue
        setter = f"body.set{_pascal(prop)}("
        if "$ref" in spec:
            ref_name = _schema_name(spec["$ref"])
            if ref_name:
                imports.append(f"import {pkg}.model.{ref_name};")
                nested_var = ref_name[0].lower() + ref_name[1:]
                lines.extend(_nested_object(ref_name, schemas, pkg, nested_var))
                lines.append(f"        body.set{_pascal(prop)}({nested_var});")
            continue
        val = _sample_value(prop, spec, required)
        lines.append(f"        {setter}{val});")

    return imports, "\n".join(lines) + "\n"


def _nested_object(
    name: str, schemas: dict[str, Any], pkg: str, var: str
) -> list[str]:
    schema = schemas.get(name) or {}
    props = schema.get("properties") if isinstance(schema, dict) else {}
    lines = [f"        {name} {var} = new {name}();"]
    if not isinstance(props, dict):
        return lines
    for prop, spec in props.items():
        if isinstance(spec, dict):
            lines.append(
                f"        {var}.set{_pascal(prop)}({_sample_value(prop, spec, set())});"
            )
    return lines


def _sample_value(prop: str, spec: dict[str, Any], required: set[str]) -> str:
    t = spec.get("type")
    if t == "boolean":
        return "true"
    if t == "integer":
        return "1"
    if t == "number":
        return "1.0"
    if t == "string":
        if "header" in prop.lower():
            return "\"QA-Gen-Bot\""
        return "\"test\""
    if t == "array":
        return "java.util.Collections.emptyList()"
    return "\"test\""


def _header_calls(op_def: dict[str, Any]) -> list[tuple[str, str, bool]]:
    """(paramName, fluentMethod, required)"""
    out: list[tuple[str, str, bool]] = []
    for param in op_def.get("parameters") or []:
        if not isinstance(param, dict) or param.get("in") != "header":
            continue
        name = param.get("name") or ""
        required = bool(param.get("required"))
        # X-Test-Header -> xTestHeaderHeader
        parts = re.split(r"[^a-zA-Z0-9]+", name)
        camel = parts[0].lower() + "".join(p.title() for p in parts[1:])
        fluent = f"{camel}Header"
        out.append((name, fluent, required))
    return out


def _query_fluent(param_name: str) -> str:
    """OpenAPI generator: mockId -> mockIdQuery."""
    if re.search(r"[A-Z]", param_name[1:]) and "_" not in param_name and "-" not in param_name:
        return param_name[0].lower() + param_name[1:] + "Query"
    parts = re.split(r"[^a-zA-Z0-9]+", param_name)
    camel = parts[0].lower() + "".join(p.title() for p in parts[1:])
    return f"{camel}Query"


def _query_calls(op_def: dict[str, Any]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for param in op_def.get("parameters") or []:
        if not isinstance(param, dict) or param.get("in") != "query":
            continue
        name = param.get("name") or ""
        out.append((name, _query_fluent(name)))
    return out


def _body_schema_name(op_def: dict[str, Any]) -> str | None:
    rb = op_def.get("requestBody") or {}
    content = rb.get("content") or {}
    app_json = content.get("application/json") or {}
    schema = app_json.get("schema") or {}
    return _schema_name(schema.get("$ref"))


def _stub_response_body() -> str:
    raw = '{"url": "http://localhost/test", "json": {"ok": true}}'
    return raw.replace("\\", "\\\\").replace('"', '\\"')


def _wiremock_test(
    op: OperationSummary,
    op_def: dict[str, Any],
    pkg: str,
    pkg_path: str,
    schemas: dict[str, Any],
) -> str:
    op_id = op.operation_id or _pascal(op.method + op.path)
    class_name = f"WireMock{_pascal(op_id)}Test"
    path = _path_only(op.path)
    wm_method = op.method.lower()
    imports: list[str] = [
        f"package {pkg}.tests;",
        "",
        f"import {pkg}.base.RepoWireMockBaseTest;",
    ]
    model_imports, body_setup = _model_imports_and_builder(
        _body_schema_name(op_def), schemas, pkg
    )
    imports.extend(model_imports)
    imports.extend(
        [
            "import org.junit.jupiter.api.DisplayName;",
            "import org.junit.jupiter.api.Test;",
            "",
            "import static com.github.tomakehurst.wiremock.client.WireMock.aResponse;",
            f"import static com.github.tomakehurst.wiremock.client.WireMock.{wm_method};",
            "import static com.github.tomakehurst.wiremock.client.WireMock.stubFor;",
            "import static com.github.tomakehurst.wiremock.client.WireMock.urlPathEqualTo;",
        ]
    )

    chain = [f"        api().{op_id}()"]
    for _name, fluent, _req in _header_calls(op_def):
        chain.append(f'                .{fluent}("QA-Gen-Bot")')
    for _name, fluent in _query_calls(op_def):
        chain.append(f'                .{fluent}("test-mock")')
    if _body_schema_name(op_def):
        chain.append("                .body(body)")
    chain.append(
        "                .execute(r -> {"
        "\n                    r.then().statusCode(200);"
        "\n                    return r;"
        "\n                });"
    )

    return (
        "\n".join(imports)
        + f"""

@DisplayName("WireMock — {op.method} {path}")
class {class_name} extends RepoWireMockBaseTest {{

    @Test
    void shouldReturn200() {{
        stubFor({wm_method}(urlPathEqualTo("{path}"))
                .willReturn(aResponse()
                        .withStatus(200)
                        .withHeader("Content-Type", "application/json")
                        .withBody("{_stub_response_body()}")));

{body_setup}
"""
        + "\n".join(chain)
        + """
    }
}
"""
    )


def _integration_test(
    op: OperationSummary,
    op_def: dict[str, Any],
    pkg: str,
    schemas: dict[str, Any],
) -> str:
    op_id = op.operation_id or _pascal(op.method + op.path)
    class_name = f"{_pascal(op_id)}IntegrationTest"
    path = _path_only(op.path)
    model_imports, body_setup = _model_imports_and_builder(
        _body_schema_name(op_def), schemas, pkg
    )
    imports = [
        f"package {pkg}.tests;",
        "",
        f"import {pkg}.base.RepoBaseTest;",
        *model_imports,
        "import org.junit.jupiter.api.DisplayName;",
        "import org.junit.jupiter.api.Test;",
    ]
    chain = [f"        api().{op_id}()"]
    for _name, fluent, _req in _header_calls(op_def):
        chain.append(f'                .{fluent}("QA-Gen-Bot")')
    for _name, fluent in _query_calls(op_def):
        chain.append(f'                .{fluent}("test-mock")')
    if _body_schema_name(op_def):
        chain.append("                .body(body)")
    chain.append(
        "                .execute(r -> {"
        "\n                    r.then().statusCode(200);"
        "\n                    return r;"
        "\n                });"
    )

    return (
        "\n".join(imports)
        + f"""

@DisplayName("Integration — {op.method} {path}")
class {class_name} extends RepoBaseTest {{

    @Test
    void shouldCallLiveApi() {{
{body_setup}
"""
        + "\n".join(chain)
        + """
    }
}
"""
    )


def build_repo_tests(
    analysis: SpecAnalysis,
    *,
    uses_wiremock: bool = True,
) -> dict[str, str]:
    """Java test sources that compile against openapi-generator DefaultApi."""
    pkg = f"com.{analysis.package_hint}"
    pkg_path = pkg.replace(".", "/")
    schemas = _schemas(analysis.raw_json)
    files: dict[str, str] = {}

    for op in analysis.operations:
        if op.method not in _HTTP:
            continue
        op_def = _operation_def(analysis.raw_json, op)
        if uses_wiremock:
            rel = f"src/test/java/{pkg_path}/tests/WireMock{_pascal(op.operation_id or 'op')}Test.java"
            files[rel] = _wiremock_test(op, op_def, pkg, pkg_path, schemas)
        rel_int = (
            f"src/test/java/{pkg_path}/tests/"
            f"{_pascal(op.operation_id or 'op')}IntegrationTest.java"
        )
        files[rel_int] = _integration_test(op, op_def, pkg, schemas)

    return files
