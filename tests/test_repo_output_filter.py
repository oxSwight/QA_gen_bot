"""Mode B API output path filter."""
from qa_gen_bot.codegen.repo_output_filter import filter_repo_generated_files


def test_filter_keeps_tests_drops_client() -> None:
    raw = {
        "src/test/java/com/x/tests/FooTest.java": "class Foo {}",
        "src/test/java/com/x/client/ApiClient.java": "bad",
        "pom.xml": "<project/>",
        "src/main/java/com/x/Main.java": "bad",
    }
    kept = filter_repo_generated_files(raw)
    assert list(kept.keys()) == ["src/test/java/com/x/tests/FooTest.java"]
