"""Proven Maven scaffold merged with LLM output."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from qa_gen_bot.spec_parser import SpecAnalysis

_TEMPLATES_DIR = Path(__file__).parent / "templates"

# Protected from LLM merge (scaffold always wins)
PROTECTED_SUFFIXES = (
    "pom.xml",
    "src/main/resources/config.properties",
    "src/main/resources/logback.xml",
)

PROTECTED_FRAGMENTS = (
    "/config/ConfigManager.java",
    "/base/BaseTest.java",
    "/base/WireMockBaseTest.java",
    "/tests/WireMock405Test.java",
    "/utils/TestDataGenerator.java",
    "/client/",
    "/dto/request/",
)


def _primary_resource(analysis: SpecAnalysis) -> str:
    for op in analysis.operations:
        parts = op.path.strip("/").split("/")
        if parts and parts[0] and "{" not in parts[0]:
            return parts[0]
    return "items"


def _client_class_name(resource: str) -> str:
    """Path segment products -> ProductsApiClient (plural preserved)."""
    if not resource:
        return "ItemsApiClient"
    parts = re.split(r"[-_]", resource.strip("/"))
    name = "".join(p[:1].upper() + p[1:] for p in parts if p)
    return name + "ApiClient"


def _dto_input_name(resource: str) -> str:
    base = resource.rstrip("s")
    if not base:
        base = resource
    return base[:1].upper() + base[1:] + "InputDto"


def _render(template: str, variables: dict[str, str]) -> str:
    for key, value in variables.items():
        template = template.replace("{{" + key + "}}", value)
    return template


def _load_template(name: str) -> str:
    return (_TEMPLATES_DIR / name).read_text(encoding="utf-8")


def _sample_path(analysis: SpecAnalysis) -> str:
    if analysis.operations:
        path = analysis.operations[0].path
        return path if path.startswith("/") else "/" + path
    return "/health"


_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options"})


def _java_type_for_path_param(analysis: SpecAnalysis, param_name: str) -> str:
    paths = analysis.raw_json.get("paths") or {}
    if not isinstance(paths, dict):
        return "String"
    for path_item in paths.values():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.lower() not in _HTTP_METHODS or not isinstance(operation, dict):
                continue
            for param in operation.get("parameters") or []:
                if not isinstance(param, dict):
                    continue
                if param.get("name") != param_name or param.get("in") != "path":
                    continue
                schema = param.get("schema") or {}
                if isinstance(schema, dict) and schema:
                    if schema.get("format") == "uuid" or schema.get("type") == "string":
                        return "String"
                    if schema.get("type") == "integer":
                        return "long"
                # Swagger 2: type/format on parameter, not under schema
                if param.get("format") == "uuid" or param.get("type") == "string":
                    return "String"
                if param.get("type") == "integer":
                    return "long"
    return "String"


def _resolve_json_ref(root: dict[str, Any], ref: str) -> dict[str, Any] | None:
    if not ref.startswith("#/"):
        return None
    node: Any = root
    for part in ref[2:].split("/"):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node if isinstance(node, dict) else None


def _all_named_schemas(root: dict[str, Any]) -> dict[str, Any]:
    """OpenAPI 3 components.schemas or Swagger 2 definitions."""
    components = root.get("components")
    if isinstance(components, dict):
        schemas = components.get("schemas")
        if isinstance(schemas, dict):
            return schemas
    definitions = root.get("definitions")
    if isinstance(definitions, dict):
        return definitions
    return {}


def _operation_has_json_body(operation: dict[str, Any]) -> bool:
    body = operation.get("requestBody")
    if isinstance(body, dict):
        content = body.get("content") or {}
        if isinstance(content, dict) and "application/json" in content:
            return True
    consumes = operation.get("consumes")
    if isinstance(consumes, list) and any(
        isinstance(c, str) and "json" in c.lower() for c in consumes
    ):
        return True
    for param in operation.get("parameters") or []:
        if isinstance(param, dict) and param.get("in") == "body":
            return True
    return False


def _resolve_schema_named(
    schema: dict[str, Any], root: dict[str, Any]
) -> tuple[str, dict[str, Any]] | None:
    if "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[-1]
        resolved = _resolve_json_ref(root, schema["$ref"])
        return (name, resolved) if isinstance(resolved, dict) else None
    if schema.get("type") == "array":
        items = schema.get("items")
        if isinstance(items, dict):
            return _resolve_schema_named(items, root)
    return ("InlineRequest", schema)


def _extract_post_body_model(
    operation: dict[str, Any], root: dict[str, Any]
) -> tuple[str, dict[str, Any]] | None:
    body = operation.get("requestBody") or {}
    content = (body.get("content") or {}).get("application/json") or {}
    schema = content.get("schema")
    if isinstance(schema, dict):
        return _resolve_schema_named(schema, root)
    for param in operation.get("parameters") or []:
        if not isinstance(param, dict) or param.get("in") != "body":
            continue
        schema = param.get("schema")
        if isinstance(schema, dict):
            return _resolve_schema_named(schema, root)
    return None


def nested_component_dto_name(openapi_schema_name: str) -> str:
    """Map OpenAPI schema name to Java DTO class (e.g. OrderItem -> OrderItemDto)."""
    if openapi_schema_name.endswith("Dto"):
        return openapi_schema_name
    return f"{openapi_schema_name}Dto"


def _schema_type_to_java(schema: dict[str, Any], root: dict[str, Any]) -> str:
    if "$ref" in schema:
        return nested_component_dto_name(schema["$ref"].rsplit("/", 1)[-1])
    t = schema.get("type")
    if t == "string":
        return "String"
    if t == "integer":
        if schema.get("format") == "int64":
            return "Long"
        return "Integer"
    if t == "number":
        return "Double"
    if t == "boolean":
        return "Boolean"
    if t == "array":
        items = schema.get("items")
        if isinstance(items, dict):
            inner = _schema_type_to_java(items, root)
            return f"java.util.List<{inner}>"
        return "java.util.List<String>"
    return "String"


def _find_all_post_request_schemas(analysis: SpecAnalysis) -> dict[str, dict[str, Any]]:
    """All distinct JSON POST body models (Pet, Order, User, …)."""
    found: dict[str, dict[str, Any]] = {}
    paths = analysis.raw_json.get("paths") or {}
    if not isinstance(paths, dict):
        return found
    for path_item in paths.values():
        if not isinstance(path_item, dict):
            continue
        post = path_item.get("post")
        if not isinstance(post, dict) or not _operation_has_json_body(post):
            continue
        resolved = _extract_post_body_model(post, analysis.raw_json)
        if not resolved:
            continue
        key, schema = resolved
        if key not in found:
            found[key] = schema
    return found


def _find_post_request_schema(analysis: SpecAnalysis) -> dict[str, Any] | None:
    all_schemas = _find_all_post_request_schemas(analysis)
    if not all_schemas:
        return None
    resource = _primary_resource(analysis)
    for model_name, schema in all_schemas.items():
        if model_name.lower() == resource.rstrip("s").lower() or model_name.lower() == resource.lower():
            return schema
    return next(iter(all_schemas.values()))


def _input_dto_class_name(model_name: str, primary_dto_input: str, resource: str) -> str:
    if model_name == "InlineRequest":
        return primary_dto_input
    stem = resource.rstrip("s").lower()
    model_lower = model_name.lower()
    if model_lower == stem or model_lower == resource.lower():
        return primary_dto_input
    if model_lower.startswith(stem) or stem in model_lower:
        return primary_dto_input
    if model_name.endswith("Request"):
        base = model_name[: -len("Request")]
        if base.lower() == stem or base.lower().rstrip("s") == stem:
            return primary_dto_input
    return f"{model_name}InputDto"


def _ref_schema_name(schema: dict[str, Any]) -> str | None:
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    return None


def _collect_component_schemas_for_dto(
    request_schema: dict[str, Any], root: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """
    Все components.schemas, на которые ссылается request body ($ref в полях и в items[]).
    Рекурсивно — MetricDetails внутри PostRequest и т.п.
    """
    all_schemas = _all_named_schemas(root)
    if not all_schemas:
        return {}

    found: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    queue: list[dict[str, Any]] = [request_schema]

    while queue:
        current = queue.pop(0)
        for prop_schema in (current.get("properties") or {}).values():
            if not isinstance(prop_schema, dict):
                continue
            ref_names: list[str] = []
            name = _ref_schema_name(prop_schema)
            if name:
                ref_names.append(name)
            if prop_schema.get("type") == "array":
                items = prop_schema.get("items")
                if isinstance(items, dict):
                    item_name = _ref_schema_name(items)
                    if item_name:
                        ref_names.append(item_name)
            for ref_name in ref_names:
                if ref_name in seen:
                    continue
                nested = all_schemas.get(ref_name)
                if not isinstance(nested, dict):
                    continue
                seen.add(ref_name)
                found[ref_name] = nested
                queue.append(nested)
    return found


def _render_dto_java(
    package: str,
    class_name: str,
    schema: dict[str, Any],
    root: dict[str, Any],
) -> str:
    props = schema.get("properties") or {}
    field_lines: list[str] = []
    for name, prop_schema in props.items():
        if not isinstance(prop_schema, dict):
            continue
        java_type = _schema_type_to_java(prop_schema, root)
        field_lines.append(f"    private {java_type} {name};")
    if not field_lines:
        field_lines = ["    private String name;", "    private Integer quantity;"]

    needs_list = any("java.util.List<" in line for line in field_lines)
    imports = "import java.util.List;\n" if needs_list else ""

    return (
        f"package {package}.dto.request;\n\n"
        f"{imports}"
        "import lombok.AllArgsConstructor;\n"
        "import lombok.Builder;\n"
        "import lombok.Data;\n"
        "import lombok.NoArgsConstructor;\n\n"
        f"/**\n * Request body DTO (from OpenAPI request schema).\n */\n"
        "@Data\n@Builder\n@NoArgsConstructor\n@AllArgsConstructor\n"
        f"public class {class_name} {{\n\n"
        + "\n".join(field_lines)
        + "\n}\n"
    )


def _build_request_dto_files(
    analysis: SpecAnalysis, pkg: str, pkg_path: str, dto_input: str
) -> dict[str, str]:
    post_schemas = _find_all_post_request_schemas(analysis)
    if not post_schemas:
        return {
            f"src/main/java/{pkg_path}/dto/request/{dto_input}.java": _render(
                _load_template("DtoInput.java"),
                {"PACKAGE": pkg, "DTO_INPUT": dto_input},
            )
        }

    resource = _primary_resource(analysis)
    files: dict[str, str] = {}
    nested_done: set[str] = set()

    for model_name, schema in post_schemas.items():
        class_name = _input_dto_class_name(model_name, dto_input, resource)
        path = f"src/main/java/{pkg_path}/dto/request/{class_name}.java"
        if path not in files:
            files[path] = _render_dto_java(pkg, class_name, schema, analysis.raw_json)
        for nested_name, nested_schema in _collect_component_schemas_for_dto(
            schema, analysis.raw_json
        ).items():
            nested_class = nested_component_dto_name(nested_name)
            if nested_class in nested_done:
                continue
            nested_done.add(nested_class)
            nested_path = f"src/main/java/{pkg_path}/dto/request/{nested_class}.java"
            if nested_path not in files:
                files[nested_path] = _render_dto_java(
                    pkg, nested_class, nested_schema, analysis.raw_json
                )
    return files


def all_request_dto_class_names(analysis: SpecAnalysis) -> list[str]:
    """All *InputDto class names from POST body schemas (for LLM hints)."""
    post_schemas = _find_all_post_request_schemas(analysis)
    if not post_schemas:
        return [_dto_input_name(_primary_resource(analysis))]
    resource = _primary_resource(analysis)
    primary = _dto_input_name(resource)
    names: list[str] = []
    seen: set[str] = set()
    for model_name in post_schemas:
        class_name = _input_dto_class_name(model_name, primary, resource)
        if class_name not in seen:
            seen.add(class_name)
            names.append(class_name)
    return names


def nested_request_dto_names(analysis: SpecAnalysis) -> list[str]:
    """Nested component DTO names referenced by request bodies."""
    names: list[str] = []
    seen: set[str] = set()
    for schema in _find_all_post_request_schemas(analysis).values():
        for ref_name in _collect_component_schemas_for_dto(schema, analysis.raw_json):
            dto = nested_component_dto_name(ref_name)
            if dto not in seen:
                seen.add(dto)
                names.append(dto)
    return names


def _path_id_metadata(analysis: SpecAnalysis) -> tuple[str, str, str]:
    """(javaType, paramName, restAssuredPathSuffix) e.g. String, orderId, /{orderId}."""
    for op in analysis.operations:
        match = re.search(r"\{([^}]+)\}", op.path)
        if match:
            name = match.group(1)
            java_type = _java_type_for_path_param(analysis, name)
            return java_type, name, f"/{{{name}}}"
    return "long", "id", "/{id}"


def uses_operation_centric_client(analysis: SpecAnalysis) -> bool:
    """
    CRUD-шаблон уместен для primary resource (Petstore /pet).
    Operation-centric — когда есть операции вне primary path и нет CRUD на /{resource}.
    Пример: POST /post + GET /get (httpbin).
    """
    resource = _primary_resource(analysis)
    collection = f"/{resource}"
    id_path_prefix = collection + "/{"

    methods_on_primary: set[str] = set()
    foreign_ops = 0

    for op in analysis.operations:
        path = op.path.rstrip("/") or "/"
        if path == collection or path.startswith(id_path_prefix):
            methods_on_primary.add(op.method.upper())
        else:
            foreign_ops += 1

    if foreign_ops == 0:
        return False

    has_get_on_primary = "GET" in methods_on_primary
    has_mutations_on_primary = methods_on_primary & {"POST", "PUT", "PATCH", "DELETE"}
    has_id_path = any(
        op.path.startswith(id_path_prefix) for op in analysis.operations
    )
    crud_on_primary = has_get_on_primary and (
        bool(has_mutations_on_primary) or has_id_path
    )

    if crud_on_primary:
        return False

    return True


def _java_param_name(api_name: str) -> str:
    parts = re.split(r"[-_]", api_name.strip())
    if not parts:
        return api_name
    head = parts[0].lower()
    tail = "".join(p[:1].upper() + p[1:] for p in parts[1:] if p)
    return head + tail


def _resolve_parameter(
    param: dict[str, Any], root: dict[str, Any]
) -> dict[str, Any] | None:
    if "$ref" in param:
        resolved = _resolve_json_ref(root, param["$ref"])
        if isinstance(resolved, dict):
            return resolved
        return None
    return param


def _param_java_type(param: dict[str, Any], root: dict[str, Any]) -> str:
    schema = param.get("schema") or {}
    if isinstance(schema, dict) and schema:
        return _schema_type_to_java(schema, root)
    if param.get("type") == "integer":
        return "long" if param.get("format") == "int64" else "Integer"
    if param.get("type") == "number":
        return "Double"
    if param.get("type") == "boolean":
        return "Boolean"
    return "String"


def _collect_operation_parameters(
    operation: dict[str, Any],
    path_item: dict[str, Any],
    root: dict[str, Any],
) -> list[dict[str, Any]]:
    """Flatten OpenAPI parameters (path-level + operation-level)."""
    merged: list[dict[str, Any]] = []
    for raw in (path_item.get("parameters") or []) + (operation.get("parameters") or []):
        if not isinstance(raw, dict):
            continue
        param = _resolve_parameter(raw, root) or raw
        name = param.get("name")
        location = param.get("in")
        if not name or not location:
            continue
        merged.append(
            {
                "name": name,
                "in": location,
                "required": bool(param.get("required")),
                "java_type": _param_java_type(param, root),
                "java_name": _java_param_name(name),
            }
        )
    return merged


def _operation_method_name(
    operation: dict[str, Any], method: str, path: str
) -> str:
    op_id = operation.get("operationId")
    if isinstance(op_id, str) and re.match(r"^[a-z][a-zA-Z0-9]*$", op_id):
        return op_id
    segment = path.strip("/").split("/")[-1] or "resource"
    seg_capped = segment[:1].upper() + segment[1:]
    return f"{method.lower()}{seg_capped}"


def _body_dto_for_operation(
    operation: dict[str, Any],
    analysis: SpecAnalysis,
    dto_input: str,
    resource: str,
) -> str | None:
    resolved = _extract_post_body_model(operation, analysis.raw_json)
    if not resolved:
        return None
    model_name, _ = resolved
    return _input_dto_class_name(model_name, dto_input, resource)


def _render_operation_method(
    *,
    method_name: str,
    http_method: str,
    path: str,
    params: list[dict[str, Any]],
    body_dto: str | None,
) -> str:
    args: list[str] = []
    if body_dto:
        args.append(f"{body_dto} body")
    for p in params:
        loc = p["in"]
        if loc in ("header", "query", "path"):
            args.append(f"{p['java_type']} {p['java_name']}")
    signature = ", ".join(args)

    lines = [
        f"    public Response {method_name}({signature}) {{",
        "        var request = given().spec(spec);",
    ]
    for p in params:
        if p["in"] == "header":
            lines.append(
                f'        request = request.header("{p["name"]}", {p["java_name"]});'
            )
        elif p["in"] == "path":
            lines.append(
                f'        request = request.pathParam("{p["name"]}", {p["java_name"]});'
            )
        elif p["in"] == "query":
            if p["required"]:
                lines.append(
                    f'        request = request.queryParam("{p["name"]}", {p["java_name"]});'
                )
            else:
                lines.append(
                    f'        if ({p["java_name"]} != null && !{p["java_name"]}.isBlank()) {{'
                )
                lines.append(
                    f'            request = request.queryParam("{p["name"]}", {p["java_name"]});'
                )
                lines.append("        }")
    if body_dto:
        lines.append("        request = request.body(body);")
    lines.extend(
        [
            "        return request",
            "                .when()",
            f"                .{http_method.lower()}(\"{path}\")",
            "                .then()",
            "                .extract()",
            "                .response();",
            "    }",
        ]
    )
    return "\n".join(lines) + "\n"


def _render_operation_api_client(
    analysis: SpecAnalysis,
    pkg: str,
    client_class: str,
    dto_input: str,
    resource: str,
) -> str:
    paths = analysis.raw_json.get("paths") or {}
    if not isinstance(paths, dict):
        paths = {}

    methods: list[str] = []
    dto_types: set[str] = set()
    for op_summary in analysis.operations:
        path_item = paths.get(op_summary.path) or {}
        if not isinstance(path_item, dict):
            continue
        operation = path_item.get(op_summary.method.lower())
        if not isinstance(operation, dict):
            continue
        params = _collect_operation_parameters(operation, path_item, analysis.raw_json)
        body_dto = None
        if op_summary.method.upper() in ("POST", "PUT", "PATCH"):
            body_dto = _body_dto_for_operation(operation, analysis, dto_input, resource)
            if body_dto:
                dto_types.add(body_dto)
        method_name = _operation_method_name(
            operation, op_summary.method, op_summary.path
        )
        methods.append(
            _render_operation_method(
                method_name=method_name,
                http_method=op_summary.method,
                path=op_summary.path,
                params=params,
                body_dto=body_dto,
            )
        )

    body = "\n".join(methods) if methods else (
        "    // No operations parsed from OpenAPI paths\n"
    )
    dto_imports = "".join(
        f"import {pkg}.dto.request.{name};\n" for name in sorted(dto_types)
    )
    return (
        f"package {pkg}.client;\n\n"
        f"{dto_imports}"
        f"import io.restassured.response.Response;\n"
        "import io.restassured.specification.RequestSpecification;\n\n"
        "import static io.restassured.RestAssured.given;\n\n"
        f"/**\n * API client projected from OpenAPI operations (not CRUD template).\n */\n"
        f"public class {client_class} {{\n\n"
        "    private final RequestSpecification spec;\n\n"
        f"    public {client_class}(RequestSpecification spec) {{\n"
        "        this.spec = spec;\n"
        "    }\n\n"
        f"{body}"
        "}\n"
    )


def _build_api_client_source(
    analysis: SpecAnalysis,
    pkg: str,
    client_class: str,
    dto_input: str,
    resource: str,
    vars_map: dict[str, str],
) -> str:
    if uses_operation_centric_client(analysis):
        return _render_operation_api_client(
            analysis, pkg, client_class, dto_input, resource
        )
    return _render(_load_template("ApiClient.java"), vars_map)


def _normalize_path(path: str) -> str:
    return path.strip().replace("\\", "/")


def is_protected_path(path: str) -> bool:
    p = _normalize_path(path)
    if any(p.endswith(s) for s in PROTECTED_SUFFIXES):
        return True
    return any(fragment in p for fragment in PROTECTED_FRAGMENTS)


def _readme_for_scaffold(analysis: SpecAnalysis, base_url: str, pkg: str) -> str:
    ops_hint = ""
    if uses_operation_centric_client(analysis):
        op_ids = [
            op.operation_id
            for op in analysis.operations
            if op.operation_id
        ]
        if op_ids:
            ops_hint = (
                f"\n- Client methods (from operationId): "
                + ", ".join(f"`{n}()`" for n in op_ids)
                + "\n"
            )
        else:
            ops_hint = "\n- Client: one method per OpenAPI operation (not CRUD).\n"
    return (
        f"# {analysis.title} — QA Framework\n\n"
        "## Maven\n\n"
        "```bash\n"
        "mvn test              # wiremock profile (default): WireMock tests only\n"
        "mvn test -Plive       # *IntegrationTest against base.url\n"
        "mvn test -Pwiremock   # same as default\n"
        "```\n"
        f"{ops_hint}\n"
        f"- Base URL: `{base_url}` (override: `-Dbase.url=...`)\n"
        f"- Package: `{pkg}`\n"
    )


def build_scaffold(
    analysis: SpecAnalysis,
    *,
    base_url_override: str | None = None,
) -> dict[str, str]:
    pkg = f"com.{analysis.package_hint}"
    pkg_path = pkg.replace(".", "/")
    artifact = analysis.package_hint
    base_url = (
        base_url_override
        or analysis.base_url
        or "https://api.example.com/v1"
    )
    sample_path = _sample_path(analysis)
    resource = _primary_resource(analysis)
    client_class = _client_class_name(resource)
    dto_input = _dto_input_name(resource)
    id_java_type, id_param, id_path_suffix = _path_id_metadata(analysis)

    vars_map = {
        "PACKAGE": pkg,
        "PACKAGE_PATH": pkg_path,
        "GROUP_ID": pkg,
        "ARTIFACT_ID": artifact,
        "ARTIFACT_TITLE": analysis.title,
        "BASE_URL": base_url,
        "SAMPLE_PATH": sample_path.lstrip("/"),
        "RESOURCE": resource,
        "CLIENT_CLASS": client_class,
        "DTO_INPUT": dto_input,
        "ID_JAVA_TYPE": id_java_type,
        "ID_PARAM": id_param,
        "ID_PATH_SUFFIX": id_path_suffix,
    }

    files: dict[str, str] = {
        "pom.xml": _render(_load_template("pom.xml"), vars_map),
        "src/main/resources/config.properties": _render(
            _load_template("config.properties"), vars_map
        ),
        "src/main/resources/logback.xml": _load_template("logback.xml"),
        f"src/main/java/{pkg_path}/config/ConfigManager.java": _render(
            _load_template("ConfigManager.java"), vars_map
        ),
        **_build_request_dto_files(analysis, pkg, pkg_path, dto_input),
        f"src/test/java/{pkg_path}/base/BaseTest.java": _render(
            _load_template("BaseTest.java"), vars_map
        ),
        f"src/test/java/{pkg_path}/base/WireMockBaseTest.java": _render(
            _load_template("WireMockBaseTest.java"), vars_map
        ),
        f"src/test/java/{pkg_path}/utils/TestDataGenerator.java": _render(
            _load_template("TestDataGenerator.java"), vars_map
        ),
        f"src/test/java/{pkg_path}/tests/WireMock405Test.java": _render(
            _load_template("WireMock405Test.java"), vars_map
        ),
        f"src/test/java/{pkg_path}/client/{client_class}.java": _build_api_client_source(
            analysis, pkg, client_class, dto_input, resource, vars_map
        ),
        "README.md": _readme_for_scaffold(analysis, base_url, pkg),
    }
    return files


def merge_with_scaffold(
    llm_files: dict[str, str],
    scaffold: dict[str, str],
) -> dict[str, str]:
    """LLM first; scaffold fills gaps; protected paths always from templates."""
    merged = {_normalize_path(k): v for k, v in llm_files.items()}
    for path, content in scaffold.items():
        p = _normalize_path(path)
        if is_protected_path(p) or p not in merged:
            merged[p] = content
    for path, content in scaffold.items():
        if is_protected_path(path):
            merged[_normalize_path(path)] = content
    return merged


def strip_llm_protected(llm_files: dict[str, str]) -> dict[str, str]:
    """Remove protected paths from LLM output before merge (saves tokens in gate)."""
    return {
        p: c
        for p, c in llm_files.items()
        if not is_protected_path(p)
    }
