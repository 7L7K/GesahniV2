from __future__ import annotations
"""Unified vector store factory using VECTOR_DSN configuration."""


import logging
import os
import sys
from urllib.parse import parse_qs, urlparse

from .memory_store import MemoryVectorStore, VectorStore

logger = logging.getLogger(__name__)


class VectorStoreConfig:
    """Configuration parsed from VECTOR_DSN."""

    def __init__(self, dsn: str):
        self.dsn = dsn
        self.scheme = ""
        self.host = ""
        self.port = None
        self.path = ""
        self.username = ""
        self.password = ""
        self.params: dict[str, str] = {}

        if dsn:
            self._parse_dsn(dsn)

    def _parse_dsn(self, dsn: str) -> None:
        """Parse DSN into components."""
        try:
            parsed = urlparse(dsn)
            self.scheme = parsed.scheme.lower()
            self.host = parsed.hostname or ""
            self.port = parsed.port
            self.path = parsed.path.lstrip("/") if parsed.path else ""
            self.username = parsed.username or ""
            self.password = parsed.password or ""
            self.params = parse_qs(parsed.query)
            # Convert query params from lists to single values
            self.params = {k: v[0] if v else "" for k, v in self.params.items()}
        except Exception as e:
            logger.error("Failed to parse VECTOR_DSN=%s: %s", dsn, e)
            raise ValueError(f"Invalid VECTOR_DSN format: {dsn}") from e

    def get_param(self, key: str, default: str = "") -> str:
        """Get a query parameter with default."""
        return self.params.get(key, default)

    def get_param_bool(self, key: str, default: bool = False) -> bool:
        """Get a boolean query parameter."""
        val = self.get_param(key, "").lower()
        return val in {"1", "true", "yes", "on"} if val else default


def _strict_mode() -> bool:
    """Return True if strict init policy is enabled."""
    if (os.getenv("STRICT_VECTOR_STORE") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return True
    # Treat staging/production-like envs as strict by default
    env = (os.getenv("ENV") or os.getenv("APP_ENV") or "").strip().lower()
    if env in {"production", "prod", "staging", "preprod", "preview"}:
        return True
    return False


def create_vector_store() -> VectorStore:
    """Create vector store from VECTOR_DSN configuration.

    DSN Formats:
    - memory:// (in-memory store for tests)
    - chroma:///path/to/data (local ChromaDB)
    - chroma+cloud://tenant.database?api_key=xxx (Chroma Cloud)
    - qdrant://host:port?api_key=xxx (Qdrant HTTP)
    - qdrant+grpc://host:port?api_key=xxx (Qdrant gRPC)
    - dual://qdrant://host:port?api_key=xxx&chroma_path=/path (Dual read)

    Default: chroma:///.chroma_data (local ChromaDB)
    """
    dsn = os.getenv("VECTOR_DSN", "").strip()

    # Handle legacy VECTOR_STORE for backward compatibility
    if not dsn:
        legacy_store = os.getenv("VECTOR_STORE", "").strip().lower()
        if legacy_store:
            logger.warning("VECTOR_STORE is deprecated, use VECTOR_DSN instead")
            if legacy_store == "memory":
                dsn = "memory://"
            elif legacy_store == "chroma":
                chroma_path = os.getenv("CHROMA_PATH", ".chroma_data")
                dsn = f"chroma:///{chroma_path}"
            elif legacy_store == "cloud":
                api_key = os.getenv("CHROMA_API_KEY", "")
                tenant = os.getenv("CHROMA_TENANT_ID", "")
                database = os.getenv("CHROMA_DATABASE_NAME", "")
                dsn = f"chroma+cloud://{tenant}.{database}?api_key={api_key}"
            elif legacy_store == "qdrant":
                url = os.getenv("QDRANT_URL", "http://localhost:6333")
                api_key = os.getenv("QDRANT_API_KEY", "")
                if api_key:
                    dsn = f"qdrant://{url}?api_key={api_key}"
                else:
                    dsn = f"qdrant://{url}"
            elif legacy_store == "dual":
                # Dual mode requires both backends configured
                qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
                qdrant_api_key = os.getenv("QDRANT_API_KEY", "")
                chroma_path = os.getenv("CHROMA_PATH", ".chroma_data")
                if qdrant_api_key:
                    dsn = f"dual://qdrant://{qdrant_url}?api_key={qdrant_api_key}&chroma_path={chroma_path}"
                else:
                    dsn = f"dual://qdrant://{qdrant_url}&chroma_path={chroma_path}"

    # Default to local ChromaDB if no DSN provided
    if not dsn:
        dsn = "chroma:///.chroma_data"
        logger.info("No VECTOR_DSN provided, using default: %s", dsn)

    config = VectorStoreConfig(dsn)

    try:
        if config.scheme == "memory":
            # Memory store for tests
            env = (os.getenv("ENV") or os.getenv("APP_ENV") or "").strip().lower()
            is_test = (
                ("PYTEST_CURRENT_TEST" in os.environ)
                or ("pytest" in sys.modules)
                or env == "test"
            )
            if not is_test:
                raise RuntimeError(
                    "MemoryVectorStore is restricted to tests/dev environments"
                )
            logger.info("Using MemoryVectorStore")
            return MemoryVectorStore()

        elif config.scheme == "chroma":
            # ChromaDB - local or cloud
            try:
                from .chroma_store import ChromaVectorStore
            except ImportError:
                raise RuntimeError(
                    "ChromaVectorStore unavailable (chromadb not installed)"
                )

            if config.host or config.port:
                # Cloud mode
                if not config.username or not config.password:
                    raise ValueError("Chroma Cloud requires tenant and database in DSN")
                api_key = config.get_param("api_key", "")
                if not api_key:
                    raise ValueError("Chroma Cloud requires api_key parameter")

                # Set legacy env vars for ChromaVectorStore
                os.environ["CHROMA_API_KEY"] = api_key
                os.environ["CHROMA_TENANT_ID"] = config.username
                os.environ["CHROMA_DATABASE_NAME"] = config.password
                os.environ["VECTOR_STORE"] = "cloud"

                logger.info(
                    "Using ChromaVectorStore (Cloud): %s.%s",
                    config.username,
                    config.password,
                )
                return ChromaVectorStore()
            else:
                # Local mode
                chroma_path = config.path or ".chroma_data"
                os.environ["CHROMA_PATH"] = chroma_path
                os.environ["VECTOR_STORE"] = "chroma"

                logger.info("Using ChromaVectorStore (Local): %s", chroma_path)
                return ChromaVectorStore()

        elif config.scheme == "qdrant":
            # Qdrant HTTP/gRPC
            try:
                from .vector_store.qdrant import QdrantVectorStore

                if QdrantVectorStore is None:
                    raise RuntimeError(
                        "QdrantVectorStore unavailable (qdrant-client not installed)"
                    )
            except ImportError:
                raise RuntimeError(
                    "QdrantVectorStore unavailable (qdrant-client not installed)"
                )
            except Exception as e:
                raise RuntimeError(
                    f"QdrantVectorStore unavailable ({e})"
                )

            # Parse host:port
            host = config.host or "localhost"
            port = config.port or (6334 if "grpc" in dsn else 6333)
            protocol = "http" if "grpc" not in dsn else "grpc"

            # Check for custom url parameter (for cloud services)
            custom_url = config.get_param("url", "")
            if custom_url:
                url = custom_url
            else:
                url = f"{protocol}://{host}:{port}"
            api_key = config.get_param("api_key", "")

            # Set legacy env vars for QdrantVectorStore
            os.environ["QDRANT_URL"] = url
            if api_key:
                os.environ["QDRANT_API_KEY"] = api_key

            logger.info("Using QdrantVectorStore: %s", url)
            return QdrantVectorStore()

        elif config.scheme == "dual":
            # Dual read mode - parse nested DSN
            try:
                from .vector_store.dual import DualReadVectorStore

                if DualReadVectorStore is None:
                    raise RuntimeError(
                        "DualReadVectorStore unavailable (qdrant/chroma deps missing)"
                    )
            except ImportError:
                raise RuntimeError(
                    "DualReadVectorStore unavailable (qdrant/chroma deps missing)"
                )

            # Extract the nested DSN (everything after dual://)
            nested_dsn = dsn[7:]  # Remove "dual://"
            if not nested_dsn:
                raise ValueError(
                    "Dual mode requires nested DSN (e.g., dual://qdrant://host:port)"
                )

            # Parse nested config
            nested_config = VectorStoreConfig(nested_dsn)
            if nested_config.scheme != "qdrant":
                raise ValueError("Dual mode currently only supports qdrant as primary")

            # Set up Qdrant
            host = nested_config.host or "localhost"
            port = nested_config.port or 6333
            url = f"http://{host}:{port}"
            api_key = nested_config.get_param("api_key", "")

            os.environ["QDRANT_URL"] = url
            if api_key:
                os.environ["QDRANT_API_KEY"] = api_key

            # Set up Chroma fallback
            chroma_path = config.get_param("chroma_path", ".chroma_data")
            os.environ["CHROMA_PATH"] = chroma_path

            # Set dual mode flags
            os.environ["VECTOR_STORE"] = "dual"
            os.environ["VECTOR_DUAL_WRITE_BOTH"] = config.get_param("write_both", "0")
            os.environ["VECTOR_DUAL_QA_WRITE_BOTH"] = config.get_param(
                "qa_write_both", "0"
            )

            logger.info("Using DualReadVectorStore: Qdrant primary, Chroma fallback")
            return DualReadVectorStore()

        else:
            raise ValueError(f"Unsupported vector store scheme: {config.scheme}")

    except Exception as exc:
        if _strict_mode():
            logger.error("FATAL: Vector store init failed: %s", exc)
            raise

        logger.warning(
            "Vector store init failed (%s: %s); falling back to MemoryVectorStore",
            type(exc).__name__,
            exc,
        )
        return MemoryVectorStore()


def get_vector_store_info() -> dict[str, str]:
    """Get information about the current vector store configuration."""
    dsn = os.getenv("VECTOR_DSN", "").strip()
    if not dsn:
        # Check legacy VECTOR_STORE
        legacy_store = os.getenv("VECTOR_STORE", "").strip().lower()
        if legacy_store:
            dsn = f"legacy:{legacy_store}"
        else:
            dsn = "default:chroma:///.chroma_data"

    try:
        # Handle legacy format
        if dsn.startswith("legacy:"):
            legacy_type = dsn[7:]  # Remove "legacy:"
            if legacy_type == "chroma":
                chroma_path = os.getenv("CHROMA_PATH", ".chroma_data")
                return {
                    "dsn": dsn,
                    "scheme": "chroma",
                    "backend": "chroma",
                    "host": "",
                    "port": "",
                    "path": chroma_path,
                }
            elif legacy_type == "qdrant":
                url = os.getenv("QDRANT_URL", "http://localhost:6333")
                return {
                    "dsn": dsn,
                    "scheme": "qdrant",
                    "backend": "qdrant",
                    "host": "localhost",
                    "port": "6333",
                    "path": "",
                }
            else:
                return {
                    "dsn": dsn,
                    "scheme": legacy_type,
                    "backend": legacy_type,
                    "host": "",
                    "port": "",
                    "path": "",
                }

        # Handle default format
        if dsn.startswith("default:"):
            return {
                "dsn": dsn,
                "scheme": "chroma",
                "backend": "chroma",
                "host": "",
                "port": "",
                "path": ".chroma_data",
            }

        # Parse regular DSN
        config = VectorStoreConfig(dsn)
        return {
            "dsn": dsn,
            "scheme": config.scheme,
            "backend": config.scheme,
            "host": config.host or "",
            "port": str(config.port) if config.port else "",
            "path": config.path or "",
        }
    except Exception as e:
        return {"dsn": dsn, "error": str(e), "backend": "unknown"}
