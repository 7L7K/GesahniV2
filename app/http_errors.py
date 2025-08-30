from __future__ import annotations

from typing import Mapping

from fastapi import HTTPException


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
    hdrs = {"WWW-Authenticate": "Bearer"}
    if headers:
        hdrs.update(dict(headers))
    return HTTPException(status_code=401, detail={"code": code, "message": message, "hint": hint}, headers=hdrs)


__all__ = ["unauthorized"]

