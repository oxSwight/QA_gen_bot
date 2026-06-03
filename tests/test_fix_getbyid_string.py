from qa_gen_bot.structure_fixer import fix_getbyid_string_literal_calls


def test_fix_getbyid_string_replaces_with_given_get():
    files = {
        "src/test/java/com/x/client/ItemsApiClient.java": """
            public class ItemsApiClient {
                public Response getById(long id) { return null; }
            }
        """,
        "src/test/java/com/x/tests/ItemNegativeTest.java": """
            package com.x.tests;
            import com.x.base.WireMockBaseTest;
            class ItemNegativeTest extends WireMockBaseTest {
                ItemsApiClient client;
                void t() { client.getById("nonexistent"); }
            }
        """,
    }
    result = fix_getbyid_string_literal_calls(files)
    text = result.files["src/test/java/com/x/tests/ItemNegativeTest.java"]
    assert 'getById("nonexistent")' not in text
    assert "given().spec(wireMockSpec)" in text
    assert 'get("/nonexistent")' in text
