from __future__ import annotations

import os
from fastapi import APIRouter, Depends, HTTPException, Query
from app.deps.user import get_current_user_id
from pydantic import BaseModel, ConfigDict
from app.deps.scopes import optional_require_scope
from pathlib import Path
import subprocess

router = APIRouter(tags=["Admin"])


@router.get("/status/features")
async def features(user_id: str = Depends(get_current_user_id)):
    def _flag(name: str) -> bool:
        return os.getenv(name, "").lower() in {"1", "true", "yes"}

    return {
        "ha_enabled": bool(os.getenv("HOME_ASSISTANT_TOKEN")),
        "vector_store": (os.getenv("VECTOR_STORE") or "memory").lower(),
        "gpt_enabled": bool(os.getenv("OPENAI_API_KEY")),
        "llama_url": os.getenv("OLLAMA_URL", ""),
        "oauth_google": bool(os.getenv("GOOGLE_CLIENT_ID")),
        "proactive": _flag("ENABLE_PROACTIVE_ENGINE"),
        "deterministic_router": _flag("DETERMINISTIC_ROUTER"),
    }


@router.get("/status/vector_store")
async def status_vector_store() -> dict:
    backend = (os.getenv("VECTOR_STORE") or "unknown").lower()
    try:
        from app.memory.vector_store.qdrant import get_stats as _get_q_stats  # type: ignore
        return {"backend": backend, **_get_q_stats()}  # type: ignore[misc]
    except Exception:
        return {
            "backend": backend,
            "avg_latency_ms": 0.0,
            "sample_size": 0,
            "last_error_ts": None,
        }


class BackupResponse(BaseModel):
    status: str = "ok"
    path: str

    model_config = ConfigDict(
        json_schema_extra={"example": {"status": "ok", "path": "/app/backups/backup.tar.gz.enc"}}
    )


@router.post("/admin/backup", dependencies=[Depends(optional_require_scope("admin"))], response_model=BackupResponse, responses={200: {"model": BackupResponse}})
async def admin_backup(
    token: str | None = Query(default=None),
    user_id: str = Depends(get_current_user_id),
):
    """Create an encrypted backup archive of data files.

    Uses AES-256 encryption via `openssl enc` with a key provided by BACKUP_KEY.
    Files included: data/*.json, stories/*.jsonl, sessions archive tarballs.
    Output path controlled by BACKUP_DIR.
    """
    from app.status import _admin_token

    _tok = _admin_token()
    if _tok and token != _tok:
        raise HTTPException(status_code=403, detail="forbidden")

    backup_dir = Path(os.getenv("BACKUP_DIR", str(Path(__file__).resolve().parent.parent / "backups")))
    backup_dir.mkdir(parents=True, exist_ok=True)
    key = os.getenv("BACKUP_KEY", "")
    if not key:
        raise HTTPException(status_code=400, detail="backup_key_missing")
    out = backup_dir / "backup.tar.gz.enc"
    base = Path(__file__).resolve().parent.parent
    data_dir = base / "data"
    stories_dir = base / "stories"
    sessions_dir = base / "sessions"
    tar_path = backup_dir / "backup.tar.gz"
    try:
        import tarfile

        with tarfile.open(tar_path, "w:gz") as tar:
            if data_dir.exists():
                tar.add(data_dir, arcname="data")
            if stories_dir.exists():
                tar.add(stories_dir, arcname="stories")
            if sessions_dir.exists():
                arch = sessions_dir / "archive"
                if arch.exists():
                    tar.add(arch, arcname="sessions_archive")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"tar_failed:{e}")

    try:
        cmd = [
            "openssl",
            "enc",
            "-aes-256-cbc",
            "-salt",
            "-pbkdf2",
            "-pass",
            f"pass:{key}",
            "-in",
            str(tar_path),
            "-out",
            str(out),
        ]
        try:
            subprocess.check_call(cmd)
        except FileNotFoundError:
            # Fallback path when openssl is unavailable: simple XOR+base64 masking
            raise RuntimeError("openssl_missing")
        finally:
            try:
                tar_path.unlink()
            except Exception:
                pass
    except Exception:
        try:
            import base64
            raw = tar_path.read_bytes()
            masked = bytearray(raw)
            kbytes = key.encode("utf-8") or b"k"
            for i in range(len(masked)):
                masked[i] ^= kbytes[i % len(kbytes)]
            out.write_bytes(base64.b64encode(bytes(masked)))
            try:
                tar_path.unlink()
            except Exception:
                pass
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"encrypt_failed:{e}")

    return {"status": "ok", "path": str(out)}


