from qa_gen_bot.structure_fixer import fix_base_class_extends


def test_fqn_extends_base_test():
    pkg = "com.microserviceautomationap"
    files = {
        "src/test/java/com/microserviceautomationap/tests/T.java": """
package com.microserviceautomationap.tests;
class T extends BaseTest {
    @org.junit.jupiter.api.Test void x() {}
}
""",
    }
    result = fix_base_class_extends(files, pkg)
    assert f"extends {pkg}.base.BaseTest" in result.files[
        "src/test/java/com/microserviceautomationap/tests/T.java"
    ]
