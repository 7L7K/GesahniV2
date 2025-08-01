# app/alias_store.py
import json, pathlib, contextlib, asyncio
import aiofiles

_PATH = pathlib.Path("alias_store.json")
_LOCK = asyncio.Lock()

async def _load() -> dict[str, str]:
    try:
        async with aiofiles.open(_PATH, "r") as f:
            return json.loads(await f.read())
    except FileNotFoundError:
        return {}

async def get(name: str) -> str | None:
    async with _LOCK:
        data = await _load()
        return data.get(name.lower().strip())

async def set(name: str, entity_id: str):
    async with _LOCK:
        data = await _load()
        data[name.lower().strip()] = entity_id
        async with aiofiles.open(_PATH, "w") as f:
            await f.write(json.dumps(data, indent=2))
