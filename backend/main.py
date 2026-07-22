import json
import math
import sqlite3
from pathlib import Path
from typing import Literal

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


# ---------------------------------------------------------
# Local-only configuration
# ---------------------------------------------------------

OLLAMA_BASE_URL = "http://127.0.0.1:11434"
OLLAMA_CHAT_URL = f"{OLLAMA_BASE_URL}/api/chat"
OLLAMA_EMBED_URL = f"{OLLAMA_BASE_URL}/api/embed"

CHAT_MODEL = "gemma3:12b"
EMBEDDING_MODEL = "nomic-embed-text"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_PATH = (
    PROJECT_ROOT
    / "data"
    / "vectorstore"
    / "knowledge.db"
)

DEFAULT_TOP_K = 6
MAX_TOP_K = 10
MINIMUM_SIMILARITY = 0.30


# ---------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------

app = FastAPI(
    title="Enterprise AI Workbench API",
    version="0.2.0",
)

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


# ---------------------------------------------------------
# Request and response models
# ---------------------------------------------------------

class Message(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str = Field(min_length=1, max_length=20_000)


class ChatRequest(BaseModel):
    messages: list[Message]


class ChatResponse(BaseModel):
    response: str
    model: str


class KnowledgeChatRequest(BaseModel):
    messages: list[Message]
    top_k: int = Field(default=DEFAULT_TOP_K, ge=1, le=MAX_TOP_K)
    department: str | None = None


class SourceResult(BaseModel):
    file_path: str
    file_name: str
    department: str | None
    page_number: int | None
    chunk_number: int
    similarity: float
    excerpt: str


class KnowledgeChatResponse(BaseModel):
    response: str
    model: str
    sources: list[SourceResult]
    search_mode: str


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=5_000)
    top_k: int = Field(default=DEFAULT_TOP_K, ge=1, le=MAX_TOP_K)
    department: str | None = None


class KnowledgeSearchResponse(BaseModel):
    results: list[SourceResult]


# ---------------------------------------------------------
# Utility functions
# ---------------------------------------------------------

def get_database_connection() -> sqlite3.Connection:
    if not DATABASE_PATH.exists():
        raise HTTPException(
            status_code=503,
            detail=(
                "The local knowledge database does not exist. "
                "Run index_documents.py first."
            ),
        )

    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def create_embedding(text: str) -> list[float]:
    try:
        response = requests.post(
            OLLAMA_EMBED_URL,
            json={
                "model": EMBEDDING_MODEL,
                "input": text,
            },
            timeout=300,
        )
        response.raise_for_status()

    except requests.ConnectionError as exc:
        raise HTTPException(
            status_code=503,
            detail="Ollama is not running on this computer.",
        ) from exc

    except requests.Timeout as exc:
        raise HTTPException(
            status_code=504,
            detail="The local embedding model took too long to respond.",
        ) from exc

    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Ollama embedding request failed: {exc}",
        ) from exc

    data = response.json()
    embeddings = data.get("embeddings")

    if not embeddings or not embeddings[0]:
        raise HTTPException(
            status_code=502,
            detail="Ollama returned no embedding.",
        )

    return embeddings[0]


def cosine_similarity(
    vector_a: list[float],
    vector_b: list[float],
) -> float:
    if not vector_a or not vector_b:
        return 0.0

    if len(vector_a) != len(vector_b):
        return 0.0

    dot_product = sum(
        a_value * b_value
        for a_value, b_value in zip(vector_a, vector_b)
    )

    magnitude_a = math.sqrt(
        sum(value * value for value in vector_a)
    )

    magnitude_b = math.sqrt(
        sum(value * value for value in vector_b)
    )

    if magnitude_a == 0 or magnitude_b == 0:
        return 0.0

    return dot_product / (magnitude_a * magnitude_b)


def search_knowledge(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    department: str | None = None,
) -> list[SourceResult]:
    query_embedding = create_embedding(query)
    connection = get_database_connection()

    try:
        if department:
            rows = connection.execute(
                """
                SELECT
                    file_path,
                    file_name,
                    department,
                    page_number,
                    chunk_number,
                    content,
                    embedding
                FROM document_chunks
                WHERE LOWER(department) = LOWER(?)
                """,
                (department,),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT
                    file_path,
                    file_name,
                    department,
                    page_number,
                    chunk_number,
                    content,
                    embedding
                FROM document_chunks
                """
            ).fetchall()

    finally:
        connection.close()

    scored_results: list[tuple[float, sqlite3.Row]] = []

    for row in rows:
        try:
            stored_embedding = json.loads(row["embedding"])
        except (TypeError, json.JSONDecodeError):
            continue

        similarity = cosine_similarity(
            query_embedding,
            stored_embedding,
        )

        if similarity >= MINIMUM_SIMILARITY:
            scored_results.append((similarity, row))

    scored_results.sort(
        key=lambda result: result[0],
        reverse=True,
    )

    results: list[SourceResult] = []

    for similarity, row in scored_results[:top_k]:
        content = row["content"].strip()

        excerpt = content[:500]

        if len(content) > 500:
            excerpt += "..."

        results.append(
            SourceResult(
                file_path=row["file_path"],
                file_name=row["file_name"],
                department=row["department"],
                page_number=row["page_number"],
                chunk_number=row["chunk_number"],
                similarity=round(similarity, 4),
                excerpt=excerpt,
            )
        )

    return results


def get_full_source_content(
    sources: list[SourceResult],
) -> list[dict]:
    if not sources:
        return []

    connection = get_database_connection()
    full_sources: list[dict] = []

    try:
        for source_number, source in enumerate(
            sources,
            start=1,
        ):
            row = connection.execute(
                """
                SELECT content
                FROM document_chunks
                WHERE file_path = ?
                  AND chunk_number = ?
                LIMIT 1
                """,
                (
                    source.file_path,
                    source.chunk_number,
                ),
            ).fetchone()

            if not row:
                continue

            full_sources.append(
                {
                    "source_number": source_number,
                    "file_path": source.file_path,
                    "page_number": source.page_number,
                    "content": row["content"],
                }
            )

    finally:
        connection.close()

    return full_sources


def call_ollama_chat(
    messages: list[dict[str, str]],
    temperature: float = 0.2,
) -> str:
    try:
        response = requests.post(
            OLLAMA_CHAT_URL,
            json={
                "model": CHAT_MODEL,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": temperature,
                },
            },
            timeout=300,
        )

        response.raise_for_status()

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

    data = response.json()
    response_text = (
        data.get("message", {})
        .get("content", "")
        .strip()
    )

    if not response_text:
        raise HTTPException(
            status_code=502,
            detail="Ollama returned an empty response.",
        )

    return response_text


def get_latest_user_question(
    messages: list[Message],
) -> str:
    for message in reversed(messages):
        if message.role == "user":
            return message.content.strip()

    raise HTTPException(
        status_code=400,
        detail="No user question was provided.",
    )


# ---------------------------------------------------------
# API endpoints
# ---------------------------------------------------------

@app.get("/health")
def health() -> dict:
    return {
        "status": "healthy",
        "backend": "local",
        "ollama": OLLAMA_BASE_URL,
        "chat_model": CHAT_MODEL,
        "embedding_model": EMBEDDING_MODEL,
        "knowledge_database_exists": DATABASE_PATH.exists(),
        "knowledge_database": str(DATABASE_PATH),
    }


@app.get("/knowledge/status")
def knowledge_status() -> dict:
    if not DATABASE_PATH.exists():
        return {
            "ready": False,
            "documents": 0,
            "chunks": 0,
            "database": str(DATABASE_PATH),
        }

    connection = get_database_connection()

    try:
        chunk_count = connection.execute(
            "SELECT COUNT(*) FROM document_chunks"
        ).fetchone()[0]

        document_count = connection.execute(
            """
            SELECT COUNT(DISTINCT file_path)
            FROM document_chunks
            """
        ).fetchone()[0]

        departments = [
            row[0]
            for row in connection.execute(
                """
                SELECT DISTINCT department
                FROM document_chunks
                WHERE department IS NOT NULL
                  AND department <> ''
                ORDER BY department
                """
            ).fetchall()
        ]

    finally:
        connection.close()

    return {
        "ready": chunk_count > 0,
        "documents": document_count,
        "chunks": chunk_count,
        "departments": departments,
        "database": str(DATABASE_PATH),
    }


@app.post(
    "/knowledge/search",
    response_model=KnowledgeSearchResponse,
)
def knowledge_search(
    request: KnowledgeSearchRequest,
) -> KnowledgeSearchResponse:
    results = search_knowledge(
        query=request.query,
        top_k=request.top_k,
        department=request.department,
    )

    return KnowledgeSearchResponse(results=results)


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    if not request.messages:
        raise HTTPException(
            status_code=400,
            detail="At least one message is required.",
        )

    response_text = call_ollama_chat(
        messages=[
            message.model_dump()
            for message in request.messages
        ],
        temperature=0.3,
    )

    return ChatResponse(
        response=response_text,
        model=CHAT_MODEL,
    )


@app.post(
    "/knowledge/chat",
    response_model=KnowledgeChatResponse,
)
def knowledge_chat(
    request: KnowledgeChatRequest,
) -> KnowledgeChatResponse:
    if not request.messages:
        raise HTTPException(
            status_code=400,
            detail="At least one message is required.",
        )

    user_question = get_latest_user_question(
        request.messages
    )

    sources = search_knowledge(
        query=user_question,
        top_k=request.top_k,
        department=request.department,
    )

    if not sources:
        return KnowledgeChatResponse(
            response=(
                "I could not find enough relevant information in "
                "the indexed company SOPs to answer this question. "
                "Try rewording the question or confirm that the "
                "correct folder has been indexed."
            ),
            model=CHAT_MODEL,
            sources=[],
            search_mode="local_sop_search",
        )

    full_sources = get_full_source_content(sources)

    context_sections = []

    for source in full_sources:
        source_label = f"[Source {source['source_number']}]"
        location = source["file_path"]

        if source["page_number"] is not None:
            location += (
                f", page {source['page_number']}"
            )

        context_sections.append(
            f"{source_label}\n"
            f"Location: {location}\n"
            f"Content:\n{source['content']}"
        )

    document_context = "\n\n---\n\n".join(
        context_sections
    )

    system_prompt = """
You are the local Enterprise AI Assistant.

Answer the user's question using only the supplied company document
context.

Rules:
1. Do not use outside knowledge to fill gaps.
2. Do not invent procedures, requirements, names, dates, or steps.
3. Cite supporting statements using [Source 1], [Source 2], etc.
4. If the documents do not contain enough information, clearly say so.
5. Explain conflicting document instructions when conflicts are present.
6. Keep the answer practical and clearly organized.
7. Do not claim that you searched the internet.
8. The supplied context came from files stored on this computer.
""".strip()

    knowledge_prompt = f"""
USER QUESTION:
{user_question}

LOCAL COMPANY DOCUMENT CONTEXT:
{document_context}

Answer the user using only the context above. Include inline source
references such as [Source 1].
""".strip()

    recent_history = [
        message.model_dump()
        for message in request.messages[-6:-1]
        if message.role in {"user", "assistant"}
    ]

    ollama_messages = [
        {
            "role": "system",
            "content": system_prompt,
        },
        *recent_history,
        {
            "role": "user",
            "content": knowledge_prompt,
        },
    ]

    response_text = call_ollama_chat(
        messages=ollama_messages,
        temperature=0.1,
    )

    return KnowledgeChatResponse(
        response=response_text,
        model=CHAT_MODEL,
        sources=sources,
        search_mode="local_sop_search",
    )