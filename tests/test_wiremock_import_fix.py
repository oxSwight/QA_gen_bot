from qa_gen_bot.structure_fixer import fix_wiremock_hamcrest_import_clash


def test_fixes_equalto_conflict():
    files = {
        "src/test/java/com/x/tests/T.java": """
package com.x.tests;
import static com.github.tomakehurst.wiremock.client.WireMock.*;
import static org.hamcrest.Matchers.*;
import static io.restassured.RestAssured.given;
class T {
    void m() {
        given().when().get("/").then().body("type", equalTo("error"));
    }
}
""",
    }
    result = fix_wiremock_hamcrest_import_clash(files)
    content = result.files["src/test/java/com/x/tests/T.java"]
    assert "WireMock.*" not in content
    assert "org.hamcrest.Matchers.equalTo" in content
    assert "StringValuePattern" not in content
