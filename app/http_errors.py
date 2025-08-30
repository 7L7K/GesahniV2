from __future__ import annotations

from typing import Mapping

from fastapi import HTTPException
from .error_envelope import build_error


def unauthorized(
    *,
    code: str = "unauthorized",
    message: str = "unauthorized",
    hint: str = "provide a valid bearer token or auth cookies",
    headers: Mapping[str, str] | None = None,
) -> HTTPException:
    """Return a standardized 401 HTTPException with structured detail.

    Detail shape: {code, message, hint}
    Includes a default WWW-Authenticate header unless headers overrides it.
    """
    hdrs = {"WWW-Authenticate": "Bearer", "X-Error-Code": code}
    if headers:
        hdrs.update(dict(headers))
    env = build_error(code=code, message=message, hint=hint, details={"status_code": 401})
    return HTTPException(status_code=401, detail=env, headers=hdrs)


def http_error(
    *, code: str, message: str, status: int = 400, hint: str | None = None, headers: Mapping[str, str] | None = None
) -> HTTPException:
    hdrs = {"X-Error-Code": code}
    if headers:
        hdrs.update(dict(headers))
    env = build_error(code=code, message=message, hint=hint, details={"status_code": status})
    return HTTPException(status_code=status, detail=env, headers=hdrs)


__all__ = ["unauthorized", "http_error"]
