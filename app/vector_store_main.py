from __future__ import annotations

import argparse

from app.memory.api import invalidate_cache


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser("vector_store")
    sub = parser.add_subparsers(dest="command")

    p_inv = sub.add_parser("invalidate", help="Remove cached answer for prompt")
    p_inv.add_argument("prompt", help="Original prompt text")

    args = parser.parse_args(argv)
    if args.command == "invalidate":
        invalidate_cache(args.prompt)
    else:  # pragma: no cover - CLI usage
        parser.print_help()
