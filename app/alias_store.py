# app/alias_store.py
import json, pathlib, contextlib, asyncio

_PATH = pathlib.Path("alias_store.json")
_LOCK = asyncio.Lock()

def _load() -> dict[str, str]:
    with contextlib.suppress(FileNotFoundError):
        return json.loads(_PATH.read_text())
    return {}

async def get(name: str) -> str | None:
    async with _LOCK:
        return _load().get(name.lower().strip())

async def set(name: str, entity_id: str):
    async with _LOCK:
        data = _load()
        data[name.lower().strip()] = entity_id
        _PATH.write_text(json.dumps(data, indent=2))
