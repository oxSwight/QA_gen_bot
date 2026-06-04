"""Repo-mode prompt selection."""
from qa_gen_bot.prompts import (
    get_maven_retry_hint,
    get_phase_tests_prompt,
    get_retry_prompt_suffix,
    get_system_prompt,
)


def test_repo_system_prompt_differs_from_quick_start() -> None:
    repo = get_system_prompt(uses_wiremock=True, repo_mode=True)
    quick = get_system_prompt(uses_wiremock=True, repo_mode=False)
    assert "schemas" in repo.lower()
    assert "src/test/java" not in repo.lower() or "не возвращай" in repo.lower()
    assert "ApiClient" in quick or "client" in quick.lower()
    assert repo != quick


def test_repo_retry_and_maven_hints() -> None:
    assert "src/test" in get_retry_prompt_suffix(uses_wiremock=True, repo_mode=True)
    assert "generate-sources" in get_maven_retry_hint(
        uses_wiremock=True, repo_mode=True
    )
    assert "api" in get_phase_tests_prompt(uses_wiremock=True, repo_mode=True).lower()
