"""
llm_backend.py — Phase 2 LLM infrastructure layer.

A single, reliable entry point for structured-output LLM calls with:

  * OpenAI primary / Anthropic secondary provider order (configurable).
  * JSON parse + schema validation (pydantic BaseModel or callable validator).
  * Retry on parse / validation failure.
  * Fallback to the next provider, then to a deterministic function.
  * A global feature flag that forces deterministic-only mode.
  * A trace-ready `LLMResult` carrying provider, model, latency, attempts,
    validation outcome, and fallback-used flag.

Scope note (Phase 2)
--------------------
This module is intentionally self-contained. It does NOT import anything
from `src/agents/`, `src/graph.py`, `src/evaluation.py`, or `src/supervisor.py`,
and it is not yet wired into the graph. Phase 3+ will consume it.

Non-negotiable rules this module respects:
  * LLM output never redefines evaluation truth, oracle labels, or numeric
    ground truth. Validation happens here; semantic truth stays upstream.
  * The deterministic fallback path remains mandatory and must always run
    when `mode="off"` or when all providers fail.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from llm_providers import (  # noqa: F401  (re-exported for tests)
    ProviderCallError,
    ProviderError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)

# ---------------------------------------------------------------------------
# Global feature flag
# ---------------------------------------------------------------------------

# Accepted values (case-insensitive): "off" (default), "auto".
# "off"  → generate_structured never calls a provider; always deterministic.
# "auto" → try configured providers, fall back to deterministic on failure.
_LLM_MODE_ENV = "SUPPLY_CHAIN_TWIN_LLM_MODE"


def current_llm_mode() -> str:
    raw = os.environ.get(_LLM_MODE_ENV, "off")
    return str(raw).strip().lower() or "off"


def is_llm_enabled() -> bool:
    return current_llm_mode() == "auto"


# ---------------------------------------------------------------------------
# Configuration dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProviderConfig:
    """One provider's call parameters.

    `name` must match a key in the provider registry (see _PROVIDER_REGISTRY).
    """

    name: str
    model: str
    temperature: float = 0.0
    max_tokens: int = 1024
    timeout_s: float = 30.0
    api_key_env: str | None = None  # override the provider's default env var


@dataclass(frozen=True)
class GatewayConfig:
    """Top-level Phase 2 gateway configuration."""

    providers: tuple[ProviderConfig, ...]
    max_retries_per_provider: int = 2
    # When the global flag is "off", generate_structured skips providers entirely.
    # When "auto", providers are tried in order.
    force_mode: str | None = None  # None → read env; "off" / "auto" → override


def default_gateway_config() -> GatewayConfig:
    """Conservative default: OpenAI primary, Anthropic secondary, 2 retries."""
    return GatewayConfig(
        providers=(
            ProviderConfig(name="openai", model="gpt-4o-mini"),
            ProviderConfig(name="anthropic", model="claude-3-5-haiku-latest"),
        ),
        max_retries_per_provider=2,
    )


# ---------------------------------------------------------------------------
# Result type (trace-ready)
# ---------------------------------------------------------------------------


@dataclass
class LLMResult:
    """Outcome of a `generate_structured` call, suitable for trace logging."""

    value: dict[str, Any] | None
    provider: str | None
    model: str | None
    latency_ms: int
    attempts: int
    validation_ok: bool
    fallback_used: bool
    mode: str
    error: str | None = None
    provider_trace: list[dict[str, Any]] = field(default_factory=list)

    def to_trace_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "latency_ms": self.latency_ms,
            "attempts": self.attempts,
            "validation_ok": self.validation_ok,
            "fallback_used": self.fallback_used,
            "mode": self.mode,
            "error": self.error,
            "provider_trace": list(self.provider_trace),
        }


# ---------------------------------------------------------------------------
# Provider registry (adapters injected here for dependency isolation + tests)
# ---------------------------------------------------------------------------


class _ProviderAdapter(Protocol):
    def __call__(
        self,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
        timeout_s: float,
        system: str | None = None,
        api_key_env: str | None = None,
    ) -> tuple[str, dict]: ...


def _default_openai_adapter(
    prompt, model, temperature, max_tokens, timeout_s, system=None, api_key_env=None,
):
    from llm_providers import openai_provider
    kwargs = {} if api_key_env is None else {"api_key_env": api_key_env}
    return openai_provider.generate_raw(
        prompt=prompt, model=model, temperature=temperature,
        max_tokens=max_tokens, timeout_s=timeout_s, system=system, **kwargs,
    )


def _default_anthropic_adapter(
    prompt, model, temperature, max_tokens, timeout_s, system=None, api_key_env=None,
):
    from llm_providers import anthropic_provider
    kwargs = {} if api_key_env is None else {"api_key_env": api_key_env}
    return anthropic_provider.generate_raw(
        prompt=prompt, model=model, temperature=temperature,
        max_tokens=max_tokens, timeout_s=timeout_s, system=system, **kwargs,
    )


_PROVIDER_REGISTRY: dict[str, _ProviderAdapter] = {
    "openai": _default_openai_adapter,
    "anthropic": _default_anthropic_adapter,
}


def register_provider(name: str, adapter: _ProviderAdapter) -> None:
    """Register (or override) a provider adapter. Tests use this."""
    _PROVIDER_REGISTRY[name] = adapter


def get_registered_providers() -> tuple[str, ...]:
    return tuple(_PROVIDER_REGISTRY.keys())


# ---------------------------------------------------------------------------
# Parsing + validation
# ---------------------------------------------------------------------------


class ValidationFailure(Exception):
    """Raised internally when parsed JSON fails schema validation."""


_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def extract_json_object(raw_text: str) -> dict[str, Any]:
    """Extract a JSON object from raw_text.

    Tolerates markdown code fences. Raises ValueError if nothing parseable.
    """
    if raw_text is None:
        raise ValueError("raw_text is None")
    text = raw_text.strip()
    if not text:
        raise ValueError("raw_text is empty")

    # Try direct parse first.
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None

    if parsed is None:
        m = _FENCED_JSON_RE.search(text)
        if m:
            try:
                parsed = json.loads(m.group(1))
            except json.JSONDecodeError:
                parsed = None

    if parsed is None:
        # Last resort: find the first balanced {...} block.
        start = text.find("{")
        end = text.rfind("}")
        if 0 <= start < end:
            try:
                parsed = json.loads(text[start : end + 1])
            except json.JSONDecodeError as exc:
                raise ValueError(f"could not parse JSON: {exc}")
        else:
            raise ValueError("no JSON object found in raw_text")

    if not isinstance(parsed, dict):
        raise ValueError(
            f"expected JSON object at top level, got {type(parsed).__name__}"
        )
    return parsed


def _validate(parsed: dict[str, Any], schema: Any) -> dict[str, Any]:
    """Validate a parsed dict against `schema`.

    Supported schema kinds:
      * None   → no validation (passthrough).
      * pydantic BaseModel subclass → schema.model_validate(...).model_dump().
      * callable(dict) -> dict or raises → called directly.
    """
    if schema is None:
        return parsed

    # Pydantic model?
    model_validate = getattr(schema, "model_validate", None)
    if callable(model_validate):
        try:
            obj = model_validate(parsed)
        except Exception as exc:  # pydantic ValidationError or similar
            raise ValidationFailure(str(exc)) from exc
        dump = getattr(obj, "model_dump", None)
        return dump() if callable(dump) else dict(parsed)

    if callable(schema):
        try:
            result = schema(parsed)
        except Exception as exc:
            raise ValidationFailure(str(exc)) from exc
        if not isinstance(result, dict):
            raise ValidationFailure(
                f"validator must return a dict, got {type(result).__name__}"
            )
        return result

    raise ValidationFailure(
        f"unsupported schema kind: {type(schema).__name__}"
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def generate_structured(
    prompt: str,
    schema: Any,
    *,
    gateway_config: GatewayConfig | None = None,
    deterministic_fallback: Callable[[str, Any], dict[str, Any]] | None = None,
    system: str | None = None,
) -> LLMResult:
    """Produce a validated structured output with retry + fallback.

    Parameters
    ----------
    prompt:
        User prompt sent to the provider.
    schema:
        Pydantic model class, callable(dict)->dict, or None. Governs validation.
    gateway_config:
        Provider order, retry counts, timeouts. Defaults to
        `default_gateway_config()`.
    deterministic_fallback:
        Callable `(prompt, schema) -> dict`. Called when the global flag is
        "off", when no providers are available, or when every provider
        exhausts its retries.
    system:
        Optional system message.

    Returns
    -------
    LLMResult
        Always returned; never raises to the caller when
        `deterministic_fallback` is provided. If no fallback is provided and
        every path fails, LLMResult.value is None with `error` set.
    """
    gateway_config = gateway_config or default_gateway_config()
    mode = (gateway_config.force_mode or current_llm_mode()).strip().lower()

    wall_start = time.perf_counter()
    provider_trace: list[dict[str, Any]] = []
    attempts = 0

    # Deterministic-only short-circuit.
    if mode != "auto":
        value, err = _run_fallback(prompt, schema, deterministic_fallback)
        latency_ms = int((time.perf_counter() - wall_start) * 1000)
        return LLMResult(
            value=value,
            provider=None,
            model=None,
            latency_ms=latency_ms,
            attempts=0,
            validation_ok=value is not None,
            fallback_used=True,
            mode=mode,
            error=err,
            provider_trace=provider_trace,
        )

    # Auto mode: try each configured provider in order.
    last_error: str | None = None
    for pc in gateway_config.providers:
        adapter = _PROVIDER_REGISTRY.get(pc.name)
        if adapter is None:
            provider_trace.append({
                "provider": pc.name, "model": pc.model,
                "event": "unregistered", "detail": "no adapter in registry",
            })
            last_error = f"provider '{pc.name}' not registered"
            continue

        for attempt in range(1, gateway_config.max_retries_per_provider + 1):
            attempts += 1
            event: dict[str, Any] = {
                "provider": pc.name, "model": pc.model, "attempt": attempt,
            }
            try:
                raw_text, pmeta = adapter(
                    prompt=prompt,
                    model=pc.model,
                    temperature=pc.temperature,
                    max_tokens=pc.max_tokens,
                    timeout_s=pc.timeout_s,
                    system=system,
                    api_key_env=pc.api_key_env,
                )
            except ProviderUnavailableError as exc:
                event.update({"event": "unavailable", "detail": str(exc)})
                provider_trace.append(event)
                last_error = f"{pc.name}: unavailable ({exc})"
                break  # unavailable → skip this provider entirely
            except ProviderTimeoutError as exc:
                event.update({"event": "timeout", "detail": str(exc)})
                provider_trace.append(event)
                last_error = f"{pc.name}: timeout ({exc})"
                continue  # retry
            except ProviderError as exc:
                event.update({"event": "call_error", "detail": str(exc)})
                provider_trace.append(event)
                last_error = f"{pc.name}: call_error ({exc})"
                continue  # retry
            except Exception as exc:  # defensive catch
                event.update({"event": "unexpected_error", "detail": str(exc)})
                provider_trace.append(event)
                last_error = f"{pc.name}: unexpected_error ({exc})"
                continue  # retry

            # Parse
            try:
                parsed = extract_json_object(raw_text)
            except Exception as exc:
                event.update({
                    "event": "parse_error", "detail": str(exc),
                    "latency_ms": pmeta.get("latency_ms"),
                })
                provider_trace.append(event)
                last_error = f"{pc.name}: parse_error ({exc})"
                continue  # retry

            # Validate
            try:
                validated = _validate(parsed, schema)
            except ValidationFailure as exc:
                event.update({
                    "event": "validation_error", "detail": str(exc),
                    "latency_ms": pmeta.get("latency_ms"),
                })
                provider_trace.append(event)
                last_error = f"{pc.name}: validation_error ({exc})"
                continue  # retry

            # Success
            event.update({
                "event": "ok",
                "latency_ms": pmeta.get("latency_ms"),
            })
            provider_trace.append(event)
            total_latency_ms = int((time.perf_counter() - wall_start) * 1000)
            return LLMResult(
                value=validated,
                provider=pc.name,
                model=pc.model,
                latency_ms=total_latency_ms,
                attempts=attempts,
                validation_ok=True,
                fallback_used=False,
                mode=mode,
                error=None,
                provider_trace=provider_trace,
            )

    # All providers exhausted → deterministic fallback.
    value, err = _run_fallback(prompt, schema, deterministic_fallback)
    total_latency_ms = int((time.perf_counter() - wall_start) * 1000)
    combined_error = last_error if value is not None else (
        f"{last_error}; fallback_error={err}" if last_error else err
    )
    return LLMResult(
        value=value,
        provider=None,
        model=None,
        latency_ms=total_latency_ms,
        attempts=attempts,
        validation_ok=value is not None,
        fallback_used=True,
        mode=mode,
        error=combined_error,
        provider_trace=provider_trace,
    )


def _run_fallback(
    prompt: str,
    schema: Any,
    deterministic_fallback: Callable[[str, Any], dict[str, Any]] | None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Run the deterministic fallback and validate its output against schema."""
    if deterministic_fallback is None:
        return None, "no deterministic_fallback provided"
    try:
        candidate = deterministic_fallback(prompt, schema)
    except Exception as exc:
        return None, f"deterministic_fallback raised: {exc}"
    if not isinstance(candidate, dict):
        return None, (
            f"deterministic_fallback must return a dict, "
            f"got {type(candidate).__name__}"
        )
    try:
        validated = _validate(candidate, schema)
    except ValidationFailure as exc:
        return None, f"deterministic_fallback output failed validation: {exc}"
    return validated, None
