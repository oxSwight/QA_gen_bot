"""Telegram profile selection helpers."""
from qa_gen_bot.generation_profile_ui import (
    parse_profile_from_callback,
    parse_profile_from_text,
)
from qa_gen_bot.config import PROFILE_CONTRACT_MOCKS, PROFILE_INTEGRATION_ONLY


def test_callback_parsing() -> None:
    assert (
        parse_profile_from_callback("genprof:integration-only")
        == PROFILE_INTEGRATION_ONLY
    )
    assert (
        parse_profile_from_callback("genprof:contract-mocks") == PROFILE_CONTRACT_MOCKS
    )
    assert parse_profile_from_callback("other") is None


def test_text_aliases() -> None:
    assert parse_profile_from_text("1") == PROFILE_INTEGRATION_ONLY
    assert parse_profile_from_text("моки") == PROFILE_CONTRACT_MOCKS
    assert parse_profile_from_text("https://api.example.com") is None


def test_pending_job_flow() -> None:
    from qa_gen_bot.pending_jobs import (
        PendingSpecJob,
        set_pending,
        update_pending_mode,
        update_pending_profile,
    )
    from qa_gen_bot.spec_parser import parse_spec_content

    spec = parse_spec_content(
        '{"openapi":"3.0.0","info":{"title":"T","version":"1"},"paths":{"/a":{"get":{}}}}'
    )
    job = PendingSpecJob("{}", spec, "a.json")
    assert job.awaiting_profile
    set_pending(99, job)
    updated = update_pending_profile(99, PROFILE_INTEGRATION_ONLY)
    assert updated is not None
    assert updated.awaiting_mode
    updated = update_pending_mode(99, "quick_start")
    assert updated is not None
    assert updated.ready_for_url
    assert updated.generation_profile == PROFILE_INTEGRATION_ONLY
    assert updated.generation_mode == "quick_start"
