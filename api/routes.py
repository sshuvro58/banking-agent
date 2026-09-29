"""
API Routes — the REST endpoints.

Only 5 user-facing routes. Not CRUD per table.
Everything funnels through POST /api/chat.

The /chat endpoint flow:
  1. verify_token (JWT)
  2. Get or create session
  3. Store user message
  4. Redact PII
  5. Delegate to coordinator
  6. Restore PII in response
  7. Store assistant response
  8. Return reply + session_id + agent_used + cost
"""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from typing import Optional

from security.authentication import create_token, verify_token
from security.pii_redaction import pii_redactor
from db.repositories.session_repo import session_repo
from db.repositories.observability_repo import observability_repo
from agents.coordinator import coordinator
from observability.logger import get_system_metrics

router = APIRouter()


# ── Request/Response models ───────────────────────────

class LoginRequest(BaseModel):
    customer_id: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    agent_used: Optional[str] = None
    cost: Optional[dict] = None


# ── Auth endpoint ─────────────────────────────────────

@router.post("/auth/login", response_model=TokenResponse)
async def login(req: LoginRequest, request: Request):
    """
    Authenticate and get a JWT.
    In production: OAuth2 with the bank's identity provider.
    """
    token = await create_token(req.customer_id, req.password)

    # Audit trail
    client_ip = request.client.host if request.client else None
    await observability_repo.audit(
        action="login",
        customer_id=req.customer_id,
        ip_address=client_ip,
    )

    return TokenResponse(access_token=token)


# ── Chat endpoint (THE main endpoint) ─────────────────

@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, user_claims: dict = Depends(verify_token)):
    """
    The single user-facing endpoint for the entire agentic system.
    Everything else happens internally.
    """
    customer_id = user_claims["sub"]

    # ── Session management ────────────────────────
    if req.session_id:
        session = await session_repo.get_session(req.session_id)
        if not session:
            session = await session_repo.create_session(customer_id)
    else:
        session = await session_repo.create_session(customer_id)

    session_id = session["session_id"]

    # ── Store user message ────────────────────────
    await session_repo.add_message(session_id, "user", req.message)

    # ── PII Redaction ─────────────────────────────
    redacted_message = await pii_redactor.redact(req.message, session_id)

    # ── Delegate to Coordinator ───────────────────
    result = await coordinator.handle_message(
        message=redacted_message,
        session_id=session_id,
        user_claims=user_claims,
    )

    # ── Restore PII in response ───────────────────
    reply = await pii_redactor.restore(result["reply"], session_id)

    # ── Store assistant response ──────────────────
    await session_repo.add_message(
        session_id, "assistant", reply,
        agent_used=result.get("agent_used"),
    )

    return ChatResponse(
        reply=reply,
        session_id=session_id,
        agent_used=result.get("agent_used"),
        cost=result.get("cost"),
    )


# ── Admin endpoints (observability) ───────────────────

@router.get("/admin/traces/{session_id}")
async def get_session_traces(session_id: str):
    """View all agent traces for a session."""
    traces = await observability_repo.get_session_traces(session_id)
    return {"session_id": session_id, "traces": traces}


@router.get("/admin/traces")
async def get_all_traces():
    """View recent traces across all sessions."""
    traces = await observability_repo.get_all_traces()
    return {"traces": traces}


@router.get("/admin/costs")
async def get_total_costs():
    """View total LLM spend."""
    return await observability_repo.get_total_cost()


@router.get("/admin/costs/{session_id}")
async def get_session_costs(session_id: str):
    """View cost for a specific session."""
    return await observability_repo.get_session_cost(session_id)


@router.get("/admin/metrics")
async def get_metrics():
    """System metrics — CPU, memory, disk."""
    return get_system_metrics()


@router.get("/admin/history/{session_id}")
async def get_chat_history(session_id: str):
    """View conversation history for a session."""
    history = await session_repo.get_history(session_id)
    return {"session_id": session_id, "messages": history}


@router.get("/health")
async def health():
    return {"status": "healthy"}