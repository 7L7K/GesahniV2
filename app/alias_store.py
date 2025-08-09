# app/alias_store.py
import os
import json
import pathlib
import asyncio
import aiofiles

# Allow overriding storage location; default to a data directory
_DEFAULT_PATH = pathlib.Path("data/alias_store.json")
_PATH = pathlib.Path(os.getenv("ALIAS_STORE_PATH", str(_DEFAULT_PATH)))
_LOCK = asyncio.Lock()


async def _ensure_parent_dir() -> None:
    parent = _PATH.parent
    if not parent.exists():
        parent.mkdir(parents=True, exist_ok=True)


async def _load() -> dict[str, str]:
    try:
        # Ensure directory exists before reads/writes
        await _ensure_parent_dir()
        async with aiofiles.open(_PATH, "r") as f:
            return json.loads(await f.read())
    except FileNotFoundError:
        return {}


async def get(name: str) -> str | None:
    async with _LOCK:
        data = await _load()
        return data.get(name.lower().strip())


async def set(name: str, entity_id: str) -> None:
    async with _LOCK:
        data = await _load()
        data[name.lower().strip()] = entity_id
        tmp_path = _PATH.with_suffix(".json.tmp")
        # Atomic write: write to temp then replace
        async with aiofiles.open(tmp_path, "w") as f:
            await f.write(json.dumps(data, indent=2))
        tmp_path.replace(_PATH)


async def get_all() -> dict[str, str]:
    async with _LOCK:
        return await _load()
