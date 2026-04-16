"""Tests for src/llm_providers/* (Phase 2 provider adapters).

These tests prove that adapter modules import without their SDKs installed
and raise ProviderUnavailableError at call time rather than import time.
No live API calls are made.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_DIR / "src"))

from llm_providers import (
    ProviderUnavailableError,
    anthropic_provider,
    openai_provider,
)


def test_openai_adapter_missing_key_or_sdk_raises_unavailable(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ProviderUnavailableError):
        openai_provider.generate_raw(
            prompt="hello", model="gpt-4o-mini", temperature=0.0,
            max_tokens=8, timeout_s=1.0,
        )


def test_anthropic_adapter_missing_key_or_sdk_raises_unavailable(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ProviderUnavailableError):
        anthropic_provider.generate_raw(
            prompt="hello", model="claude-3-5-haiku-latest", temperature=0.0,
            max_tokens=8, timeout_s=1.0,
        )


def test_provider_modules_have_expected_surface():
    for mod in (openai_provider, anthropic_provider):
        assert hasattr(mod, "generate_raw")
        assert hasattr(mod, "PROVIDER_NAME")
        assert hasattr(mod, "DEFAULT_API_KEY_ENV")
