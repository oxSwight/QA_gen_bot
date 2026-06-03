"""BaseTest subclasses renamed for Docker Surefire excludes."""
from qa_gen_bot.structure_fixer import rename_base_tests_to_integration


def test_renames_positive_base_test_to_integration():
    pkg = "com.demo"
    pp = pkg.replace(".", "/")
    path = f"src/test/java/{pp}/tests/OrdersPositiveTest.java"
    files = {
        path: f"""
package {pkg}.tests;
import {pkg}.base.BaseTest;
class OrdersPositiveTest extends BaseTest {{
    @org.junit.jupiter.api.Test void t() {{}}
}}
"""
    }
    result = rename_base_tests_to_integration(files, pkg)
    new_path = f"src/test/java/{pp}/tests/OrdersPositiveIntegrationTest.java"
    assert new_path in result.files
    assert path not in result.files
    assert "class OrdersPositiveIntegrationTest" in result.files[new_path]


def test_keeps_wiremock_positive_test():
    pkg = "com.demo"
    pp = pkg.replace(".", "/")
    path = f"src/test/java/{pp}/tests/OrderWireMockTest.java"
    files = {
        path: f"""
package {pkg}.tests;
import {pkg}.base.WireMockBaseTest;
class OrderWireMockTest extends WireMockBaseTest {{
    @org.junit.jupiter.api.Test void t() {{}}
}}
"""
    }
    result = rename_base_tests_to_integration(files, pkg)
    assert path in result.files
    assert not result.applied
