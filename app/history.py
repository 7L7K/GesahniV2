import asyncio
import json
from datetime import datetime
from pathlib import Path

HISTORY_FILE = Path(__file__).resolve().parent.parent / "history.json"
_lock = asyncio.Lock()

async def append_history(req_id: str, prompt: str, engine_used: str, response: str) -> None:
    record = {
        "req_id": req_id,
        "prompt": prompt,
        "engine_used": engine_used,
        "response": response,
        "timestamp": datetime.utcnow().isoformat(),
    }
    async with _lock:
        await asyncio.to_thread(_append, record)

def _append(record: dict) -> None:
    if HISTORY_FILE.exists():
        data = json.loads(HISTORY_FILE.read_text())
    else:
        data = []
    data.append(record)
    HISTORY_FILE.write_text(json.dumps(data, indent=2))
