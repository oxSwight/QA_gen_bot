"""Deterministic fixes before/after Maven (no API calls)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field


_WIREMOCK_STAR = re.compile(
    r"import\s+static\s+com\.github\.tomakehurst\.wiremock\.client\.WireMock\.\*;\s*\n?"
)
_MATCHERS_STAR = re.compile(
    r"import\s+static\s+org\.hamcrest\.Matchers\.\*;\s*\n?"
)
# assertThat(x, equalTo(y)) / .body("k", equalTo(v)) — force Hamcrest
_HAMCREST_EQUAL_TO = "org.hamcrest.Matchers.equalTo"


@dataclass
class FixResult:
    files: dict[str, str]
    applied: list[str] = field(default_factory=list)


def _norm(path: str) -> str:
    return path.replace("\\", "/")


def _uses_restassured(content: str) -> bool:
    return "io.restassured" in content or "restassured" in content.lower()


def fix_wiremock_hamcrest_import_clash(files: dict[str, str]) -> FixResult:
    """
    WireMock.* and Matchers.* both export equalTo/containing/etc.
    RestAssured .body() needs org.hamcrest.Matchers, not StringValuePattern.
    """
    out = dict(files)
    applied: list[str] = []

    for path, content in list(out.items()):
        p = _norm(path)
        if not p.endswith(".java") or not p.startswith("src/test/"):
            continue
        if "/base/" in p:
            continue

        original = content
        if not (_WIREMOCK_STAR.search(content) or "StringValuePattern" in content):
            # Still fix bare equalTo in RA tests when WireMock star was present
            if "WireMock" not in content and "equalTo(" not in content:
                continue

        content = _WIREMOCK_STAR.sub("", content)
        content = _MATCHERS_STAR.sub("", content)

        if "stubFor" in content or "urlPathEqualTo" in content:
            wiremock_static = (
                "import static com.github.tomakehurst.wiremock.client.WireMock.aResponse;\n"
                "import static com.github.tomakehurst.wiremock.client.WireMock.get;\n"
                "import static com.github.tomakehurst.wiremock.client.WireMock.post;\n"
                "import static com.github.tomakehurst.wiremock.client.WireMock.put;\n"
                "import static com.github.tomakehurst.wiremock.client.WireMock.delete;\n"
                "import static com.github.tomakehurst.wiremock.client.WireMock.stubFor;\n"
                "import static com.github.tomakehurst.wiremock.client.WireMock.urlPathEqualTo;\n"
            )
            content = _insert_after_package(content, wiremock_static)

        if "equalTo(" in content or "assertThat(" in content:
            content = _insert_after_package(
                content,
                f"import static {_HAMCREST_EQUAL_TO};\n",
            )

        # Qualify ambiguous matchers in RestAssured / Hamcrest usages
        content = re.sub(
            r"\.body\(\s*\"([^\"]+)\"\s*,\s*equalTo\(",
            rf'.body("\1", {_HAMCREST_EQUAL_TO}(',
            content,
        )
        content = re.sub(
            r"assertThat\(\s*([^,]+)\s*,\s*equalTo\(",
            rf"assertThat(\1, {_HAMCREST_EQUAL_TO}(",
            content,
        )

        if content != original:
            out[path] = content
            applied.append(f"WireMock/Hamcrest imports in {p}")

    return FixResult(files=out, applied=applied)


def _insert_after_package(content: str, block: str) -> str:
    if block.strip() in content:
        return content
    m = re.search(r"^package\s+[\w.]+\s*;\s*\n", content, re.MULTILINE)
    if not m:
        return block + content
    pos = m.end()
    return content[:pos] + "\n" + block + content[pos:]


def remove_broken_wiremock_tests(files: dict[str, str]) -> FixResult:
    """Drop generated *WireMock* tests that confuse matchers (scaffold 405 remains)."""
    out = dict(files)
    applied: list[str] = []
    for path, content in list(files.items()):
        p = _norm(path)
        name = p.split("/")[-1]
        if name == "WireMock405Test.java":
            continue
        if "WireMock" in name and "Test.java" in name and "StringValuePattern" in content:
            del out[path]
            applied.append(f"Removed broken {name}")
    return FixResult(files=out, applied=applied)


def fix_base_class_extends(files: dict[str, str], base_package: str) -> FixResult:
    out = dict(files)
    applied: list[str] = []
    base_fqn = f"{base_package}.base.BaseTest"
    wire_fqn = f"{base_package}.base.WireMockBaseTest"

    for path, content in list(out.items()):
        p = _norm(path)
        if not p.endswith(".java") or not p.startswith("src/test/"):
            continue
        if "/base/" in p:
            continue

        original = content
        if re.search(r"\bextends\s+BaseTest\b", content):
            content = re.sub(r"\bextends\s+BaseTest\b", f"extends {base_fqn}", content)
        if re.search(r"\bextends\s+WireMockBaseTest\b", content):
            content = re.sub(
                r"\bextends\s+WireMockBaseTest\b",
                f"extends {wire_fqn}",
                content,
            )

        if content != original:
            out[path] = content
            applied.append(f"FQN extends in {p}")

    return FixResult(files=out, applied=applied)


def _fix_client_file(content: str, base_package: str) -> str:
    """Only replace .spec(requestSpec); strip invalid types from bad autofix."""
    spec_ref = f"{base_package}.base.BaseTest.requestSpec"
    escaped = re.escape(spec_ref)

    content = re.sub(
        rf"^\s*private\s+final\s+RequestSpecification\s+{escaped}\s*;\s*\n",
        "",
        content,
        flags=re.MULTILINE,
    )
    content = re.sub(
        rf"public\s+\w+ApiClient\s*\(\s*RequestSpecification\s+{escaped}\s*\)\s*\{{[^}}]*\}}\s*\n",
        "",
        content,
    )
    content = re.sub(r"\.spec\(\s*requestSpec\s*\)", f".spec({spec_ref})", content)
    content = re.sub(
        rf"RequestSpecification\s+{escaped}",
        "RequestSpecification spec",
        content,
    )
    return content


def _is_base_scaffold_file(path: str) -> bool:
    p = _norm(path)
    return (
        p.endswith("BaseTest.java")
        or p.endswith("WireMockBaseTest.java")
        or "/base/" in p
    )


def fix_request_spec_reference(files: dict[str, str], base_package: str) -> FixResult:
    """Tests extend BaseTest; clients use BaseTest.requestSpec (public static)."""
    out = dict(files)
    applied: list[str] = []
    base_fqn = f"{base_package}.base.BaseTest"
    spec_ref = f"{base_fqn}.requestSpec"

    for path, content in list(out.items()):
        p = _norm(path)
        if not p.endswith(".java") or "requestSpec" not in content:
            continue
        if _is_base_scaffold_file(p):
            continue

        original = content

        if "/client/" in p.lower() or "Client.java" in p:
            content = _fix_client_file(content, base_package)
        elif re.search(rf"\bextends\s+{re.escape(base_fqn)}\b", content):
            pass
        elif re.search(r"\bextends\s+\w+", content):
            pass
        else:
            content = re.sub(
                r"(class\s+\w+)(\s*\{)",
                rf"\1 extends {base_fqn}\2",
                content,
                count=1,
            )

        if content != original:
            out[path] = content
            applied.append(f"requestSpec fix in {p}")

    return FixResult(files=out, applied=applied)


def restore_scaffold_base_files(
    files: dict[str, str],
    scaffold: dict[str, str],
) -> FixResult:
    """Re-apply base classes after auto-fix — they must never be mutated."""
    out = dict(files)
    applied: list[str] = []
    for path, content in scaffold.items():
        if _is_base_scaffold_file(path):
            out[_norm(path)] = content
            applied.append(f"Restored {path}")
    return FixResult(files=out, applied=applied)


def align_packages_to_path(files: dict[str, str], base_package: str) -> FixResult:
    out = dict(files)
    applied: list[str] = []
    pkg_re = re.compile(r"^package\s+([\w.]+)\s*;", re.MULTILINE)

    for path, content in list(out.items()):
        p = _norm(path)
        if not p.endswith(".java"):
            continue
        marker = "/src/test/java/"
        if marker in p:
            rel = p.split(marker, 1)[1]
        elif "/src/main/java/" in p:
            rel = p.split("/src/main/java/", 1)[1]
        else:
            continue
        expected = rel[: -len(".java")].replace("/", ".")
        if not expected.startswith("com."):
            continue
        m = pkg_re.search(content)
        if m and m.group(1) != expected:
            out[path] = pkg_re.sub(f"package {expected};", content, count=1)
            applied.append(f"package fix in {p}")

    return FixResult(files=out, applied=applied)


def move_restassured_clients_to_test(files: dict[str, str]) -> FixResult:
    out = dict(files)
    applied: list[str] = []
    to_move: list[tuple[str, str]] = []

    for path, content in list(out.items()):
        p = _norm(path)
        if not p.endswith(".java") or not p.startswith("src/main/"):
            continue
        if "/client/" not in p.lower() and "Client.java" not in p:
            continue
        if _uses_restassured(content):
            to_move.append((path, p.replace("src/main/java/", "src/test/java/", 1)))

    for old, new in to_move:
        out[new] = out.pop(old)
        applied.append(f"Moved {old} → {new}")

    return FixResult(files=out, applied=applied)


def autofix_from_maven_log(
    files: dict[str, str],
    log: str,
    base_package: str,
    *,
    uses_wiremock: bool = True,
) -> FixResult:
    applied: list[str] = []
    current = files

    fixes = []
    if (
        "org.testng" in log
        or "tests.base" in log
        or "cannot find symbol" in log
        or "ProductsApiClient" in log
        or "ApiClient" in log
    ):
        fixes.extend(
            [
                lambda f: normalize_junit_and_base_imports(f, base_package),
                lambda f: sync_api_client_class_name(f),
                lambda f: sync_client_dto_type(f, base_package),
            ]
        )
    if "ProductInputDto" in log or "InputDto" in log or "dto.request" in log:
        fixes.append(lambda f: sync_client_dto_type(f, base_package))
    if "PetInputDto" in log and (
        "username" in log or "petId" in log or "incompatible types" in log
    ):
        fixes.append(lambda f: align_request_dto_in_tests(f, base_package))
    if "long cannot be converted to java.lang.Integer" in log:
        fixes.append(strip_long_literals_in_tests)
    if "int cannot be converted to java.lang.Long" in log:
        fixes.append(suffix_long_literals_in_dto_builders)
    if "incompatible types" in log and "getById" in log:
        fixes.append(fix_getbyid_string_literal_calls)
    if "Dto" in log and "cannot find symbol" in log:
        fixes.append(sync_component_dto_suffix)
    if "UnknownHost" in log or "Errors:" in log:
        fixes.append(lambda f: rename_base_tests_to_integration(f, base_package))
    if "BaseTest" in log or "WireMockBaseTest" in log or "requestSpec" in log:
        fixes.append(lambda f: fix_base_class_extends(f, base_package))
    if "requestSpec" in log or "cyclic inheritance" in log:
        fixes.append(lambda f: fix_request_spec_reference(f, base_package))
    if uses_wiremock:
        if "symbol:   variable requestSpec" in log or "variable requestSpec" in log:
            fixes.append(lambda f: fix_wiremock_request_spec(f, base_package))
        if "StringValuePattern" in log or "WireMock" in log:
            fixes.extend(
                [
                    lambda f: fix_wiremock_test_base_class(f, base_package),
                    lambda f: fix_wiremock_request_spec(f, base_package),
                    lambda f: fix_wiremock_hamcrest_import_clash(f),
                    lambda f: remove_broken_wiremock_tests(f),
                ]
            )
    if "io.restassured" in log:
        fixes.append(move_restassured_clients_to_test)

    for fixer in fixes:
        result = fixer(current)
        current, applied = result.files, applied + result.applied

    return FixResult(files=current, applied=applied)


_TESTNG_IMPORT = re.compile(
    r"import\s+org\.testng\.annotations\.(\w+)\s*;",
)
_TESTNG_TO_JUNIT = {
    "Test": "Test",
    "BeforeMethod": "BeforeEach",
    "AfterMethod": "AfterEach",
    "BeforeClass": "BeforeAll",
    "AfterClass": "AfterAll",
    "BeforeSuite": "BeforeAll",
    "AfterSuite": "AfterAll",
    "DataProvider": "ParameterizedTest",  # best-effort; may need manual fix
}


def normalize_junit_and_base_imports(
    files: dict[str, str], base_package: str
) -> FixResult:
    """TestNG → JUnit 5; .tests.base. → .base.; drop bogus base imports."""
    out = dict(files)
    applied: list[str] = []
    wrong_base = f"{base_package}.tests.base"
    correct_base = f"{base_package}.base"

    for path, content in list(out.items()):
        if not _norm(path).endswith(".java"):
            continue
        original = content

        if wrong_base in content:
            content = content.replace(wrong_base, correct_base)

        for m in list(_TESTNG_IMPORT.finditer(content)):
            ann = m.group(1)
            junit_ann = _TESTNG_TO_JUNIT.get(ann)
            if junit_ann:
                replacement = f"import org.junit.jupiter.api.{junit_ann};"
            else:
                replacement = ""
            content = content.replace(m.group(0), replacement, 1)

        if "org.testng" in content:
            content = re.sub(r"import\s+org\.testng[^;]+;\s*\n?", "", content)
        if "@Test" in content and "org.junit.jupiter.api.Test" not in content:
            content = "import org.junit.jupiter.api.Test;\n" + content
        if "@BeforeEach" in content and "org.junit.jupiter.api.BeforeEach" not in content:
            if "BeforeEach" in content:
                content = "import org.junit.jupiter.api.BeforeEach;\n" + content

        if content != original:
            out[path] = content
            applied.append(f"JUnit/base import fix in {_norm(path)}")

    return FixResult(files=out, applied=applied)


def fix_wiremock_test_base_class(
    files: dict[str, str], base_package: str
) -> FixResult:
    """WireMock tests must extend WireMockBaseTest, not BaseTest."""
    out = dict(files)
    applied: list[str] = []
    wm_fqn = f"{base_package}.base.WireMockBaseTest"
    base_fqn = f"{base_package}.base.BaseTest"

    for path, content in list(out.items()):
        p = _norm(path)
        if not p.endswith(".java") or "/tests/" not in p:
            continue
        if p.endswith("WireMock405Test.java"):
            continue
        if "stubFor" not in content and "WireMockServer" not in content:
            continue
        original = content
        if re.search(rf"\bextends\s+{re.escape(base_fqn)}\b", content):
            content = re.sub(
                rf"\bextends\s+{re.escape(base_fqn)}\b",
                f"extends {wm_fqn}",
                content,
                count=1,
            )
        elif re.search(r"\bextends\s+BaseTest\b", content):
            content = re.sub(
                r"\bextends\s+BaseTest\b",
                f"extends {wm_fqn}",
                content,
                count=1,
            )
        if content != original:
            out[path] = content
            applied.append(f"WireMock base class in {p}")

    return FixResult(files=out, applied=applied)


def fix_wiremock_request_spec(files: dict[str, str], base_package: str) -> FixResult:
    """WireMockBaseTest exposes wireMockSpec, not requestSpec."""
    out = dict(files)
    applied: list[str] = []
    wm_fqn = f"{base_package}.base.WireMockBaseTest"
    base_fqn = f"{base_package}.base.BaseTest"

    for path, content in list(out.items()):
        p = _norm(path)
        if not p.endswith(".java") or "/tests/" not in p:
            continue
        if p.endswith("WireMock405Test.java"):
            continue
        uses_wm = (
            f"extends {wm_fqn}" in content
            or "extends WireMockBaseTest" in content
            or ("stubFor" in content and "WireMock" in content)
        )
        if not uses_wm:
            continue
        if not re.search(r"(?<!\.)\brequestSpec\b", content):
            continue
        original = content
        content = re.sub(r"(?<!\.)\brequestSpec\b", "wireMockSpec", content)
        content = content.replace(
            f"{base_fqn}.requestSpec", f"{wm_fqn}.wireMockSpec"
        )
        if content != original:
            out[path] = content
            applied.append(f"wireMockSpec in {p}")

    return FixResult(files=out, applied=applied)


def _discover_request_dto_classes(files: dict[str, str]) -> dict[str, str]:
    """class name -> file path"""
    found: dict[str, str] = {}
    for path, content in files.items():
        p = _norm(path)
        if "/dto/request/" not in p or not p.endswith(".java"):
            continue
        match = re.search(r"public\s+(?:final\s+)?class\s+(\w+)\b", content)
        if match:
            found[match.group(1)] = path
    return found


def _pick_canonical_request_dto(
    dto_classes: dict[str, str], files: dict[str, str]
) -> str | None:
    if not dto_classes:
        return None
    if len(dto_classes) == 1:
        return next(iter(dto_classes))

    scores: dict[str, int] = {name: 0 for name in dto_classes}
    for content in files.values():
        for name in dto_classes:
            scores[name] += len(re.findall(rf"\b{re.escape(name)}\b", content))

    ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
    if ranked[0][1] > 0:
        return ranked[0][0]

    for name in dto_classes:
        if name.endswith("InputDto") or name.endswith("Request"):
            return name
    return next(iter(dto_classes))


def sync_client_dto_type(files: dict[str, str], base_package: str) -> FixResult:
    """Align scaffold ApiClient create/update types with generated dto/request classes."""
    out = dict(files)
    applied: list[str] = []
    dtos = _discover_request_dto_classes(out)
    canonical = _pick_canonical_request_dto(dtos, out)
    if not canonical:
        return FixResult(files=out, applied=applied)

    dto_fqn = f"{base_package}.dto.request.{canonical}"
    dto_import = f"import {dto_fqn};"

    for path, content in list(out.items()):
        p = _norm(path)
        if not p.endswith("ApiClient.java") or "/client/" not in p:
            continue
        original = content

        for wrong in set(re.findall(r"\b(\w+(?:InputDto|Request|Input))\b", content)):
            if wrong == canonical:
                continue
            if wrong in dtos or wrong.endswith("InputDto") or wrong.endswith("Request"):
                content = re.sub(rf"\b{re.escape(wrong)}\b", canonical, content)

        if dto_import not in content:
            pkg = re.search(r"^package\s+[^;]+;\s*\n", content, re.MULTILINE)
            if pkg:
                insert_at = pkg.end()
                content = content[:insert_at] + dto_import + "\n" + content[insert_at:]
            else:
                content = dto_import + "\n" + content

        if content != original:
            out[path] = content
            applied.append(f"DTO sync {canonical} in {p}")

    # Replace only phantom *InputDto names (not defined in dto/request/)
    scaffold_only = re.compile(r"\b\w+InputDto\b")
    for path, content in list(out.items()):
        if not _norm(path).endswith(".java"):
            continue
        original = content
        for wrong in set(scaffold_only.findall(content)):
            if wrong == canonical or wrong in dtos:
                continue
            content = re.sub(rf"\b{re.escape(wrong)}\b", canonical, content)
        if content != original:
            out[path] = content
            applied.append(f"DTO rename in {_norm(path)}")

    return FixResult(files=out, applied=applied)


_TEST_DTO_BY_CLASS = (
    (re.compile(r"User\w*Test"), "UserInputDto"),
    (re.compile(r"Store\w*Test"), "OrderInputDto"),
    (re.compile(r"Pet\w*Test"), "PetInputDto"),
)


def fix_single_arg_client_update(files: dict[str, str]) -> FixResult:
    """client.update(dto) -> client.update(id, dto) when id is set on builder."""
    out = dict(files)
    applied: list[str] = []

    for path, content in list(out.items()):
        p = _norm(path)
        if not p.endswith("Test.java") or "client.update(" not in content:
            continue
        original = content
        content = re.sub(
            r"client\.update\(\s*(\w+)\s*\)\s*;",
            r"client.update(\1.getId(), \1);",
            content,
        )
        if content != original:
            out[path] = content
            applied.append(f"update(id, dto) in {p}")

    return FixResult(files=out, applied=applied)


def move_response_dtos_to_main(files: dict[str, str]) -> FixResult:
    """Move response DTOs from src/test/java to src/main/java when misplaced."""
    out = dict(files)
    applied: list[str] = []
    to_move: list[tuple[str, str]] = []

    for path in list(out.keys()):
        p = _norm(path)
        if "/src/test/java/" not in p or "/dto/response/" not in p:
            continue
        new_path = p.replace("/src/test/java/", "/src/main/java/", 1)
        to_move.append((path, new_path))

    for old, new in to_move:
        if new not in out:
            out[new] = out.pop(old)
            applied.append(f"Moved response DTO {old} -> {new}")
        else:
            del out[old]
            applied.append(f"Dropped duplicate test-path {old}")

    return FixResult(files=out, applied=applied)


_LONG_BUILDER_FIELDS = re.compile(r"\.(id|petId)\((\d+)\)(?!\s*L)")


def suffix_long_literals_in_dto_builders(files: dict[str, str]) -> FixResult:
    """`.id(100500)` → `.id(100500L)` when scaffold DTO fields are Long (int64)."""
    out = dict(files)
    applied: list[str] = []

    for path, content in list(out.items()):
        p = _norm(path)
        if not p.endswith(".java"):
            continue
        updated = _LONG_BUILDER_FIELDS.sub(r".\1(\2L)", content)
        if updated != content:
            out[path] = updated
            applied.append(f"Long suffix in builders {p}")

    return FixResult(files=out, applied=applied)


def strip_long_literals_in_tests(files: dict[str, str]) -> FixResult:
    """
    Убираем L только у int32 полей (quantity, userStatus), не у id/petId (Long).
    """
    out = dict(files)
    applied: list[str] = []
    pattern = re.compile(r"\.(quantity|userStatus)\((\d+)L\)")

    for path, content in list(out.items()):
        p = _norm(path)
        if not p.endswith(".java") or "/tests/" not in p:
            continue
        updated = pattern.sub(r".\1(\2)", content)
        if updated != content:
            out[path] = updated
            applied.append(f"int literal fix in {p}")

    return FixResult(files=out, applied=applied)


def align_request_dto_in_tests(files: dict[str, str], base_package: str) -> FixResult:
    """User/Store tests must not build PetInputDto for User/Order bodies."""
    out = dict(files)
    applied: list[str] = []
    dtos = _discover_request_dto_classes(out)

    for path, content in list(out.items()):
        p = _norm(path)
        if "/tests/" not in p or not p.endswith("Test.java"):
            continue
        class_file = p.split("/")[-1]
        target: str | None = None
        for pattern, dto_name in _TEST_DTO_BY_CLASS:
            if pattern.search(class_file) and dto_name in dtos:
                target = dto_name
                break
        if not target:
            continue
        original = content
        for wrong in dtos:
            if wrong.endswith("InputDto") and wrong != target:
                content = re.sub(rf"\b{re.escape(wrong)}\b", target, content)
        import_wrong = re.compile(
            rf"import\s+{re.escape(base_package)}\.dto\.request\.(\w+InputDto)\s*;"
        )
        content = import_wrong.sub(
            f"import {base_package}.dto.request.{target};", content
        )
        if content != original:
            out[path] = content
            applied.append(f"DTO {target} in {p}")

    return FixResult(files=out, applied=applied)


def _is_main_input_dto(name: str) -> bool:
    return name.endswith("InputDto")


def sync_component_dto_suffix(files: dict[str, str]) -> FixResult:
    """
    Тесты ожидают OrderItemDto, scaffold мог создать OrderItem.
    Переименовывает класс и ссылки: OrderItem -> OrderItemDto.
    """
    out = dict(files)
    applied: list[str] = []
    dtos = _discover_request_dto_classes(out)

    for base, path in list(dtos.items()):
        if _is_main_input_dto(base) or base.endswith("Dto"):
            continue
        target = f"{base}Dto"
        if target in dtos:
            continue
        content = out[path]
        updated = re.sub(rf"\bclass\s+{re.escape(base)}\b", f"class {target}", content)
        new_path = path.replace(f"/{base}.java", f"/{target}.java")
        del out[path]
        out[new_path] = updated
        applied.append(f"Promoted {base} -> {target}")

    dtos = _discover_request_dto_classes(out)
    for path, content in list(out.items()):
        if not _norm(path).endswith(".java"):
            continue
        original = content
        for class_name in sorted(dtos, key=len, reverse=True):
            if not class_name.endswith("Dto") or _is_main_input_dto(class_name):
                continue
            base = class_name.removesuffix("Dto")
            if not base or base in dtos:
                continue
            content = re.sub(rf"\b{re.escape(base)}\b", class_name, content)
        if content != original:
            out[path] = content
            applied.append(f"DTO suffix refs in {_norm(path)}")

    return FixResult(files=out, applied=applied)


_GETBYID_STRING_RE = re.compile(r"\bclient\.getById\s*\(\s*\"([^\"]*)\"\s*\)")


def _client_getbyid_java_type(files: dict[str, str]) -> str | None:
    for path, content in files.items():
        p = _norm(path)
        if "/client/" not in p.lower() or not p.endswith("ApiClient.java"):
            continue
        match = re.search(r"getById\s*\(\s*(\w+)\s+\w+\s*\)", content)
        if match:
            return match.group(1)
    return None


def fix_getbyid_string_literal_calls(files: dict[str, str]) -> FixResult:
    """
    client.getById(\"nonexistent\") при getById(long) — замена на RestAssured GET.
    """
    id_type = _client_getbyid_java_type(files)
    if id_type not in ("long", "int"):
        return FixResult(files=files, applied=[])

    out = dict(files)
    applied: list[str] = []
    for path, content in list(out.items()):
        p = _norm(path)
        if not p.endswith("Test.java") or "/tests/" not in p:
            continue
        if not _GETBYID_STRING_RE.search(content):
            continue
        spec = "wireMockSpec" if "WireMockBaseTest" in content else "requestSpec"
        if spec not in content and "extends BaseTest" in content:
            spec = "requestSpec"

        def _replace(match: re.Match[str]) -> str:
            return (
                f"given().spec({spec}).when().get(\"/nonexistent\").then()"
                ".extract().response()"
            )

        new_content = _GETBYID_STRING_RE.sub(_replace, content)
        if "import static io.restassured.RestAssured.given;" not in new_content:
            new_content = _insert_after_package(
                new_content,
                "import static io.restassured.RestAssured.given;\n",
            )
        if new_content != content:
            out[path] = new_content
            applied.append(f"getById(String) -> given().get in {p}")

    return FixResult(files=out, applied=applied)


def rename_base_tests_to_integration(
    files: dict[str, str], base_package: str
) -> FixResult:
    """
    Тесты на BaseTest бьют в base.url (часто фиктивный URL из OpenAPI).
    Surefire в pom исключает *IntegrationTest — переименовываем для Docker Maven.
    """
    out = dict(files)
    applied: list[str] = []
    base_fqn = f"{base_package}.base.BaseTest"
    wm_fqn = f"{base_package}.base.WireMockBaseTest"

    for path in list(out.keys()):
        p = _norm(path)
        if "/tests/" not in p or not p.endswith("Test.java"):
            continue
        if p.endswith("WireMock405Test.java") or "IntegrationTest.java" in p:
            continue
        content = out[path]
        if wm_fqn in content or "extends WireMockBaseTest" in content:
            continue
        if (
            f"extends {base_fqn}" not in content
            and "extends BaseTest" not in content
        ):
            continue
        match = re.search(r"\bclass\s+(\w+)\b", content)
        if not match:
            continue
        old_name = match.group(1)
        if old_name.endswith("IntegrationTest"):
            continue
        if old_name.endswith("Test"):
            new_name = old_name[:-4] + "IntegrationTest"
        else:
            new_name = old_name + "IntegrationTest"
        new_content = content.replace(f"class {old_name}", f"class {new_name}", 1)
        new_path = p.replace(f"/{old_name}.java", f"/{new_name}.java")
        del out[path]
        out[new_path] = new_content
        applied.append(f"{old_name} -> {new_name} (excluded from Docker mvn test)")

    return FixResult(files=out, applied=applied)


def sync_api_client_class_name(files: dict[str, str]) -> FixResult:
    """Align test imports with scaffold *ApiClient.java class name."""
    out = dict(files)
    applied: list[str] = []
    client_name: str | None = None

    for path, content in out.items():
        p = _norm(path)
        if "/client/" not in p.lower() or not p.endswith("ApiClient.java"):
            continue
        match = re.search(r"public\s+(?:final\s+)?class\s+(\w+ApiClient)\b", content)
        if match:
            client_name = match.group(1)
            break

    if not client_name:
        return FixResult(files=out, applied=applied)

    for path, content in list(out.items()):
        if not _norm(path).endswith(".java"):
            continue
        original = content
        for wrong in set(re.findall(r"\b(\w+ApiClient)\b", content)):
            if wrong == client_name:
                continue
            if wrong.endswith("ApiClient") and wrong != client_name:
                content = re.sub(rf"\b{re.escape(wrong)}\b", client_name, content)
        if content != original:
            out[path] = content
            applied.append(f"ApiClient rename {path}")

    return FixResult(files=out, applied=applied)


def apply_all_structure_fixes(
    files: dict[str, str],
    base_package: str,
    scaffold: dict[str, str] | None = None,
    *,
    uses_wiremock: bool = True,
) -> FixResult:
    applied: list[str] = []
    current = files
    fixers: list = [
        lambda f: normalize_junit_and_base_imports(f, base_package),
        move_response_dtos_to_main,
        fix_single_arg_client_update,
        lambda f: align_packages_to_path(f, base_package),
        lambda f: fix_base_class_extends(f, base_package),
        lambda f: sync_api_client_class_name(f),
        lambda f: sync_client_dto_type(f, base_package),
        lambda f: align_request_dto_in_tests(f, base_package),
        suffix_long_literals_in_dto_builders,
        strip_long_literals_in_tests,
        fix_getbyid_string_literal_calls,
        lambda f: sync_component_dto_suffix(f),
        lambda f: rename_base_tests_to_integration(f, base_package),
    ]
    if uses_wiremock:
        fixers.extend(
            [
                lambda f: fix_wiremock_test_base_class(f, base_package),
                lambda f: fix_wiremock_request_spec(f, base_package),
                lambda f: fix_wiremock_hamcrest_import_clash(f),
                lambda f: remove_broken_wiremock_tests(f),
            ]
        )
    fixers.extend(
        [
            lambda f: fix_request_spec_reference(f, base_package),
            lambda f: move_restassured_clients_to_test(f),
        ]
    )
    for fixer in fixers:
        result = fixer(current)
        current = result.files
        applied.extend(result.applied)
    if scaffold:
        restored = restore_scaffold_base_files(current, scaffold)
        current = restored.files
        applied.extend(restored.applied)
    return FixResult(files=current, applied=applied)
