#!/usr/bin/env python3

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-CSRF-Token"],
    max_age=600,
)

@app.get("/healthz/ready")
async def health_check():
    return {"status": "ok"}

@app.get("/v1/whoami")
async def whoami():
    return {"user_id": "test", "is_authenticated": True}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
