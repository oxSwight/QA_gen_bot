"""Mode B API output path filter."""
from qa_gen_bot.codegen.repo_output_filter import filter_repo_generated_files


def test_filter_keeps_schemas_drops_client_and_llm_tests() -> None:
    raw = {
        "src/test/java/com/x/tests/FooTest.java": "class Foo {}",
        "src/test/resources/schemas/foo-schema.json": "{}",
        "src/test/java/com/x/client/ApiClient.java": "bad",
        "pom.xml": "<project/>",
        "src/main/java/com/x/Main.java": "bad",
    }
    kept = filter_repo_generated_files(raw)
    assert list(kept.keys()) == ["src/test/resources/schemas/foo-schema.json"]
