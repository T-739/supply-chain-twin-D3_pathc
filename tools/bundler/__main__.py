"""CLI entry for the B5 bundler.

Example::

    python -m tools.bundler \\
        --harness-dir runs/phase3_demo \\
        --bundles-root bundles \\
        --bundle-id demo_default_3mode
"""

from __future__ import annotations

import argparse
import json
import sys

from tools.bundler.bundler import BundlerError, build_bundle_from_harness_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Repackage a harness output directory into the B5 bundle "
            "layout. Read-only; no runtime code is invoked."
        )
    )
    parser.add_argument("--harness-dir", required=True)
    parser.add_argument("--bundles-root", required=True)
    parser.add_argument("--bundle-id", required=True)
    parser.add_argument(
        "--variant-tag",
        action="append",
        default=None,
        metavar="TAG",
        help=(
            "Restrict to an explicit ordered variant tag list. "
            "Repeatable. Omitted = auto-discover by scanning the "
            "harness directory."
        ),
    )
    parser.add_argument("--source-notes", default="")
    args = parser.parse_args(argv)

    try:
        metadata = build_bundle_from_harness_dir(
            harness_dir=args.harness_dir,
            bundles_root=args.bundles_root,
            bundle_id=args.bundle_id,
            variant_tags=args.variant_tag,
            source_notes=args.source_notes,
        )
    except BundlerError as exc:
        print(f"bundler error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(metadata, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
