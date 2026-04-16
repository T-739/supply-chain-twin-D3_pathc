"""Tests for src/llm_backend.py (Phase 2 LLM infrastructure).

No live API calls. All provider behavior is injected via register_provider().
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from pydantic import BaseModel, Field

_PROJECT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_DIR / "src"))

import llm_backend
from llm_backend import (
    GatewayConfig,
    LLMResult,
    ProviderConfig,
    ValidationFailure,
    extract_json_object,
    generate_structured,
    register_provider,
)
from llm_providers import (
    ProviderCallError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)


# -------------------------------------------------------------------------
# Helpers — fake provider adapters
# -------------------------------------------------------------------------


def _make_fake(responses, call_log):
    """Return an adapter whose behavior is scripted by `responses`.

    Each entry in `responses` is either a string (raw_text returned successfully)
    or an Exception instance (raised when called).
    """
    it = iter(responses)

    def _adapter(prompt, model, temperature, max_tokens, timeout_s,
                 system=None, api_key_env=None):
        call_log.append({"prompt": prompt, "model": model})
        try:
            nxt = next(it)
        except StopIteration as exc:
            raise AssertionError(
                "fake adapter called more times than scripted"
            ) from exc
        if isinstance(nxt, Exception):
            raise nxt
        return nxt, {"provider": "fake", "model": model, "latency_ms": 1}

    return _adapter


class DummySchema(BaseModel):
    name: str
    count: int = Field(ge=0)


def _fallback_ok(prompt, schema):
    return {"name": "fallback", "count": 0}


def _fallback_bad(prompt, schema):
    return {"name": "fallback", "count": -1}  # fails validation


def _auto_cfg(retries=2, providers=("primary", "secondary")):
    return GatewayConfig(
        providers=tuple(
            ProviderConfig(name=p, model=f"{p}-model") for p in providers
        ),
        max_retries_per_provider=retries,
        force_mode="auto",
    )


def _off_cfg():
    return GatewayConfig(
        providers=(ProviderConfig(name="primary", model="m"),),
        force_mode="off",
    )


# -------------------------------------------------------------------------
# extract_json_object
# -------------------------------------------------------------------------

def test_extract_json_plain():
    assert extract_json_object('{"a": 1}') == {"a": 1}


def test_extract_json_fenced():
    text = "some preface\n```json\n{\"a\": 2}\n```\n"
    assert extract_json_object(text) == {"a": 2}


def test_extract_json_embedded_balanced():
    text = "prefix {\"a\": 3, \"b\": [1,2]} suffix"
    assert extract_json_object(text) == {"a": 3, "b": [1, 2]}


def test_extract_json_empty_raises():
    with pytest.raises(ValueError):
        extract_json_object("")


def test_extract_json_non_object_raises():
    with pytest.raises(ValueError):
        extract_json_object("[1, 2, 3]")


# -------------------------------------------------------------------------
# Global flag / deterministic-only mode
# -------------------------------------------------------------------------

def test_mode_off_uses_deterministic_fallback_only(monkeypatch):
    calls: list = []
    register_provider("primary", _make_fake(["{}"], calls))
    res = generate_structured(
        "p", DummySchema,
        gateway_config=_off_cfg(),
        deterministic_fallback=_fallback_ok,
    )
    assert isinstance(res, LLMResult)
    assert res.mode == "off"
    assert res.fallback_used is True
    assert res.provider is None
    assert res.value == {"name": "fallback", "count": 0}
    assert calls == []  # no provider calls made
    assert res.attempts == 0


def test_env_flag_default_is_off(monkeypatch):
    monkeypatch.delenv("SUPPLY_CHAIN_TWIN_LLM_MODE", raising=False)
    assert llm_backend.current_llm_mode() == "off"
    assert llm_backend.is_llm_enabled() is False


def test_env_flag_auto(monkeypatch):
    monkeypatch.setenv("SUPPLY_CHAIN_TWIN_LLM_MODE", "auto")
    assert llm_backend.is_llm_enabled() is True


# -------------------------------------------------------------------------
# Success path
# -------------------------------------------------------------------------

def test_success_first_try():
    calls: list = []
    register_provider("primary", _make_fake(['{"name": "ok", "count": 5}'], calls))
    res = generate_structured(
        "p", DummySchema,
        gateway_config=_auto_cfg(),
        deterministic_fallback=_fallback_ok,
    )
    assert res.value == {"name": "ok", "count": 5}
    assert res.provider == "primary"
    assert res.model == "primary-model"
    assert res.fallback_used is False
    assert res.validation_ok is True
    assert res.attempts == 1
    assert res.error is None
    assert any(e["event"] == "ok" for e in res.provider_trace)


# -------------------------------------------------------------------------
# Retry on malformed JSON, then success
# -------------------------------------------------------------------------

def test_retry_on_malformed_then_success():
    calls: list = []
    register_provider(
        "primary",
        _make_fake(
            ["not json at all", '{"name": "ok", "count": 1}'],
            calls,
        ),
    )
    res = generate_structured(
        "p", DummySchema,
        gateway_config=_auto_cfg(retries=2),
        deterministic_fallback=_fallback_ok,
    )
    assert res.value == {"name": "ok", "count": 1}
    assert res.provider == "primary"
    assert res.attempts == 2
    assert res.fallback_used is False
    events = [e["event"] for e in res.provider_trace]
    assert "parse_error" in events
    assert events[-1] == "ok"


# -------------------------------------------------------------------------
# Validation failure → retry → still bad → fallback to secondary
# -------------------------------------------------------------------------

def test_validation_failure_then_secondary_succeeds():
    primary_calls: list = []
    secondary_calls: list = []
    # Primary always returns JSON that violates schema (count < 0).
    register_provider(
        "primary",
        _make_fake(['{"name": "x", "count": -1}',
                    '{"name": "y", "count": -2}'], primary_calls),
    )
    register_provider(
        "secondary",
        _make_fake(['{"name": "secondary", "count": 7}'], secondary_calls),
    )
    res = generate_structured(
        "p", DummySchema,
        gateway_config=_auto_cfg(retries=2),
        deterministic_fallback=_fallback_ok,
    )
    assert res.value == {"name": "secondary", "count": 7}
    assert res.provider == "secondary"
    assert res.fallback_used is False
    events = [e["event"] for e in res.provider_trace]
    assert events.count("validation_error") == 2
    assert events[-1] == "ok"


# -------------------------------------------------------------------------
# Provider exception → secondary provider
# -------------------------------------------------------------------------

def test_provider_call_error_triggers_retry_then_secondary():
    primary_calls: list = []
    secondary_calls: list = []
    register_provider(
        "primary",
        _make_fake(
            [ProviderCallError("boom"), ProviderCallError("boom2")],
            primary_calls,
        ),
    )
    register_provider(
        "secondary",
        _make_fake(['{"name": "sec", "count": 2}'], secondary_calls),
    )
    res = generate_structured(
        "p", DummySchema,
        gateway_config=_auto_cfg(retries=2),
        deterministic_fallback=_fallback_ok,
    )
    assert res.provider == "secondary"
    assert res.value == {"name": "sec", "count": 2}
    assert len(primary_calls) == 2  # both primary retries consumed
    events = [e["event"] for e in res.provider_trace]
    assert events.count("call_error") == 2
    assert events[-1] == "ok"


def test_provider_unavailable_skips_to_next_without_retries():
    primary_calls: list = []
    secondary_calls: list = []
    register_provider(
        "primary",
        _make_fake([ProviderUnavailableError("sdk missing")], primary_calls),
    )
    register_provider(
        "secondary",
        _make_fake(['{"name": "sec", "count": 0}'], secondary_calls),
    )
    res = generate_structured(
        "p", DummySchema,
        gateway_config=_auto_cfg(retries=3),
        deterministic_fallback=_fallback_ok,
    )
    # Primary gets exactly 1 call, then we skip to secondary.
    assert len(primary_calls) == 1
    assert res.provider == "secondary"


def test_timeout_is_retried():
    primary_calls: list = []
    register_provider(
        "primary",
        _make_fake(
            [ProviderTimeoutError("t1"), '{"name": "ok", "count": 3}'],
            primary_calls,
        ),
    )
    res = generate_structured(
        "p", DummySchema,
        gateway_config=_auto_cfg(retries=2, providers=("primary",)),
        deterministic_fallback=_fallback_ok,
    )
    assert res.provider == "primary"
    assert res.attempts == 2
    events = [e["event"] for e in res.provider_trace]
    assert "timeout" in events


# -------------------------------------------------------------------------
# All providers fail → deterministic fallback kicks in
# -------------------------------------------------------------------------

def test_all_providers_fail_falls_back_to_deterministic():
    primary_calls: list = []
    secondary_calls: list = []
    register_provider(
        "primary",
        _make_fake(
            [ProviderCallError("p1"), ProviderCallError("p2")],
            primary_calls,
        ),
    )
    register_provider(
        "secondary",
        _make_fake(
            [ProviderCallError("s1"), ProviderCallError("s2")],
            secondary_calls,
        ),
    )
    res = generate_structured(
        "p", DummySchema,
        gateway_config=_auto_cfg(retries=2),
        deterministic_fallback=_fallback_ok,
    )
    assert res.fallback_used is True
    assert res.provider is None
    assert res.value == {"name": "fallback", "count": 0}
    assert res.error is not None
    assert res.attempts == 4


def test_all_providers_fail_and_fallback_also_fails_returns_none():
    primary_calls: list = []
    register_provider(
        "primary",
        _make_fake([ProviderCallError("p1"), ProviderCallError("p2")], primary_calls),
    )
    res = generate_structured(
        "p", DummySchema,
        gateway_config=_auto_cfg(retries=2, providers=("primary",)),
        deterministic_fallback=_fallback_bad,  # fails validation
    )
    assert res.value is None
    assert res.fallback_used is True
    assert res.validation_ok is False
    assert res.error is not None


def test_no_fallback_and_all_fail_returns_none_safely():
    primary_calls: list = []
    register_provider(
        "primary",
        _make_fake([ProviderCallError("boom")], primary_calls),
    )
    res = generate_structured(
        "p", DummySchema,
        gateway_config=_auto_cfg(retries=1, providers=("primary",)),
        deterministic_fallback=None,
    )
    assert res.value is None
    assert res.fallback_used is True
    assert "no deterministic_fallback" in (res.error or "")


# -------------------------------------------------------------------------
# Schema flexibility
# -------------------------------------------------------------------------

def test_callable_validator_schema():
    calls: list = []
    register_provider("primary", _make_fake(['{"x": 1}'], calls))

    def my_validator(d):
        if "x" not in d:
            raise ValueError("missing x")
        return d

    res = generate_structured(
        "p", my_validator,
        gateway_config=_auto_cfg(providers=("primary",)),
        deterministic_fallback=lambda p, s: {"x": 0},
    )
    assert res.value == {"x": 1}


def test_none_schema_is_passthrough():
    calls: list = []
    register_provider("primary", _make_fake(['{"whatever": true}'], calls))
    res = generate_structured(
        "p", None,
        gateway_config=_auto_cfg(providers=("primary",)),
        deterministic_fallback=lambda p, s: {"whatever": False},
    )
    assert res.value == {"whatever": True}


# -------------------------------------------------------------------------
# Trace completeness
# -------------------------------------------------------------------------

def test_trace_dict_shape():
    calls: list = []
    register_provider("primary", _make_fake(['{"name": "ok", "count": 1}'], calls))
    res = generate_structured(
        "p", DummySchema,
        gateway_config=_auto_cfg(providers=("primary",)),
        deterministic_fallback=_fallback_ok,
    )
    td = res.to_trace_dict()
    for k in (
        "provider", "model", "latency_ms", "attempts", "validation_ok",
        "fallback_used", "mode", "error", "provider_trace",
    ):
        assert k in td


# -------------------------------------------------------------------------
# Malformed JSON never crashes the caller
# -------------------------------------------------------------------------

def test_malformed_json_never_raises_to_caller():
    calls: list = []
    register_provider(
        "primary",
        _make_fake(["<<<<<not json>>>>>", "still not json"], calls),
    )
    res = generate_structured(
        "p", DummySchema,
        gateway_config=_auto_cfg(retries=2, providers=("primary",)),
        deterministic_fallback=_fallback_ok,
    )
    assert res.fallback_used is True
    assert res.value == {"name": "fallback", "count": 0}
