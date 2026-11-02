import os

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.ingredients import (
    handle_chat_message,
    load_substitutions,
    get_substitutions,
)

load_dotenv(dotenv_path="api.env")

router = APIRouter()

try:
    SUBSTITUTIONS = load_substitutions()
except (FileNotFoundError, ValueError) as e:
    print(f"[substitutions] not loaded: {e}")
    SUBSTITUTIONS = {}


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)


def add_substitutions(results):
    """Attach substitution hints for each recipe's missing ingredients."""
    for r in results:
        if "missed" in r:
            r["substitutions"] = get_substitutions(r["missed"], SUBSTITUTIONS)
    return results


# Plain `def` (not async): the work is blocking I/O (requests, Gemini),
# so FastAPI runs it in a worker thread and the server stays responsive.
@router.post("/chat")
def chat(req: ChatRequest):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured")

    try:
        response = handle_chat_message(req.message, api_key)
    except Exception as e:
        print(f"[chat] error: {type(e).__name__}: {e}")
        raise HTTPException(status_code=502, detail="Recipe lookup failed, try again")

    if response["type"] == "ingredient_search":
        add_substitutions(response["results"])

    return response