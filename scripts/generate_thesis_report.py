#!/usr/bin/env python3
"""scripts/generate_thesis_report.py — render a thesis markdown from a compare report.

Usage::

    python scripts/generate_thesis_report.py \\
        --compare-report runs/phase3/compare_report.json \\
        --out           runs/phase3/thesis_report.md

Pure deterministic rendering; same input JSON in → same markdown out.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


_PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_DIR / "src"))

from session.session_compare import render_thesis_markdown  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render thesis markdown from compare report")
    parser.add_argument("--compare-report", required=True,
                        help="Path to compare_report.json")
    parser.add_argument("--out", required=True,
                        help="Output markdown path")
    args = parser.parse_args(argv)

    with open(args.compare_report, "r", encoding="utf-8") as f:
        compare = json.load(f)

    md = render_thesis_markdown(compare)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(md)
        f.flush()
        os.fsync(f.fileno())
    print(f"thesis_report={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
