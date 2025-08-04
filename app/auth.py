from __future__ import annotations

import json
import os
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException
from jose import jwt
from pydantic import BaseModel

ALGORITHM = "HS256"
SECRET_KEY = os.getenv("JWT_SECRET", "change-me")
EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "30"))

try:
    _users_raw = os.getenv("LOGIN_USERS", "{}")
    USERS: dict[str, str] = json.loads(_users_raw)
except json.JSONDecodeError:
    USERS = {}

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest) -> TokenResponse:
    stored = USERS.get(req.username)
    if stored is None or stored != req.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    expire = datetime.utcnow() + timedelta(minutes=EXPIRE_MINUTES)
    payload = {"sub": req.username, "exp": expire}
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return TokenResponse(access_token=token)
