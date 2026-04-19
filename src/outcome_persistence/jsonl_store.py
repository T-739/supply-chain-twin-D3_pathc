"""outcome_persistence/jsonl_store.py — Path C Phase 1 JSONL store.

Append-only JSONL persistence with crash-resilient read:
  - each line is a complete JSON object, canonically serialized
  - lines end with '\\n' and are independently parseable
  - read_all() skips a truncated / corrupt trailing line rather than
    raising, so a reader can still recover all complete prior rows
    after a mid-write crash.

No wall-clock input. No uuid4. No access to data/cases/*.json.
"""

from __future__ import annotations

import json
import os
from typing import Any, Iterable, Iterator


def _canonical_line(obj: Any) -> str:
    """One line of canonical JSON. Keys sorted; compact separators."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class JSONLStore:
    """Append-only JSONL file store."""

    def __init__(self, path: str | os.PathLike) -> None:
        self._path = os.fspath(path)

    @property
    def path(self) -> str:
        return self._path

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def append(self, obj: dict) -> None:
        """Append a single object as a JSONL line and fsync."""
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(_canonical_line(obj))
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())

    def append_many(self, objs: Iterable[dict]) -> int:
        """Append many objects in order. Returns count written."""
        n = 0
        with open(self._path, "a", encoding="utf-8") as f:
            for obj in objs:
                f.write(_canonical_line(obj))
                f.write("\n")
                n += 1
            f.flush()
            os.fsync(f.fileno())
        return n

    def write_all(self, objs: Iterable[dict]) -> int:
        """Overwrite the store with the given objects. Returns count written."""
        n = 0
        tmp_path = self._path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            for obj in objs:
                f.write(_canonical_line(obj))
                f.write("\n")
                n += 1
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, self._path)
        return n

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def exists(self) -> bool:
        return os.path.exists(self._path)

    def read_all(self) -> list[dict]:
        """Return every complete JSON line. Tolerates a truncated tail."""
        return list(self.iter_lines())

    def iter_lines(self) -> Iterator[dict]:
        """Yield each complete JSON object in file order."""
        if not self.exists():
            return
        with open(self._path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.rstrip("\n").rstrip("\r")
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    # Crash tolerance: skip the partial trailing line.
                    return
