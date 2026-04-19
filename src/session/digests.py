"""session/digests.py — Path C Phase 1 deterministic-digest helpers.

All digest / canonical-JSON helpers in this module are pure and
deterministic. They do NOT use wall-clock input, uuid4, or any
nondeterministic ordering. They are the shared foundation for
``event_loop_c`` and ``session_manager``.

Hashing rule (owner point 4, roadmap §1.D):

    session_id = sha256(
        f"{seed}|{config_digest}|{event_stream_digest}|{initial_memory_digest}"
    ).hexdigest()  # full 64-char hex, no truncation

No wall-clock input, no uuid4. Callers that want a short id for
display must truncate at the display layer — the canonical id is
never truncated.

Canonical JSON rule:

  ``json.dumps(obj, sort_keys=True, separators=(",", ":"))``

This is the only serialization form Path C writes to disk or hashes.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable


# ---------------------------------------------------------------------------
# Canonical JSON
# ---------------------------------------------------------------------------


def _default_encoder(obj: Any) -> Any:
    """Fallback JSON encoder for objects json.dumps cannot natively handle.

    Supports:
      - pydantic BaseModel instances (via ``.model_dump()``)
      - datetime / date / time objects (via ``.isoformat()``)
      - Enum values (``.value``)
      - sets / frozensets → sorted lists

    Anything else raises TypeError so silent nondeterminism cannot slip
    through.
    """
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if hasattr(obj, "value") and hasattr(obj, "name"):
        return obj.value
    if isinstance(obj, (set, frozenset)):
        return sorted(obj)
    raise TypeError(
        f"Object of type {type(obj).__name__} is not canonical-JSON serializable"
    )


def canonical_json(obj: Any) -> str:
    """Deterministic canonical JSON serialization."""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        default=_default_encoder,
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# SHA-256 helpers
# ---------------------------------------------------------------------------


def sha256_hex(s: str) -> str:
    """SHA-256 hex digest of a UTF-8 string (64 chars)."""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Typed digests (one per Roadmap §1.D input)
# ---------------------------------------------------------------------------


def digest_config_dict(config: dict) -> str:
    """Digest of a config-shaped dict. Caller passes a plain dict."""
    return sha256_hex(canonical_json(config))


def _event_payload_to_canonical_dict(event: Any) -> dict:
    """Flatten an EventPayload into a deterministic, minimal dict.

    Does NOT import from event_schema to keep digests import-topology
    clean; relies on duck-typing of the event attributes.
    """
    et = event.event_type
    sev = event.severity
    ts = event.timestamp

    affected = []
    for a in event.affected_entities:
        affected.append({
            "entity_type": a.entity_type,
            "entity_id": a.entity_id,
        })

    return {
        "event_id": event.event_id,
        "event_type": et.value if hasattr(et, "value") else str(et),
        "severity": sev.value if hasattr(sev, "value") else str(sev),
        "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
        "affected_entities": affected,
        "parameters": dict(event.parameters or {}),
    }


def digest_event_stream(events: Iterable[Any]) -> str:
    """Digest of an ordered list of EventPayload objects."""
    payload = [_event_payload_to_canonical_dict(e) for e in events]
    return sha256_hex(canonical_json(payload))


def digest_memory_records(records: list[dict]) -> str:
    """Digest of a list of memory-record dicts (already canonical-form)."""
    return sha256_hex(canonical_json(list(records)))


# ---------------------------------------------------------------------------
# Session id
# ---------------------------------------------------------------------------


def compute_session_id(
    *,
    seed: int,
    config_digest: str,
    event_stream_digest: str,
    initial_memory_digest: str,
) -> str:
    """Full 64-char SHA-256 hex, per Roadmap §1.D."""
    return sha256_hex(
        f"{int(seed)}|{config_digest}|{event_stream_digest}|{initial_memory_digest}"
    )


# ---------------------------------------------------------------------------
# Stable foreign-key helper
# ---------------------------------------------------------------------------


def memory_record_id(session_id: str, event_timestamp: str, event_id: str) -> str:
    """Deterministic FK for SessionEventRecord.memory_record_id.

    Formed from the tuple that uniquely identifies a memory row
    (session_id, event_timestamp, event_id). No wall-clock input.
    """
    return sha256_hex(f"{session_id}|{event_timestamp}|{event_id}")
