"""Deterministic Mode B test generation."""
from pathlib import Path

from qa_gen_bot.codegen.repo_scaffold import build_repo_scaffold
from qa_gen_bot.spec_parser import parse_spec_content


def test_httpbin_repo_scaffold_includes_fluent_api_tests() -> None:
    raw = Path("fixtures/httpbin-live-testing-api.json").read_text(encoding="utf-8-sig")
    analysis = parse_spec_content(raw)
    files = build_repo_scaffold(analysis, raw, uses_wiremock=True)
    assert "RepoWireMockBaseTest.java" in "".join(files)
    wm = files[
        "src/test/java/com/httpbinlivetestingapi/tests/WireMockSubmitTestDataTest.java"
    ]
    assert "api().submitTestData()" in wm
    assert "xTestHeaderHeader" in wm
    assert ".body(body)" in wm
    fetch = files[
        "src/test/java/com/httpbinlivetestingapi/tests/WireMockFetchTestDataTest.java"
    ]
    assert "api().fetchTestData()" in fetch
    assert "mockIdQuery" in fetch
