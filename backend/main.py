from typing import Literal

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_MODEL = "gemma3:12b"

app = FastAPI(
    title="Enterprise AI Workbench API",
    version="0.1.0",
)

# Only allow the local Vite frontend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class Message(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str = Field(min_length=1, max_length=20000)


class ChatRequest(BaseModel):
    messages: list[Message]


class ChatResponse(BaseModel):
    response: str
    model: str


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "healthy",
        "backend": "local",
        "ollama": OLLAMA_URL,
        "model": OLLAMA_MODEL,
    }


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    if not request.messages:
        raise HTTPException(status_code=400, detail="At least one message is required.")

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [message.model_dump() for message in request.messages],
        "stream": False,
        "options": {
            "temperature": 0.3,
        },
    }

    try:
        ollama_response = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=300,
        )
        ollama_response.raise_for_status()
    except requests.ConnectionError as exc:
        raise HTTPException(
            status_code=503,
            detail="Ollama is not running on this computer.",
        ) from exc
    except requests.Timeout as exc:
        raise HTTPException(
            status_code=504,
            detail="The local model took too long to respond.",
        ) from exc
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Ollama request failed: {exc}",
        ) from exc

    data = ollama_response.json()
    response_text = data.get("message", {}).get("content", "").strip()

    if not response_text:
        raise HTTPException(
            status_code=502,
            detail="Ollama returned an empty response.",
        )

    return ChatResponse(
        response=response_text,
        model=OLLAMA_MODEL,
    )