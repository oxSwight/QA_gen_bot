from qa_gen_bot.structure_fixer import normalize_junit_and_base_imports

BASE = "com.demo"


def test_testng_and_wrong_base_package():
    files = {
        "src/test/java/com/demo/tests/T.java": """
package com.demo.tests;
import org.testng.annotations.Test;
import org.testng.annotations.BeforeMethod;
import com.demo.tests.base.BaseTest;
public class T extends BaseTest {
    @BeforeMethod void x() {}
    @Test void y() {}
}
""",
    }
    result = normalize_junit_and_base_imports(files, BASE)
    text = result.files["src/test/java/com/demo/tests/T.java"]
    assert "org.testng" not in text
    assert "com.demo.base.BaseTest" in text
    assert "org.junit.jupiter.api.Test" in text
    assert "org.junit.jupiter.api.BeforeEach" in text
