"""B5 backend foundation (Phase-1 slice 1).

Read-only BFF over the B5 bundle contract. GET-only.
Reasoning for the name ``backend/`` (vs ``b5_backend/``):
the bundle contract is the single load-bearing surface for the
B5 read side; there is no second backend in this repo and none
planned. Matching the common full-stack convention keeps the
path predictable for future frontend contributors and avoids a
custom prefix that would need to be explained in every file.

Boundary:
  - no import of ``src/event_loop_c.py``, ``src/session/*``,
    ``src/api/*.py``, or ``app.py``
  - no write-path routes (validated by a route-scan test)
  - no reinterpretation of compare semantics
"""
