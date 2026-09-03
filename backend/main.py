import subprocess
import sys
import threading
import os
from contextlib import asynccontextmanager
from datetime import date, datetime
import json
import math
import sqlite3
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from data.database import initialize_database
from core.database import madden_database
from core.health import router as platform_health_router
from core.module_registry import module_registry
from modules.document_intelligence.integrations.receivables_repository import (
    ReceivablesRepository,
)
from modules.document_intelligence.integrations.invoice_owner_cache import (
    invoice_owner_cache_repository,
    refresh_invoice_owner_cache,
)
from modules.document_intelligence.integrations.history_repository import (
    HistoryRepository,
)
from modules.document_intelligence.cash_application.existing_provider import (
    ExistingCashApplicationProvider,
)
from modules.document_intelligence.cash_application.router import (
    configure_cash_application_data_provider,
)
from modules.document_intelligence.lockbox_preparation.active_provider import (
    ExistingReadOnlyPreparationProvider,
)
from modules.document_intelligence.lockbox_preparation.coordinator import (
    DurableLockboxPreparationCoordinator,
)
from modules.document_intelligence.lockbox_preparation.repository import (
    LockboxPreparationRepository,
)
from modules.document_intelligence.lockbox_preparation.router import (
    configure_durable_lockbox_preparation,
)
from modules.document_intelligence.lockbox_preparation.service import (
    DurableLockboxPreparationService,
)
from modules.document_intelligence.lockbox_review.service import (
    configure_current_open_ar_loader,
    configure_governed_preparation_loader,
)
from modules.document_intelligence.lockbox_preparation.contracts import (
    dataclass_payload,
)
from modules.document_intelligence.lockbox_preparation.source_loader import (
    SavedLockboxSourceLoader,
)
from modules.job_queue.service import job_queue_service
import core.jobs as job_queue

from decimal import Decimal
from modules.document_intelligence.services import (
    AIExplainer,
    HistoricalBehaviorEngine,
    InvoiceMatcher,
    RecommendationEngine,
)

from modules.workflow_foundation.access_control import ModuleAccessMiddleware
from modules.automations.scheduler import automation_scheduler
from customer_match import router as customer_match_router
from customer_risk import router as customer_risk_router

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sql_workspace import router as sql_workspace_router
from schema_explorer import router as schema_explorer_router
from sql_ai import router as sql_ai_router

# ---------------------------------------------------------
# Local-only configuration
# ---------------------------------------------------------

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
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
INDEX_SCRIPT_PATH = Path(__file__).resolve().parent / "index_documents.py"

index_job = {
    "running": False,
    "status": "idle",
    "started_at": None,
    "completed_at": None,
    "return_code": None,
    "message": "No indexing job has been run.",
    "output": "",
}

index_job_lock = threading.Lock()


# ---------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    automation_scheduler.start()
    lockbox_preparation_coordinator.resume_recovered()

    try:
        yield
    finally:
        automation_scheduler.stop()


app = FastAPI(
    title="Enterprise AI Workbench API",
    version="0.2.0",
    lifespan=lifespan,
)

initialize_database()

app.add_middleware(ModuleAccessMiddleware)
cors_origins = [
    "http://127.0.0.1:5173",
    "http://localhost:5173",
]
configured_app_url = os.getenv("ETOP_APP_URL")
if configured_app_url:
    parsed_app_url = urlsplit(configured_app_url)
    if parsed_app_url.scheme not in {"http", "https"} or not parsed_app_url.netloc:
        raise RuntimeError("ETOP_APP_URL must be a valid http(s) application URL.")
    cors_origins.append(f"{parsed_app_url.scheme}://{parsed_app_url.netloc}")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(sql_workspace_router)
app.include_router(schema_explorer_router)
app.include_router(sql_ai_router)
app.include_router(platform_health_router)
app.include_router(customer_match_router)
app.include_router(customer_risk_router)

# Every business module is registered the same way, through the manifest-
# based ModuleRegistry: a broken module's import/router-mount failure is
# captured as a "failed" module status instead of taking down every other
# module and the platform itself (see ADR-005 in Architecture Decisions.md).
for module_path in (
    "modules.document_intelligence",
    "modules.reports",
    "modules.customer_360",
    "modules.credit_risk",
    "modules.accounts_payable",
    "modules.payment_notes",
    "modules.workflow_foundation",
    "modules.financial_close",
    "modules.erp_evidence",
    "modules.automations",
    "modules.platform_search",
    "modules.vendor_intelligence",
    "modules.ar_collections",
    "modules.freight_logistics",
    "modules.inventory_purchasing",
    "modules.tax_compliance",
    "modules.sales_order_visibility",
    "modules.pricing_contracts",
    "modules.general_ledger",
    "modules.cash_flow_forecasting",
    "modules.job_queue",
):
    module_registry.register(app, module_path)

receivables_repository = ReceivablesRepository(
    database=madden_database,
    invoice_owner_cache=invoice_owner_cache_repository,
)

cash_application_provider = ExistingCashApplicationProvider(
    receivables_repository=receivables_repository,
)

configure_cash_application_data_provider(
    cash_application_provider
)

lockbox_preparation_repository = LockboxPreparationRepository()
lockbox_preparation_provider = ExistingReadOnlyPreparationProvider(
    receivables_repository=receivables_repository,
)

job_queue_service.recover_interrupted()


def _on_lockbox_job_queued(job_id: str) -> None:
    snapshot = lockbox_preparation_repository.get_job(job_id)
    title = f"Lockbox batch {snapshot.get('source_reference') or job_id}"
    job_queue.enqueue(job_id, "lockbox_preparation", title)
    job_queue.mark_running(job_id)


def _on_lockbox_job_complete(
    job_id: str,
    result: dict | None,
    error: BaseException | None,
) -> None:
    if error is not None:
        job_queue.mark_failed(job_id, message=str(error))
        return
    result = result or {}
    balanced_count = result.get("balanced_count")
    exception_count = result.get("exception_count")
    job_queue.mark_completed(
        job_id,
        message=f"{balanced_count} balanced, {exception_count} need review",
        result_module="Lockbox Automation",
        result_reference=job_id,
    )


lockbox_preparation_coordinator = DurableLockboxPreparationCoordinator(
    repository=lockbox_preparation_repository,
    provider=lockbox_preparation_provider,
    on_job_queued=_on_lockbox_job_queued,
    on_job_complete=_on_lockbox_job_complete,
)
lockbox_preparation_service = DurableLockboxPreparationService(
    coordinator=lockbox_preparation_coordinator,
    source_loader=SavedLockboxSourceLoader(),
)
configure_durable_lockbox_preparation(
    lockbox_preparation_service
)
configure_governed_preparation_loader(
    lambda source_job_id: lockbox_preparation_service.current_source_job(
        source_job_id,
        include_transactions=True,
    )
)
configure_current_open_ar_loader(
    lambda customer_number, as_of_date: dataclass_payload(
        lockbox_preparation_provider.load_open_ar(
            customer_number,
            as_of_date,
        )
    )
)

invoice_matcher = InvoiceMatcher()

history_repository = HistoryRepository(
    database=madden_database,
)

historical_behavior_engine = HistoricalBehaviorEngine()
recommendation_engine = RecommendationEngine()
ai_explainer = AIExplainer()

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

def run_full_index() -> None:
    with index_job_lock:
        index_job["running"] = True
        index_job["status"] = "running"
        index_job["started_at"] = datetime.now().isoformat(timespec="seconds")
        index_job["completed_at"] = None
        index_job["return_code"] = None
        index_job["message"] = "Indexing all local SOP folders."
        index_job["output"] = ""

    try:
        result = subprocess.run(
            [
                sys.executable,
                str(INDEX_SCRIPT_PATH),
                "--all",
            ],
            cwd=str(INDEX_SCRIPT_PATH.parent),
            capture_output=True,
            text=True,
            timeout=7200,
            check=False,
        )

        combined_output = "\n".join(
            value.strip()
            for value in [result.stdout, result.stderr]
            if value and value.strip()
        )

        with index_job_lock:
            index_job["running"] = False
            index_job["completed_at"] = datetime.now().isoformat(
                timespec="seconds"
            )
            index_job["return_code"] = result.returncode
            index_job["output"] = combined_output[-15000:]

            if result.returncode == 0:
                index_job["status"] = "completed"
                index_job["message"] = (
                    "The local knowledge base was updated successfully."
                )
            else:
                index_job["status"] = "failed"
                index_job["message"] = (
                    "The indexing process completed with errors."
                )

    except subprocess.TimeoutExpired:
        with index_job_lock:
            index_job["running"] = False
            index_job["status"] = "failed"
            index_job["completed_at"] = datetime.now().isoformat(
                timespec="seconds"
            )
            index_job["message"] = (
                "Indexing exceeded the two-hour time limit."
            )

    except Exception as exc:
        with index_job_lock:
            index_job["running"] = False
            index_job["status"] = "failed"
            index_job["completed_at"] = datetime.now().isoformat(
                timespec="seconds"
            )
            index_job["message"] = f"Indexing failed: {exc}"

# ---------------------------------------------------------
# API endpoints
# ---------------------------------------------------------

@app.get("/api/test/open-invoices/{customer_number}")
def test_open_invoices(
    customer_number: str,
    aging_as_of_date: date | None = None,
) -> dict:
    effective_aging_date = aging_as_of_date or date.today()

    invoices = receivables_repository.get_open_invoices(
        customer_number=customer_number,
        aging_as_of_date=effective_aging_date,
    )

    return {
        "customer_number": customer_number,
        "aging_as_of_date": effective_aging_date,
        "invoice_count": len(invoices),
        "invoices": [
            invoice.model_dump()
            for invoice in invoices
        ],
    }

@app.get("/api/test/invoice-match/{customer_number}")
def test_invoice_match(
    customer_number: str,
    payment_amount: Decimal,
    invoice_number: str | None = None,
    aging_as_of_date: date | None = None,
) -> dict:
    effective_aging_date = (
        aging_as_of_date or date.today()
    )

    invoices = receivables_repository.get_open_invoices(
        customer_number=customer_number,
        aging_as_of_date=effective_aging_date,
    )

    supplied_invoice_numbers = (
        [invoice_number]
        if invoice_number
        else []
    )

    result = invoice_matcher.match(
        customer_number=customer_number,
        payment_amount=payment_amount,
        open_invoices=invoices,
        supplied_invoice_numbers=(
            supplied_invoice_numbers
        ),
    )

    return result.model_dump()


@app.get("/api/test/cash-application-recommendation/{customer_number}")
def test_cash_application_recommendation(
    customer_number: str,
    payment_amount: Decimal,
    invoice_number: str | None = None,
    aging_as_of_date: date | None = None,
    include_history: bool = True,
) -> dict:
    effective_aging_date = (
        aging_as_of_date or date.today()
    )

    invoices = receivables_repository.get_open_invoices(
        customer_number=customer_number,
        aging_as_of_date=effective_aging_date,
    )

    historical_behavior = None

    if include_history:
        payment_groups = (
            history_repository.get_historical_payment_groups(
            customer_number=customer_number,
            limit=500,
            )
        )

        historical_behavior = historical_behavior_engine.analyze(
            customer_number=customer_number,
            payment_groups=payment_groups,
        )    

    recommendation = recommendation_engine.recommend(
        customer_number=customer_number,
        payment_amount=payment_amount,
        open_invoices=invoices,
        supplied_invoice_numbers=(
            [invoice_number]
            if invoice_number
            else []
        ),
        historical_behavior=historical_behavior,
    )

    return {
        "recommendation": recommendation.model_dump(),
        "explanation": ai_explainer.explain(
            recommendation
        ),
    }


@app.get("/health")
def health() -> dict:
    """Return launcher-safe local runtime readiness.

    This endpoint intentionally exposes only coarse readiness facts. Protected
    module, SQL, and knowledge endpoints remain authenticated.
    """

    knowledge_ready = DATABASE_PATH.exists()

    try:
        madden_status = madden_database.test_connection()
        madden_database_ready = bool(madden_status.get("connected"))
    except Exception:
        # Health must report dependency readiness without exposing database
        # connection details or turning a dependency outage into a 5xx.
        madden_database_ready = False

    return {
        "status": "healthy",
        "backend": "local",
        "backend_ready": True,
        "madden_database_ready": madden_database_ready,
        "knowledge_database_exists": knowledge_ready,
        "knowledge_ready": knowledge_ready,
        "ollama": OLLAMA_BASE_URL,
        "chat_model": CHAT_MODEL,
        "embedding_model": EMBEDDING_MODEL,
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
@app.post("/knowledge/reindex")
def reindex_knowledge() -> dict:
    with index_job_lock:
        if index_job["running"]:
            raise HTTPException(
                status_code=409,
                detail="A knowledge-base indexing job is already running.",
            )

        index_thread = threading.Thread(
            target=run_full_index,
            daemon=True,
        )
        index_thread.start()

    return {
        "started": True,
        "message": "Local SOP indexing has started.",
    }


@app.get("/knowledge/reindex/status")
def reindex_status() -> dict:
    with index_job_lock:
        return dict(index_job)

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

class CustomerIntelligenceSummaryRequest(BaseModel):
    customer: dict
    health: dict
    recommendations: list[dict]


@app.post("/api/v1/customer-intelligence/summary")
def generate_customer_intelligence_summary(payload: CustomerIntelligenceSummaryRequest):
    """Generate a local, grounded customer summary. Calculations stay deterministic in ETOP."""
    prompt = f"""You are an enterprise credit and customer analyst.
Use only the JSON provided. Do not invent facts or numbers.
Write a concise executive account summary under 160 words.
Explain the health score, the strongest positive signal, the largest risk, and the recommended next action.

DATA:
{json.dumps(payload.model_dump(), default=str)}
"""
    try:
        response = requests.post(
            OLLAMA_CHAT_URL,
            json={
                "model": CHAT_MODEL,
                "stream": False,
                "messages": [{"role": "user", "content": prompt}],
                "options": {"temperature": 0.1},
            },
            timeout=120,
        )
        response.raise_for_status()
        content = response.json().get("message", {}).get("content", "").strip()
        if not content:
            raise ValueError("Ollama returned an empty summary.")
        return {
            "summary": content,
            "model": CHAT_MODEL,
            "generated_at": datetime.now().isoformat(),
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Local AI summary unavailable: {exc}") from exc
