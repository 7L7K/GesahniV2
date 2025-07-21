from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .router import route_prompt

app = FastAPI(title="Gesahni Assistant")


class AskRequest(BaseModel):
    prompt: str


class AskResponse(BaseModel):
    response: str


@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest):
    try:
        answer = route_prompt(request.prompt)
        return AskResponse(response=answer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
    return {"status": "ok"}
