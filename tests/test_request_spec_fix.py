from qa_gen_bot.structure_fixer import fix_request_spec_reference


def test_does_not_patch_base_test_itself():
    pkg = "com.microserviceautomationap"
    files = {
        f"src/test/java/{pkg.replace('.', '/')}/base/BaseTest.java": f"""
package {pkg}.base;
public abstract class BaseTest {{
    public static Object requestSpec;
}}
""",
    }
    result = fix_request_spec_reference(files, pkg)
    assert "extends" not in result.files[
        f"src/test/java/{pkg.replace('.', '/')}/base/BaseTest.java"
    ]
