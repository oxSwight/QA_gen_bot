"""Canonical names from scaffold for generation prompts (must match build_scaffold)."""
from __future__ import annotations

from qa_gen_bot.scaffold import (
    _client_class_name,
    _dto_input_name,
    _primary_resource,
    all_request_dto_class_names,
    nested_request_dto_names,
    put_update_on_collection_body_only,
    uses_operation_centric_client,
)
from qa_gen_bot.spec_parser import SpecAnalysis


def build_scaffold_hints(analysis: SpecAnalysis, *, uses_wiremock: bool = True) -> str:
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
        update_line = (
            "  — update(Dto body): PUT /{resource}, id только в JSON-теле; "
            "WireMock stub на /{resource}, не /{resource}/1\n"
        ).format(resource=resource)
        if not put_update_on_collection_body_only(analysis):
            update_line = (
                "  — getById/delete/update(id, …): id типа long для petId (не String)\n"
            )
        client_hint = (
            f"• ApiClient: {pkg}.client.{client} — getAll, getById, create, update, delete\n"
            f"{update_line}"
        )
    wiremock_lines = ""
    if uses_wiremock:
        wiremock_lines = (
            f"• WireMockBaseTest: {pkg}.base.WireMockBaseTest — stubFor; "
            f"client = new {client}(wireMockSpec)\n"
            "• WireMock405Test — уже есть, не перезаписывай\n"
        )
    else:
        wiremock_lines = (
            "• Профиль integration-only: только BaseTest + *IntegrationTest.java на base.url\n"
            "• НЕ используй WireMock/stubFor/WireMockBaseTest\n"
        )

    return f"""\
=== Scaffold (уже в проекте — НЕ генерируй эти файлы) ===
• Package: {pkg}
{client_hint}  — в тестах: private {client} client;
  — @BeforeEach void init() {{ client = new {client}(requestSpec); }}
{dto_lines}
• User*Test → UserInputDto; Store*Test → OrderInputDto; Pet*Test → {dto}
{nested_line}• НЕ создавай дубликаты *Dto в dto/request/ — используй имена выше (OrderItemDto, не OrderItem).
• BaseTest: {pkg}.base.BaseTest (requestSpec) — интеграционные API-тесты
{wiremock_lines}• Resource path: /{resource}
"""


def build_repo_codegen_hints(analysis: SpecAnalysis, *, uses_wiremock: bool = True) -> str:
    """Hints for Mode B: openapi-generator API packages (not hand-written client)."""
    pkg = f"com.{analysis.package_hint}"
    op_lines = "\n".join(
        f"  — {op.method} {op.path}"
        + (f" (operationId: {op.operation_id})" if op.operation_id else "")
        for op in analysis.operations
    )
    wiremock = ""
    if uses_wiremock:
        wiremock = (
            f"• WireMockBaseTest: {pkg}.base.WireMockBaseTest\n"
            "• WireMock405Test — не перезаписывай\n"
        )
    else:
        wiremock = "• Только *IntegrationTest.java extends BaseTest — без WireMock\n"
    return f"""\
=== Mode B: openapi-generator (НЕ генерируй client/dto/pom) ===
• Package: {pkg}
• После mvn generate-sources:
  - API: {pkg}.api.DefaultApi — fluent Oper (НЕ вызывай api.method(arg1, arg2))
  - Models: {pkg}.model.*
• Пример вызова:
  DefaultApi api = DefaultApi._default(() -> new RequestSpecBuilder().setBaseUri(baseUri)...);
  api.submitTestData().xTestHeaderHeader("h").body(payload).execute(r -> {{ r.then().statusCode(200); return r; }});
  api.fetchTestData().mockIdQuery("id").execute(r -> {{ r.then().statusCode(200); return r; }});
• Тесты в scaffold: RepoWireMockBaseTest / RepoBaseTest + api()
• Операции из спеки:
{op_lines}
{wiremock}• Доп. файлы от API: только src/test/resources/schemas/*.json (опционально)
"""
