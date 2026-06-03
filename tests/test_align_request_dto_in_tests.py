"""align_request_dto_in_tests — User/Store tests must not use PetInputDto."""
from qa_gen_bot.structure_fixer import align_request_dto_in_tests


def test_user_test_gets_user_input_dto():
    pkg = "com.demo"
    files = {
        f"src/main/java/{pkg.replace('.', '/')}/dto/request/PetInputDto.java": (
            f"package {pkg}.dto.request; public class PetInputDto {{}}"
        ),
        f"src/main/java/{pkg.replace('.', '/')}/dto/request/UserInputDto.java": (
            f"package {pkg}.dto.request; public class UserInputDto {{ private String username; }}"
        ),
        f"src/test/java/{pkg.replace('.', '/')}/tests/UserIntegrationTest.java": f"""
            package {pkg}.tests;
            import {pkg}.dto.request.PetInputDto;
            class UserIntegrationTest {{
                void t() {{ PetInputDto.builder().username("u1").build(); }}
            }}
        """,
    }
    result = align_request_dto_in_tests(files, pkg)
    test = result.files[
        f"src/test/java/{pkg.replace('.', '/')}/tests/UserIntegrationTest.java"
    ]
    assert "UserInputDto" in test
    assert "PetInputDto" not in test
    assert any("UserInputDto" in a for a in result.applied)
