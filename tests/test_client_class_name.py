from qa_gen_bot.scaffold import _client_class_name, build_scaffold
from qa_gen_bot.spec_parser import parse_spec_content

OPENAPI = """
{"openapi":"3.0.0","info":{"title":"Demo","version":"1"},
 "paths":{"/products":{"get":{}}}}
"""


def test_client_class_plural():
    assert _client_class_name("products") == "ProductsApiClient"


def test_scaffold_has_matching_client_file():
    analysis = parse_spec_content(OPENAPI)
    scaffold = build_scaffold(analysis)
    assert any(
        p.endswith("ProductsApiClient.java") for p in scaffold
    )
    content = next(v for k, v in scaffold.items() if k.endswith("ProductsApiClient.java"))
    assert "public ProductsApiClient(" in content.replace("final ", "")
    assert "Response getAll()" in content
