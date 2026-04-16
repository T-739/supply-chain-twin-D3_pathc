"""
llm_providers — Phase 2 provider adapters.

Each adapter exposes a single function::

    generate_raw(
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
        timeout_s: float,
        system: str | None = None,
    ) -> tuple[str, dict]

returning (raw_text, meta) where meta carries provider-side observability
fields (provider, model, latency_ms).

Adapters MUST lazy-import their SDKs inside generate_raw() so this package
remains importable in environments without openai / anthropic installed.
If the SDK is missing or the API key is not configured, adapters raise
`ProviderUnavailableError`.

These modules contain no business logic, no prompts, and no agent awareness.
"""

from __future__ import annotations


class ProviderError(RuntimeError):
    """Base class for provider-side errors."""


class ProviderUnavailableError(ProviderError):
    """Raised when the SDK is missing, the API key is absent, or the
    provider cannot be reached at all. Signals the gateway to try the
    next provider or fall back to deterministic mode."""


class ProviderTimeoutError(ProviderError):
    """Raised when a provider call exceeds timeout_s."""


class ProviderCallError(ProviderError):
    """Raised on any other provider-side failure (HTTP error, rate limit,
    malformed transport response, etc.)."""


__all__ = [
    "ProviderError",
    "ProviderUnavailableError",
    "ProviderTimeoutError",
    "ProviderCallError",
]
