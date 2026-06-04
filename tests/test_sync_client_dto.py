from qa_gen_bot.structure_fixer import sync_client_dto_type

BASE = "com.demo"


def test_client_uses_generated_dto_name():
    files = {
        "src/test/java/com/demo/client/ProductsApiClient.java": """
package com.demo.client;
public class ProductsApiClient {
    public Response create(ProductInputDto body) { return null; }
    public Response update(long id, ProductInputDto body) { return null; }
}
""",
        "src/main/java/com/demo/dto/request/ProductInput.java": """
package com.demo.dto.request;
public class ProductInput {}
""",
        "src/test/java/com/demo/tests/T.java": """
import com.demo.dto.request.ProductInputDto;
class T { ProductInputDto x; }
""",
    }
    result = sync_client_dto_type(files, BASE)
    client = result.files["src/test/java/com/demo/client/ProductsApiClient.java"]
    assert "ProductInput" in client
    assert "ProductInputDto" not in client
    assert "import com.demo.dto.request.ProductInput;" in client
    test = result.files["src/test/java/com/demo/tests/T.java"]
    assert "ProductInputDto" not in test
    assert "ProductInput" in test
