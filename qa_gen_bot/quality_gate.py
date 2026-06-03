"""Validate generated framework before shipping ZIP."""
from __future__ import annotations

import re
from dataclasses import dataclass, field


FORBIDDEN_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Allure запрещён", re.compile(r"\ballure\b", re.IGNORECASE)),
    ("aspectjweaver запрещён", re.compile(r"aspectjweaver", re.IGNORECASE)),
    ("aspectj javaagent запрещён", re.compile(r"-javaagent:.*aspectj", re.IGNORECASE)),
    ("TestNG запрещён — только JUnit 5", re.compile(r"org\.testng")),
    ("Неверный пакет base", re.compile(r"\.tests\.base\.")),
    ("PRIVET / prompt injection artifact", re.compile(r"PRIVET\.md", re.IGNORECASE)),
]

_SCHEMA_REF_RE = re.compile(
    r'matchesJsonSchemaInClasspath\s*\(\s*["\']([^"\']+)["\']\s*\)'
)
_DTO_TYPE_RE = re.compile(r"\b([A-Z][A-Za-z0-9]*Dto)\b")
_JAVA_PRIMITIVES = frozenset(
    {"String", "Integer", "Long", "Double", "Boolean", "Void", "Object"}
)
_BASE_TEST_EXTENDS_RE = re.compile(
    r"\bextends\s+(?:\w+\.)*BaseTest\b"
)

@dataclass
class GateResult:
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = []
        if self.errors:
            lines.append("Ошибки:")
            lines.extend(f"  • {e}" for e in self.errors)
        if self.warnings:
            lines.append("Предупреждения:")
            lines.extend(f"  • {w}" for w in self.warnings)
        return "\n".join(lines)


def _all_content(files: dict[str, str]) -> str:
    return "\n".join(files.values())


def _has_path(files: dict[str, str], suffix: str) -> bool:
    return any(p.replace("\\", "/").endswith(suffix) for p in files)


def _java_files(files: dict[str, str]) -> dict[str, str]:
    return {p: c for p, c in files.items() if p.endswith(".java")}


def _has_junit_tests(blob: str) -> bool:
    return "@Test" in blob or "org.junit.jupiter.api.Test" in blob


def _is_test_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return normalized.startswith("src/test/") or "/src/test/" in normalized


def _norm(path: str) -> str:
    return path.replace("\\", "/")


def _request_dto_classes(files: dict[str, str]) -> dict[str, str]:
    """class name -> file path"""
    found: dict[str, str] = {}
    for path, content in _java_files(files).items():
        norm = _norm(path)
        if "/dto/request/" not in norm or not norm.endswith(".java"):
            continue
        m = re.search(r"public\s+(?:final\s+)?class\s+(\w+)\b", content)
        if m:
            found[m.group(1)] = norm
    return found


def _referenced_dto_types(content: str, own_class: str | None = None) -> set[str]:
    refs = set(_DTO_TYPE_RE.findall(content))
    refs -= _JAVA_PRIMITIVES
    if own_class:
        refs.discard(own_class)
    return refs


def _check_request_dto_closure(
    files: dict[str, str], request_dtos: dict[str, str]
) -> list[str]:
    """Every *Dto referenced in dto/request must have a matching .java file."""
    errors: list[str] = []
    for path, content in _java_files(files).items():
        norm = _norm(path)
        if "/dto/request/" not in norm:
            continue
        own = None
        m = re.search(r"public\s+(?:final\s+)?class\s+(\w+)\b", content)
        if m:
            own = m.group(1)
        for dto_type in sorted(_referenced_dto_types(content, own)):
            if dto_type not in request_dtos:
                errors.append(
                    f"{norm}: ссылка на {dto_type}, но нет "
                    f"src/.../dto/request/{dto_type}.java "
                    f"(nested OpenAPI $ref / рассинхрон scaffold)."
                )
    return errors


def _client_getbyid_param_type(files: dict[str, str]) -> str | None:
    for path, content in _java_files(files).items():
        if "/client/" not in _norm(path) or not path.endswith("ApiClient.java"):
            continue
        match = re.search(r"getById\s*\(\s*(\w+)\s+\w+\s*\)", content)
        if match:
            return match.group(1)
    return None


def _check_getbyid_call_type_mismatch(files: dict[str, str]) -> list[str]:
    """client.getById(long) vs getById(\"nonexistent\") — test-compile failure."""
    id_type = _client_getbyid_param_type(files)
    if id_type not in ("long", "int"):
        return []
    errors: list[str] = []
    for path, content in _java_files(files).items():
        if "/tests/" not in _norm(path) or "@Test" not in content:
            continue
        if re.search(r"\.getById\s*\(\s*\"", content):
            errors.append(
                f"{_norm(path)}: getById(String) несовместим с ApiClient.getById({id_type}) — "
                "используй RestAssured given().get(...) или числовой id."
            )
    return errors


def _has_operation_centric_client(files: dict[str, str]) -> bool:
    for path, content in _java_files(files).items():
        if "/client/" not in _norm(path) or not path.endswith("ApiClient.java"):
            continue
        if "projected from OpenAPI operations" in content:
            return True
    return False


def _check_crud_on_operation_client(files: dict[str, str]) -> list[str]:
    """Reject CRUD client calls when scaffold exposes operation-centric methods only."""
    if not _has_operation_centric_client(files):
        return []
    errors: list[str] = []
    crud_re = re.compile(r"\.(getAll|getById|create|update|delete)\s*\(")
    for path, content in _java_files(files).items():
        if "/tests/" not in _norm(path):
            continue
        if crud_re.search(content):
            errors.append(
                f"{_norm(path)}: вызов CRUD-метода, но scaffold client — "
                "operation-centric (методы из operationId)."
            )
    return errors


def _check_base_test_surefire_exposure(files: dict[str, str]) -> list[str]:
    """
    Surefire в pom исключает *IntegrationTest, *NegativeTest, *SchemaTest.
    Класс *PositiveTest на BaseTest попадёт в mvn test → UnknownHost.
    """
    errors: list[str] = []
    for path, content in _java_files(files).items():
        norm = _norm(path)
        if "/tests/" not in norm or not norm.endswith("Test.java"):
            continue
        if "WireMock405Test.java" in norm:
            continue
        if "WireMockBaseTest" in content or "extends WireMockBaseTest" in content:
            continue
        if not _BASE_TEST_EXTENDS_RE.search(content):
            continue
        cm = re.search(r"\bclass\s+(\w+)\b", content)
        if not cm:
            continue
        class_name = cm.group(1)
        if class_name.endswith("IntegrationTest"):
            continue
        if class_name.endswith("NegativeTest") or class_name.endswith("SchemaTest"):
            continue
        errors.append(
            f"{norm}: {class_name} extends BaseTest, но не *IntegrationTest — "
            f"Docker mvn test выполнит live-запрос к base.url."
        )
    return errors


def validate_generated_project(files: dict[str, str]) -> GateResult:
    errors: list[str] = []
    warnings: list[str] = []

    if not files:
        errors.append("Модель не вернула ни одного <file> тега.")
        return GateResult(passed=False, errors=errors)

    if not _has_path(files, "pom.xml"):
        errors.append("Отсутствует pom.xml.")

    if not any("/base/BaseTest.java" in p.replace("\\", "/") for p in files):
        errors.append("Отсутствует scaffold: src/test/.../base/BaseTest.java")

    if not any("/base/WireMockBaseTest.java" in p.replace("\\", "/") for p in files):
        errors.append("Отсутствует scaffold: WireMockBaseTest.java")

    for path, content in _java_files(files).items():
        if path.replace("\\", "/").endswith("/base/BaseTest.java"):
            if re.search(r"\bextends\b", content):
                errors.append("BaseTest.java не должен extends другой класс (cyclic).")
            if "cyclic inheritance" in content.lower():
                errors.append("BaseTest.java повреждён auto-fix.")

    blob = _all_content(files)

    for label, pattern in FORBIDDEN_PATTERNS:
        if pattern.search(blob):
            errors.append(label)

    if not _has_junit_tests(blob):
        errors.append("Нет ни одного метода с @Test.")

    test_class_count = sum(
        1
        for path, content in _java_files(files).items()
        if _is_test_path(path) and _has_junit_tests(content)
    )
    if test_class_count < 1:
        errors.append("Нет тестовых классов в src/test/java с @Test.")
    elif test_class_count < 3:
        errors.append(
            f"Нужно ≥3 тестовых класса (сейчас {test_class_count}): positive, negative, integration/WireMock."
        )

    if "matchesJsonSchemaInClasspath" not in blob and "matchesJsonSchema" not in blob:
        errors.append(
            "Нет JSON Schema валидации (matchesJsonSchemaInClasspath) в тестах."
        )

    if not re.search(r"\b405\b", blob):
        errors.append("Нет негативного сценария с HTTP 405 (WireMock).")

    if "stubFor" not in blob and "WireMock.stubFor" not in blob:
        errors.append("Нет WireMock stubFor в тестах.")

    if re.search(r"import\s+static\s+.*WireMock\.\*", blob):
        errors.append(
            "Запрещён import static WireMock.* — конфликт equalTo с Hamcrest."
        )

    if "StringValuePattern" in blob:
        errors.append(
            "StringValuePattern в тестах — используй org.hamcrest.Matchers.equalTo."
        )

    if re.search(r"RequestSpecification\s+com\.\w+\.base\.BaseTest\.requestSpec", blob):
        errors.append(
            "Сломанный ApiClient: requestSpec в объявлении поля/параметра."
        )

    client_names = set()
    for path, content in _java_files(files).items():
        if "/client/" in path.replace("\\", "/") and path.endswith("ApiClient.java"):
            m = re.search(r"public\s+(?:final\s+)?class\s+(\w+ApiClient)\b", content)
            if m:
                client_names.add(m.group(1))
    if len(client_names) > 1:
        errors.append(f"Несколько ApiClient классов: {client_names}")
    elif len(client_names) == 1:
        expected = next(iter(client_names))
        client_path_suffix = f"/client/{expected}.java"
        if not any(p.replace("\\", "/").endswith(client_path_suffix) for p in files):
            errors.append(f"Нет файла client/{expected}.java (scaffold).")
        for path, content in _java_files(files).items():
            if "/tests/" not in path.replace("\\", "/"):
                continue
            for wrong in re.findall(rf"import\s+com\.\w+\.client\.(\w+ApiClient)\s*;", content):
                if wrong != expected:
                    errors.append(
                        f"Тест {path} импортирует {wrong}, scaffold client: {expected}"
                    )
                    break
    elif not client_names:
        for path, content in _java_files(files).items():
            if "/tests/" in path.replace("\\", "/") and re.search(
                r"import\s+com\.\w+\.client\.\w+ApiClient", content
            ):
                errors.append(
                    f"Тест {path} импортирует ApiClient, но client/*.java отсутствует."
                )
                break

    for path, content in _java_files(files).items():
        if not _is_test_path(path) or "@Test" not in content:
            continue
        if "org.junit.jupiter" not in content:
            errors.append(f"{path}: нет import org.junit.jupiter (только JUnit 5).")
        if re.search(r"\w+ApiClient\.(list|getAll|create|getById)\s*\(", content):
            errors.append(
                f"{path}: статический вызов ApiClient — используй instance client.method()."
            )

    for path, content in _java_files(files).items():
        for schema_ref in _SCHEMA_REF_RE.findall(content):
            ref = schema_ref.replace("\\", "/")
            if not any(
                p.replace("\\", "/").endswith(ref) or p.replace("\\", "/").endswith(
                    f"src/test/resources/{ref}"
                )
                for p in files
            ):
                errors.append(f"{path}: schema {schema_ref!r} не найден в проекте.")

    if "WireMockServer" not in blob and "WireMockBaseTest" not in blob:
        errors.append("Нет базового класса WireMock.")

    for path, content in _java_files(files).items():
        if "WireMockBaseTest" not in content and "extends WireMockBaseTest" not in content:
            continue
        if re.search(r"(?<!\.)\brequestSpec\b", content):
            errors.append(
                f"{path}: WireMock-тест использует requestSpec — нужен wireMockSpec."
            )

    if "ConfigManager" not in blob:
        errors.append("Отсутствует ConfigManager.")

    if "RequestSpecBuilder" not in blob:
        errors.append("RestAssured RequestSpecBuilder не настроен.")

    request_dtos = _request_dto_classes(files)

    if not request_dtos:
        errors.append("Нет request DTO в src/.../dto/request/ (нужен минимум один класс).")

    errors.extend(_check_request_dto_closure(files, request_dtos))
    errors.extend(_check_getbyid_call_type_mismatch(files))
    errors.extend(_check_crud_on_operation_client(files))
    errors.extend(_check_base_test_surefire_exposure(files))

    for path, content in _java_files(files).items():
        if "/client/" not in path.replace("\\", "/") or not path.endswith("ApiClient.java"):
            continue
        missing_dto: set[str] = set()
        for dto_type in re.findall(
            r"(?:create|update)\s*\([^)]*?(\w+)\s+\w+\s*\)", content
        ):
            if dto_type in ("long", "int", "String", "void", "Response"):
                continue
            if dto_type not in request_dtos:
                missing_dto.add(dto_type)
        for dto_type in sorted(missing_dto):
            errors.append(
                f"ApiClient ссылается на {dto_type}, но такого класса нет в dto/request/."
            )

    main_java = {
        p: c for p, c in _java_files(files).items() if p.startswith("src/main/")
    }
    if any("javafaker" in c.lower() or "com.github.javafaker" in c for c in main_java.values()):
        errors.append(
            "JavaFaker в src/main/java — перенеси TestDataGenerator в src/test/java."
        )

    if any("io.restassured" in c for c in main_java.values()):
        errors.append(
            "RestAssured в src/main/java — client должен быть в src/test "
            "или main без rest-assured (scope=test в pom)."
        )

    if any("TestDataGenerator" in p for p in main_java):
        warnings.append("TestDataGenerator лучше держать в src/test/java.")

    if not _has_path(files, "config.properties"):
        warnings.append("Нет src/main/resources/config.properties.")

    schema_files = [p for p in files if "/schemas/" in p.replace("\\", "/") and p.endswith(".json")]
    if not schema_files:
        errors.append("Нет JSON Schema файлов в src/test/resources/schemas/.")

    if "getConnectionTimeout" in blob and "CoreConnectionPNames" not in blob:
        warnings.append(
            "Таймауты объявлены в ConfigManager, но могут не применяться к RestAssured."
        )

    passed = len(errors) == 0
    return GateResult(passed=passed, errors=errors, warnings=warnings)
