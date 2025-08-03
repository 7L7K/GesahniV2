#!/usr/bin/env python
import asyncio
import sys

from app import embeddings

TEXT = sys.argv[1] if len(sys.argv) > 1 else "hello world"
ITERS = int(sys.argv[2]) if len(sys.argv) > 2 else 10

async def main() -> None:
    metrics = await embeddings.benchmark(TEXT, iterations=ITERS)
    print(metrics)

if __name__ == "__main__":
    asyncio.run(main())
