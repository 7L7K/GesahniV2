import logging
import os
from pathlib import Path
from typing import Any, Dict, List

import httpx

logger = logging.getLogger(__name__)


class RAGClient:
    """Minimal client for interacting with a RAGFlow server.

    This client offers two high level helpers:

    * ``ingest`` – send a file or URL to RAGFlow for indexing.
    * ``query`` – retrieve top matching documents for a question.

    The implementation intentionally errs on the side of leniency: any
    network or parsing errors are logged and converted into safe defaults so
    callers never fail hard when the RAG backend is unavailable.
    """

    def __init__(self, base_url: str | None = None, timeout: float = 15.0) -> None:
        self.base_url = base_url or os.getenv("RAGFLOW_URL", "http://localhost:8001")
        self.timeout = timeout
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def ingest(self, path_or_url: str, *, collection: str) -> str:
        """Ingest a file or URL into ``collection``.

        Returns the document identifier on success or an empty string when the
        request fails. ``path_or_url`` may be a local file path or a remote
        URL. The method will pick the appropriate ingestion endpoint based on
        whether the path exists on disk.
        """

        try:
            if Path(path_or_url).exists():
                files = {"file": open(path_or_url, "rb")}
                data = {"collection": collection}
                resp = self._client.post("/api/v1/documents", data=data, files=files)
            else:
                payload = {"collection": collection, "url": path_or_url}
                resp = self._client.post("/api/v1/documents:ingest", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("id") or data.get("doc_id") or ""
        except Exception as e:  # pragma: no cover - network failures
            logger.warning("RAGFlow ingest failed: %s", e)
            return ""

    def query(
        self, question: str, *, collection: str, k: int = 6
    ) -> List[Dict[str, Any]]:
        """Return up to ``k`` docs from ``collection`` relevant to ``question``.

        Each result is normalized into ``{"text", "source", "loc"}``.
        Errors return an empty list instead of raising.
        """

        payload = {"query": question, "collection": collection, "top_k": k}
        try:
            resp = self._client.post("/api/v1/query", json=payload)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:  # pragma: no cover - network failures
            logger.warning("RAGFlow query failed: %s", e)
            return []

        docs: List[Dict[str, Any]] = []
        for item in data.get("documents") or data.get("matches") or []:
            meta = item.get("metadata", {})
            text = item.get("text") or item.get("page_content") or ""
            docs.append(
                {
                    "text": text,
                    "source": item.get("source") or meta.get("source") or "",
                    "loc": item.get("loc") or meta.get("loc") or "",
                }
            )
        return docs


__all__ = ["RAGClient"]
