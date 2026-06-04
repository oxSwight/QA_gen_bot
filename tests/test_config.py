"""Tests for settings and GENERATION_PROFILE validation."""
from __future__ import annotations

import os
from unittest import mock

import pytest

from qa_gen_bot.config import (
    DEFAULT_GENERATION_PROFILE,
    PROFILE_CONTRACT_MOCKS,
    PROFILE_INTEGRATION_ONLY,
    load_settings,
)


def test_default_profile_when_env_missing() -> None:
    with mock.patch.dict(os.environ, {}, clear=True):
        os.environ.pop("GENERATION_PROFILE", None)
        settings = load_settings(require_telegram=False, require_anthropic=False)
    assert settings.generation_profile == DEFAULT_GENERATION_PROFILE
    assert settings.generation_profile == PROFILE_CONTRACT_MOCKS
    assert settings.uses_wiremock is True
    assert settings.is_integration_only is False


def test_integration_only_profile() -> None:
    env = {
        "GENERATION_PROFILE": "integration-only",
        "TG_TOKEN": "x",
        "ANTHROPIC_KEY": "y",
    }
    with mock.patch.dict(os.environ, env, clear=True):
        settings = load_settings(require_telegram=False, require_anthropic=False)
    assert settings.generation_profile == PROFILE_INTEGRATION_ONLY
    assert settings.uses_wiremock is False
    assert settings.is_integration_only is True


def test_profile_normalized_to_lowercase() -> None:
    env = {"GENERATION_PROFILE": "  CONTRACT-MOCKS  "}
    with mock.patch.dict(os.environ, env, clear=True):
        settings = load_settings(require_telegram=False, require_anthropic=False)
    assert settings.generation_profile == PROFILE_CONTRACT_MOCKS


def test_invalid_profile_fail_fast() -> None:
    env = {"GENERATION_PROFILE": "full-mocks"}
    with mock.patch.dict(os.environ, env, clear=True):
        with pytest.raises(RuntimeError, match="Invalid GENERATION_PROFILE"):
            load_settings(require_telegram=False, require_anthropic=False)
