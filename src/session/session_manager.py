"""session/session_manager.py — Path C Phase 1 save / load / replay.

Phase 1 responsibilities:
  - serialize a SessionArtifact to a canonical on-disk form
  - load it back losslessly
  - expose a ``replay`` helper that re-serializes a loaded artifact
    (used by test_replay_byte_identical to verify save → load → replay
    is byte-equal to the original save).

On-disk layout (inside ``out_dir``):
  - ``session_artifact.json``   — canonical JSON of the full artifact
  - ``memory.jsonl``            — one MemoryRecord dict per line

Determinism rules (Roadmap §1.D):
  - canonical JSON everywhere (sort_keys, compact separators)
  - no wall-clock in the serialization path
  - fsync on each write so a fresh process sees the same bytes.

Does NOT import evaluation / action_code_mapper. Does NOT access
data/cases/*.json.
"""

from __future__ import annotations

import json
import os
from typing import Any

from session.digests import canonical_json
from session.session_schema import SessionArtifact


ARTIFACT_FILENAME = "session_artifact.json"
MEMORY_FILENAME = "memory.jsonl"


def save_session(artifact: SessionArtifact, out_dir: str | os.PathLike) -> dict:
    """Write artifact JSON + memory JSONL into out_dir. Returns paths."""
    out_dir = os.fspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    artifact_path = os.path.join(out_dir, ARTIFACT_FILENAME)
    memory_path = os.path.join(out_dir, MEMORY_FILENAME)

    payload = artifact.model_dump()
    with open(artifact_path, "w", encoding="utf-8") as f:
        f.write(canonical_json(payload))
        f.flush()
        os.fsync(f.fileno())

    records = payload.get("memory_snapshot", {}).get("records") or []
    with open(memory_path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(canonical_json(rec))
            f.write("\n")
        f.flush()
        os.fsync(f.fileno())

    return {"artifact_path": artifact_path, "memory_path": memory_path}


def load_session(out_dir: str | os.PathLike) -> SessionArtifact:
    """Load a saved SessionArtifact from out_dir. Loss-less roundtrip."""
    out_dir = os.fspath(out_dir)
    artifact_path = os.path.join(out_dir, ARTIFACT_FILENAME)
    with open(artifact_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return SessionArtifact.model_validate(data)


def replay_session_bytes(artifact: SessionArtifact) -> str:
    """Canonical bytes for a SessionArtifact.

    The bytes produced here are exactly the bytes written to
    ``session_artifact.json`` by ``save_session``. A loaded artifact
    re-serialized with this function must be byte-identical to the
    original save.
    """
    return canonical_json(artifact.model_dump())
