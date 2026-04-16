"""Anthropic provider adapter (Phase 2).

Lazy-imports `anthropic`. Returns raw string output plus a small meta dict.
No prompt templates, no schema awareness.
"""

from __future__ import annotations

import os
import time

from . import ProviderCallError, ProviderTimeoutError, ProviderUnavailableError

PROVIDER_NAME = "anthropic"
DEFAULT_API_KEY_ENV = "ANTHROPIC_API_KEY"


def generate_raw(
    prompt: str,
    model: str,
    temperature: float,
    max_tokens: int,
    timeout_s: float,
    system: str | None = None,
    api_key_env: str = DEFAULT_API_KEY_ENV,
) -> tuple[str, dict]:
    """Call Anthropic Messages API and return (raw_text, meta).

    Raises
    ------
    ProviderUnavailableError
        SDK not installed or API key not set.
    ProviderTimeoutError
        Request exceeded timeout_s.
    ProviderCallError
        Any other Anthropic-side failure.
    """
    try:
        import anthropic  # noqa: F401
        from anthropic import Anthropic
    except Exception as exc:  # pragma: no cover — env-dependent
        raise ProviderUnavailableError(
            f"anthropic SDK not importable: {exc}"
        ) from exc

    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise ProviderUnavailableError(
            f"Anthropic API key not set (env var {api_key_env} missing)."
        )

    client = Anthropic(api_key=api_key, timeout=timeout_s)

    # Anthropic asks for a separate system arg rather than a message.
    start = time.perf_counter()
    try:
        response = client.messages.create(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            system=system or "",
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:  # pragma: no cover — requires live API
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        msg = str(exc).lower()
        if "timeout" in msg or "timed out" in msg:
            raise ProviderTimeoutError(
                f"anthropic call timed out after ~{elapsed_ms}ms: {exc}"
            ) from exc
        raise ProviderCallError(f"anthropic call failed: {exc}") from exc
    latency_ms = int((time.perf_counter() - start) * 1000)

    try:
        # Anthropic returns a list of content blocks; join text blocks.
        parts = []
        for block in getattr(response, "content", []) or []:
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
        raw_text = "".join(parts)
    except Exception as exc:  # pragma: no cover
        raise ProviderCallError(
            f"anthropic response shape unexpected: {exc}"
        ) from exc

    meta = {
        "provider": PROVIDER_NAME,
        "model": model,
        "latency_ms": latency_ms,
    }
    return raw_text, meta
