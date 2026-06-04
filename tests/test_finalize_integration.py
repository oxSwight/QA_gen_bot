"""Integration: scaffold + auto-fix must keep BaseTest valid."""
import json

from qa_gen_bot.pipeline import _finalize_files
from qa_gen_bot.scaffold import build_scaffold
from qa_gen_bot.spec_parser import parse_spec_content
from qa_gen_bot.structure_fixer import fix_request_spec_reference


OPENAPI = """
{
  "openapi": "3.0.0",
  "info": {"title": "Demo API", "version": "1"},
  "paths": {
    "/items": {
      "get": {"operationId": "list", "responses": {"200": {"description": "ok"}}}
    }
  }
}
"""


def test_finalize_restores_base_after_bad_autofix():
    analysis = parse_spec_content(OPENAPI)
    scaffold = build_scaffold(analysis)
    pkg = f"com.{analysis.package_hint}"
    base_path = f"src/test/java/{pkg.replace('.', '/')}/base/BaseTest.java"

    broken_llm = {
        base_path: f"""
package {pkg}.base;
public abstract class BaseTest extends {pkg}.base.BaseTest {{
    public static Object requestSpec;
}}
""",
        f"src/test/java/{pkg.replace('.', '/')}/tests/T.java": f"""
package {pkg}.tests;
class T {{
    void x() {{ var y = requestSpec; }}
}}
""",
    }

    log: list[str] = []
    files, gate = _finalize_files(
        broken_llm,
        scaffold,
        True,
        pkg,
        log,
        uses_wiremock=True,
    )

    base_content = files[base_path]
    assert "extends" not in base_content or "abstract class BaseTest {" in base_content
    assert "extends com." not in base_content.split("{")[0]
    assert gate.passed or "StringValuePattern" not in str(gate.errors)


def test_request_spec_never_touches_base():
    pkg = "com.demoapi"
    path = "src/test/java/com/demoapi/base/BaseTest.java"
    files = {path: f"package {pkg}.base;\npublic abstract class BaseTest {{\n  static x requestSpec;\n}}\n"}
    result = fix_request_spec_reference(files, pkg)
    assert "extends" not in result.files[path]
