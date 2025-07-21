import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
import os
from .router import route_prompt

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="GesahniV2")

class AskRequest(BaseModel):
    prompt: str

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
