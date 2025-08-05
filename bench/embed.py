#!/usr/bin/env python
import asyncio
import sys

from app import embeddings
from app.deps.user import get_current_user_id

TEXT = sys.argv[1] if len(sys.argv) > 1 else "hello world"
ITERS = int(sys.argv[2]) if len(sys.argv) > 2 else 10


async def main() -> None:
    user_id = get_current_user_id()
    metrics = await embeddings.benchmark(TEXT, iterations=ITERS, user_id=user_id)
    print(metrics)


if __name__ == "__main__":
    asyncio.run(main())
