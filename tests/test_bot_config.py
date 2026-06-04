"""bot.json merge with env."""
import json
import os
from pathlib import Path
from unittest import mock

from qa_gen_bot.bot_config import apply_bot_file_config, load_bot_file_config
from qa_gen_bot.config import Settings, load_settings


def test_load_bot_file_config(tmp_path: Path) -> None:
    path = tmp_path / "bot.json"
    path.write_text(
        json.dumps(
            {
                "default_generation_profile": "integration-only",
                "default_generation_mode": "repo",
                "segment": "startup",
                "tester_max_runs": 3,
            }
        ),
        encoding="utf-8",
    )
    cfg = load_bot_file_config(path)
    assert cfg.default_generation_profile == "integration-only"
    assert cfg.default_generation_mode == "repo"
    assert cfg.segment == "startup"
    assert cfg.tester_max_runs == 3


def test_env_wins_over_bot_profile(tmp_path: Path) -> None:
    path = tmp_path / "bot.json"
    path.write_text(
        '{"default_generation_profile": "integration-only"}',
        encoding="utf-8",
    )
    base = Settings(
        tg_token="t",
        anthropic_api_key="k",
        generation_profile="contract-mocks",
        tester_telegram_id=1,
        tester_max_runs=5,
    )
    file_cfg = load_bot_file_config(path)
    merged = apply_bot_file_config(base, file_cfg, env_profile_set=True)
    assert merged.generation_profile == "contract-mocks"


def test_bot_json_applies_when_env_profile_missing(tmp_path: Path) -> None:
    path = tmp_path / "bot.json"
    path.write_text(
        '{"default_generation_profile": "integration-only"}',
        encoding="utf-8",
    )
    base = Settings(
        tg_token="t",
        anthropic_api_key="k",
        generation_profile="contract-mocks",
    )
    merged = apply_bot_file_config(
        base, load_bot_file_config(path), env_profile_set=False
    )
    assert merged.generation_profile == "integration-only"


def test_load_settings_with_bot_json(tmp_path: Path) -> None:
    bot_path = tmp_path / "bot.json"
    bot_path.write_text(
        '{"default_generation_profile": "integration-only", "tester_max_runs": 2}',
        encoding="utf-8",
    )
    env = {
        "TG_TOKEN": "x",
        "ANTHROPIC_KEY": "y",
        "TESTER_TELEGRAM_ID": "99",
    }
    with mock.patch.dict(os.environ, env, clear=True):
        with mock.patch(
            "qa_gen_bot.bot_config.resolve_bot_config_path",
            return_value=bot_path,
        ):
            settings = load_settings(require_telegram=False, require_anthropic=False)
    assert settings.generation_profile == "integration-only"
    assert settings.tester_max_runs == 2


def test_segment_applied_from_bot_json(tmp_path: Path) -> None:
    path = tmp_path / "bot.json"
    path.write_text('{"segment": "team"}', encoding="utf-8")
    base = Settings(tg_token="t", anthropic_api_key="k")
    merged = apply_bot_file_config(
        base, load_bot_file_config(path), env_profile_set=False
    )
    assert merged.segment == "team"
