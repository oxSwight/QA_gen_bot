from qa_gen_bot.structure_fixer import sync_api_client_class_name

BASE = "src/test/java/com/demo"


def test_renames_wrong_api_client_in_tests():
    files = {
        f"{BASE}/client/ProductsApiClient.java": "public class ProductsApiClient {}",
        f"{BASE}/tests/T.java": "import com.demo.client.ProductApiClient;\nProductApiClient c;",
    }
    result = sync_api_client_class_name(files)
    assert "ProductsApiClient" in result.files[f"{BASE}/tests/T.java"]
    assert "ProductApiClient" not in result.files[f"{BASE}/tests/T.java"]
