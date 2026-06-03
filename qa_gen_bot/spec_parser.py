"""Parse and validate incoming API specification files."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SpecType(str, Enum):
    OPENAPI = "openapi"
    SWAGGER = "swagger"
    POSTMAN = "postman"
    UNKNOWN = "unknown"


@dataclass
class OperationSummary:
    method: str
    path: str
    operation_id: str | None
    summary: str | None


@dataclass
class SpecAnalysis:
    spec_type: SpecType
    title: str
    version: str
    base_url: str | None
    package_hint: str
    operations: list[OperationSummary] = field(default_factory=list)
    raw_json: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


def _slug_package_name(title: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9]+", "", title.lower())
    if not name:
        return "api"
    if name[0].isdigit():
        name = "api" + name
    return name[:24]


def _collect_operations(paths: dict[str, Any]) -> list[OperationSummary]:
    http_methods = {"get", "post", "put", "patch", "delete", "head", "options"}
    ops: list[OperationSummary] = []
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.lower() not in http_methods:
                continue
            if not isinstance(operation, dict):
                continue
            ops.append(
                OperationSummary(
                    method=method.upper(),
                    path=path,
                    operation_id=operation.get("operationId"),
                    summary=operation.get("summary"),
                )
            )
    return ops


def parse_spec_content(content: str) -> SpecAnalysis:
    content = content.strip()
    if not content:
        return SpecAnalysis(
            spec_type=SpecType.UNKNOWN,
            title="",
            version="",
            base_url=None,
            package_hint="api",
            error="Файл пустой.",
        )

    # Strip BOM / leading garbage line (e.g. prompt injection before JSON)
    if not content.startswith("{"):
        first_brace = content.find("{")
        if first_brace == -1:
            return SpecAnalysis(
                spec_type=SpecType.UNKNOWN,
                title="",
                version="",
                base_url=None,
                package_hint="api",
                error="Файл не содержит JSON-объект.",
            )
        content = content[first_brace:]

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        return SpecAnalysis(
            spec_type=SpecType.UNKNOWN,
            title="",
            version="",
            base_url=None,
            package_hint="api",
            error=f"Невалидный JSON: {exc.msg}",
        )

    if not isinstance(data, dict):
        return SpecAnalysis(
            spec_type=SpecType.UNKNOWN,
            title="",
            version="",
            base_url=None,
            package_hint="api",
            error="Корень JSON должен быть объектом.",
        )

    info = data.get("info") or {}
    if isinstance(info, dict):
        schema = str(info.get("schema", ""))
        if "postman.com" in schema:
            return SpecAnalysis(
                spec_type=SpecType.POSTMAN,
                title=str(info.get("name", "Postman Collection")),
                version="",
                base_url=None,
                package_hint="api",
                raw_json=data,
                error=(
                    "Это Postman Collection, а не OpenAPI/Swagger. "
                    "Экспортируй OpenAPI 3.x из Postman (Export → OpenAPI 3.0) "
                    "или возьми официальный swagger.json с API."
                ),
            )

    if "openapi" in data:
        spec_type = SpecType.OPENAPI
        version = str(data["openapi"])
        title = str(info.get("title", "API"))
        paths = data.get("paths") or {}
        servers = data.get("servers") or []
        base_url = servers[0].get("url") if servers else None
    elif "swagger" in data:
        spec_type = SpecType.SWAGGER
        version = str(data["swagger"])
        title = str(info.get("title", "API"))
        paths = data.get("paths") or {}
        host = data.get("host", "")
        base_path = data.get("basePath", "") or ""
        schemes = data.get("schemes") or ["https"]
        scheme = schemes[0] if schemes else "https"
        base_url = f"{scheme}://{host}{base_path}" if host else None
    else:
        return SpecAnalysis(
            spec_type=SpecType.UNKNOWN,
            title="",
            version="",
            base_url=None,
            package_hint="api",
            raw_json=data,
            error=(
                "Не найдены поля 'openapi' или 'swagger'. "
                "Нужен OpenAPI 3.x или Swagger 2.0."
            ),
        )

    operations = _collect_operations(paths if isinstance(paths, dict) else {})
    if not operations:
        return SpecAnalysis(
            spec_type=spec_type,
            title=title,
            version=version,
            base_url=base_url,
            package_hint=_slug_package_name(title),
            raw_json=data,
            error="В спецификации нет HTTP-операций (paths пустой).",
        )

    return SpecAnalysis(
        spec_type=spec_type,
        title=title,
        version=version,
        base_url=base_url,
        package_hint=_slug_package_name(title),
        operations=operations,
        raw_json=data,
    )


def build_spec_brief(analysis: SpecAnalysis, max_ops: int = 40) -> str:
    lines = [
        f"Title: {analysis.title}",
        f"Type: {analysis.spec_type.value} {analysis.version}",
        f"Suggested Java package: com.{analysis.package_hint}",
        f"Base URL: {analysis.base_url or '(set in config.properties)'}",
        f"Operations count: {len(analysis.operations)}",
        "",
        "Operations (implement tests for the most important CRUD/read flows):",
    ]
    for op in analysis.operations[:max_ops]:
        op_id = op.operation_id or "-"
        summary = op.summary or ""
        lines.append(f"  {op.method} {op.path}  id={op_id}  {summary}")
    if len(analysis.operations) > max_ops:
        lines.append(f"  ... and {len(analysis.operations) - max_ops} more")
    return "\n".join(lines)
