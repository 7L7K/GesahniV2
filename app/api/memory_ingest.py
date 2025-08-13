from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from app.deps.user import get_current_user_id
from app.security import rate_limit, verify_token


logger = logging.getLogger(__name__)

router = APIRouter(tags=["memory"], dependencies=[Depends(verify_token), Depends(rate_limit)])


class IngestResponse(BaseModel):
    status: str
    doc_hash: str | None = None
    chunk_count: int | None = None
    ids: list[str] | None = None
    headings: list[str] | None = None


@router.post("/memory/ingest", response_model=IngestResponse)
async def ingest_memory(
    request: Request,
    user_id: str = Depends(get_current_user_id),
    file: UploadFile | None = File(None),
    url: str | None = Form(None),
    source: str | None = Form(None),
):
    """Accept a file upload or URL and ingest into Qdrant as Markdown chunks."""
    try:
        from app.ingest.markitdown_ingest import ingest_path_or_url
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ingest_unavailable: {e}")

    path: Optional[str] = None
    tmp_path: Optional[str] = None
    try:
        if file is None and not url:
            raise HTTPException(status_code=400, detail="file_or_url_required")
        if file is not None:
            contents = await file.read()
            import tempfile
            import os
            fd, tmp_path = tempfile.mkstemp(prefix="ing_", suffix="_upload")
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(contents)
            except Exception:
                # Ensure descriptor is closed on any error to avoid leaks
                try:
                    os.close(fd)
                except Exception:
                    pass
                raise
            path = tmp_path
        res = ingest_path_or_url(user_id=user_id, source=source or (url or (getattr(file, "filename", None) or "upload")), path=path, url=url)
        return IngestResponse(**res)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("memory.ingest failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e) or "ingest_failed")
    finally:
        try:
            if tmp_path:
                import os
                os.remove(tmp_path)
        except Exception:
            pass


