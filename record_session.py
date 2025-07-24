import argparse
import asyncio
from pathlib import Path

from app.capture import record


def main() -> None:
    parser = argparse.ArgumentParser(description="Record a session")
    parser.add_argument("--duration", type=int, required=True)
    parser.add_argument("--output", type=str, required=True)
    args = parser.parse_args()

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    result = record(args.duration, str(out_dir))
    if asyncio.iscoroutine(result):
        result = asyncio.run(result)
    print(result)


if __name__ == "__main__":
    main()
