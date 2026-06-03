"""Generation mode UI parsing."""
from qa_gen_bot.generation_mode_ui import (
    parse_mode_from_callback,
    parse_mode_from_text,
)


def test_mode_callback() -> None:
    assert parse_mode_from_callback("genmode:quick_start") == "quick_start"
    assert parse_mode_from_callback("genmode:repo") == "repo"
    assert parse_mode_from_callback("genmode:other") is None


def test_mode_text() -> None:
    assert parse_mode_from_text("zip") == "quick_start"
    assert parse_mode_from_text("repo") == "repo"
