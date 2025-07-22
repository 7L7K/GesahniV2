import logging
import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from .router import route_prompt
from .home_assistant import get_states, call_service, resolve_entities, verify_connection
from .logging_config import configure_logging
from .middleware import RequestIDMiddleware
from .status import router as status_router
from .llama_integration import router as llama_router, verify_model

load_dotenv()
configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="GesahniV2")
app.add_middleware(RequestIDMiddleware)
app.include_router(status_router)
app.include_router(llama_router)

@app.on_event("startup")
async def startup_checks():
    await verify_connection()
    await verify_model()


class AskRequest(BaseModel):
    prompt: str


class ServiceRequest(BaseModel):
    domain: str
    service: str
    data: dict | None = None


@app.post("/ask")
async def ask(req: AskRequest):
    logger.info("Received prompt: %s", req.prompt)
    try:
        answer = await route_prompt(req.prompt)
        return {"response": answer}
    except Exception as e:
        logger.exception("Error processing prompt: %s", e)
        raise HTTPException(status_code=500, detail="Error processing prompt")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/config")
async def config():
    # Return environment variables loaded from .env
    config_vars = {k: v for k, v in os.environ.items() if k.isupper()}
    return config_vars


@app.post("/intent-test")
async def intent_test(req: AskRequest):
    logger.info("Intent test for: %s", req.prompt)
    # Placeholder: simply echo the prompt
    return {"intent": "test", "prompt": req.prompt}


@app.get("/ha/entities")
async def ha_entities():
    try:
        return await get_states()
    except Exception as e:
        logger.exception("HA states error: %s", e)
        raise HTTPException(status_code=500, detail="Home Assistant error")


@app.post("/ha/service")
async def ha_service(req: ServiceRequest):
    try:
        resp = await call_service(req.domain, req.service, req.data or {})
        return resp or {"status": "ok"}
    except Exception as e:
        logger.exception("HA service error: %s", e)
        raise HTTPException(status_code=500, detail="Home Assistant error")


@app.get("/ha/resolve")
async def ha_resolve(name: str):
    try:
        entities = await resolve_entities(name)
        if entities:
            return {"entity_id": entities[0]}
        raise HTTPException(status_code=404, detail="Entity not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("HA resolve error: %s", e)
        raise HTTPException(status_code=500, detail="Home Assistant error")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
