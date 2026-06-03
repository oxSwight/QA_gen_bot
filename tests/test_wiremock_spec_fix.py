from qa_gen_bot.structure_fixer import fix_wiremock_request_spec

PKG = "com.demo"
PATH = "src/test/java/com/demo/tests/ProductsWireMockTest.java"


def test_request_spec_becomes_wire_mock_spec():
    files = {
        PATH: f"""
package {PKG}.tests;
import {PKG}.base.WireMockBaseTest;
import static com.github.tomakehurst.wiremock.client.WireMock.stubFor;
class ProductsWireMockTest extends {PKG}.base.WireMockBaseTest {{
    void init() {{ var c = new Object(requestSpec); }}
}}
""",
    }
    result = fix_wiremock_request_spec(files, PKG)
    text = result.files[PATH]
    assert "wireMockSpec" in text
    assert "requestSpec" not in text
