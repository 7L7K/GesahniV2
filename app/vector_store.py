from __future__ import annotations
from app.memory.vector_store import *  # noqa: F401,F403

if __name__ == "__main__":
    import argparse
    from app.memory.api import invalidate_cache
    from app.jobs.migrate_chroma_to_qdrant import main as migrate_main  # noqa: F401

    parser = argparse.ArgumentParser("vector_store")
    sub = parser.add_subparsers(dest="cmd")
    inv = sub.add_parser("invalidate", help="Remove cached answer for prompt")
    inv.add_argument("prompt")

    mig = sub.add_parser("migrate", help="Run Chroma→Qdrant migration helper")
    mig.add_argument("action", choices=["inventory", "export", "migrate"], nargs="?", default="inventory")
    mig.add_argument("--dry-run", action="store_true")
    mig.add_argument("--out-dir", default=None)

    args = parser.parse_args()
    if args.cmd == "invalidate":
        invalidate_cache(args.prompt)
    elif args.cmd == "migrate":
        argv = [args.action]
        if args.dry_run:
            argv.append("--dry-run")
        if args.out_dir:
            argv.extend(["--out-dir", args.out_dir])
        migrate_main(argv)
    else:
        parser.print_help()
