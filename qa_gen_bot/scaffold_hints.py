"""Canonical names from scaffold for LLM prompts (must match build_scaffold)."""
from __future__ import annotations

from qa_gen_bot.scaffold import (
    _client_class_name,
    _dto_input_name,
    _primary_resource,
    all_request_dto_class_names,
    nested_request_dto_names,
    uses_operation_centric_client,
)
from qa_gen_bot.spec_parser import SpecAnalysis


def build_scaffold_hints(analysis: SpecAnalysis) -> str:
    pkg = f"com.{analysis.package_hint}"
    resource = _primary_resource(analysis)
    client = _client_class_name(resource)
    dto = _dto_input_name(resource)
    all_dtos = all_request_dto_class_names(analysis)
    dto_lines = "\n".join(
        f"• Request DTO: {pkg}.dto.request.{name}" for name in all_dtos
    )
    nested = nested_request_dto_names(analysis)
    nested_line = ""
    if nested:
        nested_line = (
            "• Nested request DTO (уже в scaffold, имена с суффиксом Dto): "
            + ", ".join(f"{pkg}.dto.request.{n}" for n in nested)
            + "\n"
        )
    if uses_operation_centric_client(analysis):
        op_lines = "\n".join(
            f"  — {op.method} {op.path}"
            + (f" → {op.operation_id}()" if op.operation_id else "")
            for op in analysis.operations
        )
        client_hint = (
            f"• ApiClient: {pkg}.client.{client} — методы = OpenAPI operations (не CRUD):\n"
            f"{op_lines}\n"
            "  — обязательные header/query из спеки — аргументы метода\n"
            "  — НЕ вызывай getAll/getById/create/update/delete (их нет в client)\n"
        )
    else:
        client_hint = (
            f"• ApiClient: {pkg}.client.{client} — только ресурс /{resource} "
            f"(getAll, getById, create, update, delete)\n"
            "  — getById/delete/update: id типа long для petId (не String)\n"
        )
    return f"""\
=== Scaffold (уже в проекте — НЕ генерируй эти файлы) ===
• Package: {pkg}
{client_hint}  — в тестах: private {client} client;
  — @BeforeEach void init() {{ client = new {client}(requestSpec); }}
{dto_lines}
• User*Test → UserInputDto; Store*Test → OrderInputDto; Pet*Test → {dto}
{nested_line}• НЕ создавай дубликаты *Dto в dto/request/ — используй имена выше (OrderItemDto, не OrderItem).
• BaseTest: {pkg}.base.BaseTest (requestSpec) — обычные API-тесты
• WireMockBaseTest: {pkg}.base.WireMockBaseTest — stubFor; client = new {client}(wireMockSpec)
• WireMock405Test — уже есть, не перезаписывай
• Resource path: /{resource}
"""
