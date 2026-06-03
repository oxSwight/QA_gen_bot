"""Unit tests for maven_validator output parsing."""
from qa_gen_bot.maven_validator import _parse_maven_output


def test_build_success_without_tests_run_fails():
    output = """
[INFO] ------------------------------------------------------------------------
[INFO] BUILD SUCCESS
[INFO] ------------------------------------------------------------------------
"""
    result = _parse_maven_output(output, exit_code=0)
    assert not result.passed
    assert result.tests_run is None
    assert any("Surefire" in e for e in result.errors)


def test_build_success_with_tests_run_passes():
    output = """
[INFO] Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
[INFO] BUILD SUCCESS
"""
    result = _parse_maven_output(output, exit_code=0)
    assert result.passed
    assert result.tests_run == 3


def test_surefire_errors_fail_build():
    output = """
[INFO] Tests run: 8, Failures: 0, Errors: 3, Skipped: 0
[ERROR] OrdersPositiveTest.createOrder » UnknownHost api.production-env.com
[INFO] BUILD FAILURE
"""
    result = _parse_maven_output(output, exit_code=1)
    assert not result.passed
    assert result.test_errors == 3
    assert result.tests_run == 8


def test_compile_failure_without_tests_run_fails():
    output = """
[INFO] Compiling 3 source files with javac
[ERROR] COMPILATION ERROR :
[ERROR] /project/src/main/java/com/x/dto/request/PostInputDto.java:[20,13] cannot find symbol
  symbol:   class MetricDetailsDto
[INFO] BUILD FAILURE
"""
    result = _parse_maven_output(output, exit_code=1)
    assert not result.passed
    assert result.tests_run is None
    assert any("компиляции" in e or "COMPILATION" in e for e in result.errors)


def test_clean_surefire_summary_passes_despite_docker_exit_code_quirk():
    """Docker на Windows иногда отдаёт exit_code=1 при BUILD SUCCESS."""
    output = """
[INFO] Results:
[INFO] Tests run: 5, Failures: 0, Errors: 0, Skipped: 0
[INFO] BUILD SUCCESS
"""
    result = _parse_maven_output(output, exit_code=1)
    assert result.passed
