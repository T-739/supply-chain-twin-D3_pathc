"""OpenAI provider adapter (Phase 2).

Lazy-imports `openai`. Returns raw string output plus a small meta dict.
No prompt templates, no schema awareness.
"""

from __future__ import annotations

import os
import time

from . import ProviderCallError, ProviderTimeoutError, ProviderUnavailableError

PROVIDER_NAME = "openai"
DEFAULT_API_KEY_ENV = "OPENAI_API_KEY"


def generate_raw(
    prompt: str,
    model: str,
    temperature: float,
    max_tokens: int,
    timeout_s: float,
    system: str | None = None,
    api_key_env: str = DEFAULT_API_KEY_ENV,
) -> tuple[str, dict]:
    """Call OpenAI chat completions and return (raw_text, meta).

    Raises
    ------
    ProviderUnavailableError
        SDK not installed or API key not set.
    ProviderTimeoutError
        Request exceeded timeout_s.
    ProviderCallError
        Any other OpenAI-side failure.
    """
    try:
        import openai  # noqa: F401
        from openai import OpenAI
    except Exception as exc:  # pragma: no cover — env-dependent
        raise ProviderUnavailableError(
            f"openai SDK not importable: {exc}"
        ) from exc

    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise ProviderUnavailableError(
            f"OpenAI API key not set (env var {api_key_env} missing)."
        )

    client = OpenAI(api_key=api_key, timeout=timeout_s)

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    start = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
    except Exception as exc:  # pragma: no cover — requires live API
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        msg = str(exc).lower()
        if "timeout" in msg or "timed out" in msg:
            raise ProviderTimeoutError(
                f"openai call timed out after ~{elapsed_ms}ms: {exc}"
            ) from exc
        raise ProviderCallError(f"openai call failed: {exc}") from exc
    latency_ms = int((time.perf_counter() - start) * 1000)

    try:
        raw_text = response.choices[0].message.content or ""
    except Exception as exc:  # pragma: no cover
        raise ProviderCallError(
            f"openai response shape unexpected: {exc}"
        ) from exc

    meta = {
        "provider": PROVIDER_NAME,
        "model": model,
        "latency_ms": latency_ms,
    }
    return raw_text, meta
