from qa_gen_bot.xml_parser import parse_llm_output


def test_rejects_path_traversal():
    out = parse_llm_output(
        '<file path="../../../etc/passwd">x</file>'
        '<file path="src/test/ok.java">class Ok {}</file>'
    )
    assert "../../../etc/passwd" not in out.files
    assert "src/test/ok.java" in out.files
