from __future__ import annotations
from app.memory.vector_store import *  # noqa: F401,F403

if __name__ == "__main__":
    import argparse
    from app.memory.api import invalidate_cache
    p = argparse.ArgumentParser("vector_store"); sub = p.add_subparsers(dest="cmd")
    inv = sub.add_parser("invalidate"); inv.add_argument("prompt")
    args = p.parse_args()
    invalidate_cache(args.prompt) if args.cmd == "invalidate" else p.print_help()
