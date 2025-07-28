import asyncio
from app.history import append_history

async def main():
    await append_history("unit test", "test", "ok")
    print("✅ Test write done")

asyncio.run(main())
